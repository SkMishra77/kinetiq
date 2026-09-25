"""create_program, edit_session_template, set_program_phase, get_program tools."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db.repos import exercises as exr
from ..db.repos import programs as prg
from ..domain.models import ProgramInput
from ..services import Services


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="create_program",
        description=(
            "Store a training program you have designed for the user (split, "
            "sessions, exercises with sets × rep range, target RIR, rest, tempo, "
            "progression rule, deload policy, rationale). Use once after "
            "onboarding and whenever a new goal or schedule needs a new program. "
            "Exercises are resolved against the library; unresolved names come "
            "back as `unresolved` and the program is NOT stored. `dry_run=true` "
            "returns the same validation without writing. Activating archives "
            "the previous active program (reversible via set_program_phase)."
        ),
        annotations=ToolAnnotations(
            title="Create Program", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def create_program(program: ProgramInput,
                        dry_run: Annotated[bool, Field(default=False)] = False) -> dict:
        # Resolve exercises
        unresolved: list[dict] = []
        resolved_sessions = []
        for s in program.sessions:
            re_exs = []
            for te in s.exercises:
                res = exr.resolve_name(svc.db, te.exercise)
                if not res.exercise_id:
                    unresolved.append({"input": te.exercise, "candidates": res.candidates})
                    continue
                re_exs.append((res.exercise_id, te))
            resolved_sessions.append((s, re_exs))
        if unresolved:
            return {"status": "needs_resolution", "unresolved": unresolved,
                     "echo": "Could not resolve some exercise names; please correct or add them first."}
        if dry_run:
            return {"status": "ok_dry_run",
                     "sessions": [{"name": s.name, "exercises": [
                         {"exercise": te.exercise, "sets": te.sets,
                          "rep_range": (te.rep_min, te.rep_max)} for te in s.exercises
                     ]} for s, _ in resolved_sessions],
                     "echo": "Validation passed (dry_run)."}
        prg.archive_active(svc.db, reason="replaced by create_program")
        pid = prg.create_program(
            svc.db, name=program.name, goal=program.goal,
            split_type=program.split_type, days_per_week=program.days_per_week,
            progression_model=program.progression_model,
            block_length_weeks=program.block_length_weeks,
            deload_policy=program.deload_policy, rationale=program.rationale,
            activate=program.activate,
        )
        for i, (s, te_list) in enumerate(resolved_sessions, start=1):
            tid = prg.add_session_template(
                svc.db, pid, i, name=s.name, key_name=s.key_name,
                focus=s.focus, target_muscles=s.target_muscles,
                est_minutes=s.est_minutes,
            )
            for j, (eid, te) in enumerate(te_list, start=1):
                prg.add_template_exercise(
                    svc.db, tid, j, exercise_id=eid, sets=te.sets,
                    rep_min=te.rep_min, rep_max=te.rep_max,
                    target_rir=te.target_rir, rest_s=te.rest_s,
                    tempo=te.tempo, role=te.role,
                    progression_rule=te.progression_rule,
                    increment_kg=te.increment_kg,
                    start_weight_kg=te.start_weight_kg,
                    is_optional=te.is_optional, notes=te.notes,
                )
        return {"status": "stored", "program_id": pid,
                 "echo": f"Stored program '{program.name}' with {len(resolved_sessions)} templates."}

    @mcp.tool(
        name="get_program",
        description=(
            "Return the active program (or a specific program_id) with all "
            "session templates, template exercises and the active block."
        ),
        annotations=ToolAnnotations(
            title="Get Program", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def get_program(program_id: Annotated[int | None, Field(default=None)] = None) -> dict:
        p = prg.program_with_templates(svc.db, program_id)
        if not p:
            return {"program": None, "message": "No active program."}
        return {"program": p}

    @mcp.tool(
        name="edit_session_template",
        description=(
            "Change one exercise in a session template (soft-deactivates the old "
            "row and keeps history). Actions: swap (replace exercise), modify "
            "(change sets/reps/tempo/…), remove, add, reorder. Always give a "
            "`reason` (stored as a trainer note)."
        ),
        annotations=ToolAnnotations(
            title="Edit Session Template", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def edit_session_template(
        template_id: int,
        action: Annotated[str, Field(pattern="^(swap|modify|remove|add|reorder)$")],
        template_exercise_id: Annotated[int | None, Field(default=None)] = None,
        new_exercise: Annotated[str | None, Field(default=None,
            description="Exercise name or alias.")] = None,
        sets: Annotated[int | None, Field(default=None, ge=1, le=12)] = None,
        rep_min: Annotated[int | None, Field(default=None, ge=1, le=100)] = None,
        rep_max: Annotated[int | None, Field(default=None, ge=1, le=100)] = None,
        target_rir: Annotated[int | None, Field(default=None, ge=0, le=6)] = None,
        rest_s: Annotated[int | None, Field(default=None, ge=15, le=600)] = None,
        tempo: Annotated[str | None, Field(default=None)] = None,
        reason: Annotated[str, Field(min_length=1)] = "user edit",
    ) -> dict:
        with svc.db.write() as c:
            if action in ("swap", "modify", "remove") and template_exercise_id is None:
                raise ToolError(f"{action} requires template_exercise_id")
            if action == "remove":
                c.execute("UPDATE template_exercises SET active=0, deactivated_at=datetime('now') "
                          "WHERE id=?", (template_exercise_id,))
                return {"status": "removed", "template_exercise_id": template_exercise_id,
                         "echo": f"Removed exercise {template_exercise_id}"}
            if action == "swap":
                if not new_exercise:
                    raise ToolError("swap requires new_exercise")
                res = exr.resolve_name(svc.db, new_exercise)
                if not res.exercise_id:
                    return {"status": "needs_resolution",
                             "candidates": res.candidates,
                             "echo": f"Unresolved exercise: {new_exercise}"}
                # Deactivate the old row and insert a new one with same order_no
                row = c.execute("SELECT * FROM template_exercises WHERE id=?",
                                 (template_exercise_id,)).fetchone()
                if not row:
                    raise ToolError("template_exercise_id not found")
                c.execute("UPDATE template_exercises SET active=0, deactivated_at=datetime('now') "
                          "WHERE id=?", (template_exercise_id,))
                cur = c.execute(
                    """INSERT INTO template_exercises(template_id, order_no, exercise_id,
                            sets, rep_min, rep_max, target_rir, rest_s, tempo, role,
                            progression_rule, increment_kg, start_weight_kg, is_optional,
                            notes, active, created_at, replaced_by_id)
                       SELECT template_id, order_no, ?, sets, rep_min, rep_max, target_rir,
                              rest_s, tempo, role, progression_rule, increment_kg,
                              start_weight_kg, is_optional, ?, 1, datetime('now'), NULL
                       FROM template_exercises WHERE id=?""",
                    (res.exercise_id, f"swapped from #{template_exercise_id}: {reason}",
                     template_exercise_id),
                )
                new_id = cur.lastrowid
                c.execute("UPDATE template_exercises SET replaced_by_id=? WHERE id=?",
                          (new_id, template_exercise_id))
                return {"status": "swapped", "old_id": template_exercise_id,
                         "new_id": new_id, "echo": f"Swapped to {new_exercise}: {reason}"}
            if action == "modify":
                updates = {}
                if sets is not None: updates["sets"] = sets
                if rep_min is not None: updates["rep_min"] = rep_min
                if rep_max is not None: updates["rep_max"] = rep_max
                if target_rir is not None: updates["target_rir"] = target_rir
                if rest_s is not None: updates["rest_s"] = rest_s
                if tempo is not None: updates["tempo"] = tempo
                if not updates:
                    raise ToolError("modify requires at least one field")
                sets_sql = ", ".join(f"{k}=:{k}" for k in updates)
                updates["id"] = template_exercise_id
                c.execute(f"UPDATE template_exercises SET {sets_sql} WHERE id=:id", updates)
                return {"status": "modified", "template_exercise_id": template_exercise_id,
                         "changed": list(updates.keys()), "echo": f"Modified: {list(updates.keys())}"}
            raise ToolError(f"unsupported action: {action}")

    @mcp.tool(
        name="set_program_phase",
        description=(
            "Program-level actions: advance_block (start the next block), "
            "start_deload, end_deload, set_next_session (override rotation), "
            "archive (soft), reactivate (undo archive). Deloads are only applied "
            "here — the analysis engine may recommend them via an insight."
        ),
        annotations=ToolAnnotations(
            title="Set Program Phase", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def set_program_phase(
        action: Annotated[str, Field(pattern="^(advance_block|start_deload|end_deload|set_next_session|archive|reactivate)$")],
        program_id: Annotated[int | None, Field(default=None)] = None,
        template_id: Annotated[int | None, Field(default=None)] = None,
        weeks: Annotated[int | None, Field(default=None, ge=1, le=8)] = None,
        reason: Annotated[str, Field(default="user request")] = "user request",
    ) -> dict:
        pid = program_id
        if pid is None:
            p = prg.get_active(svc.db)
            if not p:
                raise ToolError("no active program")
            pid = p["id"]
        with svc.db.write() as c:
            if action == "archive":
                c.execute("UPDATE programs SET status='archived', archived_at=datetime('now'), "
                          "updated_at=datetime('now'), notes=COALESCE(notes,'') || ' | ' || ? "
                          "WHERE id=?", (f"archive: {reason}", pid))
                return {"status": "archived", "program_id": pid, "echo": f"Archived program #{pid}"}
            if action == "reactivate":
                c.execute("UPDATE programs SET status='active', archived_at=NULL, "
                          "updated_at=datetime('now') WHERE id=?", (pid,))
                return {"status": "active", "program_id": pid}
            if action == "start_deload":
                c.execute("UPDATE program_blocks SET status='done', ended_on=date('now') "
                          "WHERE program_id=? AND status='active'", (pid,))
                cur = c.execute(
                    """INSERT INTO program_blocks(program_id, block_no, kind, planned_weeks,
                            volume_multiplier, load_multiplier, rir_offset,
                            status, started_on)
                       VALUES(?, (SELECT COALESCE(MAX(block_no),0)+1 FROM program_blocks WHERE program_id=?),
                              'deload', ?, 0.5, 0.9, 2, 'active', date('now'))""",
                    (pid, pid, weeks or 1),
                )
                return {"status": "deloading", "block_id": cur.lastrowid, "program_id": pid,
                         "echo": f"Started {weeks or 1}-week deload block"}
            if action == "end_deload":
                c.execute("UPDATE program_blocks SET status='done', ended_on=date('now') "
                          "WHERE program_id=? AND status='active' AND kind='deload'", (pid,))
                c.execute(
                    """INSERT INTO program_blocks(program_id, block_no, kind, planned_weeks,
                            volume_multiplier, load_multiplier, rir_offset, status, started_on)
                       VALUES(?, (SELECT COALESCE(MAX(block_no),0)+1 FROM program_blocks WHERE program_id=?),
                              'accumulation', 4, 1.0, 1.0, 0, 'active', date('now'))""",
                    (pid, pid),
                )
                return {"status": "accumulation", "program_id": pid,
                         "echo": "Deload ended; new accumulation block started"}
            if action == "advance_block":
                c.execute("UPDATE program_blocks SET status='done', ended_on=date('now') "
                          "WHERE program_id=? AND status='active'", (pid,))
                cur = c.execute(
                    """INSERT INTO program_blocks(program_id, block_no, kind, planned_weeks,
                            volume_multiplier, load_multiplier, rir_offset, status, started_on)
                       VALUES(?, (SELECT COALESCE(MAX(block_no),0)+1 FROM program_blocks WHERE program_id=?),
                              'accumulation', ?, 1.0, 1.0, 0, 'active', date('now'))""",
                    (pid, pid, weeks or 4),
                )
                return {"status": "advanced", "block_id": cur.lastrowid, "program_id": pid}
            if action == "set_next_session":
                if template_id is None:
                    raise ToolError("set_next_session requires template_id")
                tpl = c.execute("SELECT order_no FROM session_templates WHERE id=? AND program_id=?",
                                 (template_id, pid)).fetchone()
                if not tpl:
                    raise ToolError("template not part of program")
                c.execute("UPDATE programs SET next_template_index=?, updated_at=datetime('now') WHERE id=?",
                          (tpl[0] - 1, pid))
                return {"status": "rotation_set", "next_template_index": tpl[0] - 1}
        raise ToolError(f"unsupported action: {action}")

    @mcp.tool(
        name="list_program_templates",
        description=(
            "List pre-built program templates matching the user's goal, "
            "experience level, days/week and available equipment. Use during "
            "onboarding or when the user asks for a program recommendation. "
            "Returns template slug, name, description, and required equipment."
        ),
        annotations=ToolAnnotations(
            title="List Program Templates", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def list_program_templates(
        goal: Annotated[str | None, Field(default=None)] = None,
        experience: Annotated[str | None, Field(default=None)] = None,
        days_per_week: Annotated[int | None, Field(default=None, ge=1, le=7)] = None,
        equipment: Annotated[list[str] | None, Field(default=None)] = None,
    ) -> dict:
        templates = _load_program_templates()
        filtered = []
        for t in templates:
            if goal and t["goal"] != goal:
                continue
            if experience and experience not in t.get("experience", []):
                continue
            if days_per_week and t["days_per_week"] != days_per_week:
                continue
            if equipment:
                avail = set(equipment)
                required = set(t.get("equipment_required", []))
                if not required.issubset(avail | {"bodyweight"}):
                    continue
            filtered.append({
                "slug": t["slug"],
                "name": t["name"],
                "goal": t["goal"],
                "experience": t.get("experience", []),
                "split_type": t["split_type"],
                "days_per_week": t["days_per_week"],
                "progression_model": t["progression_model"],
                "equipment_required": t.get("equipment_required", []),
                "description": t.get("description", ""),
                "session_count": len(t.get("sessions", [])),
            })
        return {"count": len(filtered), "templates": filtered}

    @mcp.tool(
        name="apply_program_template",
        description=(
            "Instantiate a pre-built program template as the user's active "
            "program. Resolves exercises against the library and respects "
            "profile equipment. Archives the current active program. Use "
            "after list_program_templates shows a match."
        ),
        annotations=ToolAnnotations(
            title="Apply Program Template", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def apply_program_template(
        template_slug: Annotated[str, Field(description="Slug from list_program_templates.")],
        dry_run: Annotated[bool, Field(default=False)] = False,
    ) -> dict:
        templates = _load_program_templates()
        tmpl = next((t for t in templates if t["slug"] == template_slug), None)
        if not tmpl:
            raise ToolError(f"template '{template_slug}' not found")

        unresolved: list[dict] = []
        resolved_sessions = []
        for s in tmpl.get("sessions", []):
            re_exs = []
            for te in s.get("exercises", []):
                res = exr.resolve_name(svc.db, te["exercise"])
                if not res.exercise_id:
                    unresolved.append({"input": te["exercise"], "candidates": res.candidates})
                    continue
                re_exs.append((res.exercise_id, te))
            resolved_sessions.append((s, re_exs))
        if unresolved:
            return {"status": "needs_resolution", "unresolved": unresolved}
        if dry_run:
            return {"status": "ok_dry_run", "template": template_slug,
                     "sessions": len(resolved_sessions)}

        prg.archive_active(svc.db, reason="replaced by apply_program_template")
        pid = prg.create_program(
            svc.db, name=tmpl["name"], goal=tmpl["goal"],
            split_type=tmpl["split_type"], days_per_week=tmpl["days_per_week"],
            progression_model=tmpl["progression_model"],
            block_length_weeks=tmpl.get("block_length_weeks", 4),
            deload_policy={}, rationale=tmpl.get("description"), activate=True,
        )
        for i, (s, te_list) in enumerate(resolved_sessions, start=1):
            tid = prg.add_session_template(
                svc.db, pid, i, name=s["name"], key_name=s.get("key_name"),
                focus=s.get("focus"), target_muscles=s.get("target_muscles", []),
                est_minutes=s.get("est_minutes"),
            )
            for j, (eid, te) in enumerate(te_list, start=1):
                prg.add_template_exercise(
                    svc.db, tid, j, exercise_id=eid, sets=te.get("sets", 3),
                    rep_min=te.get("rep_min", 8), rep_max=te.get("rep_max", 12),
                    target_rir=te.get("target_rir", 2), rest_s=te.get("rest_s", 120),
                    tempo=te.get("tempo"), role=te.get("role", "primary"),
                    progression_rule=te.get("progression_rule"),
                    increment_kg=te.get("increment_kg"),
                    start_weight_kg=te.get("start_weight_kg"),
                    is_optional=te.get("is_optional", False),
                    notes=te.get("notes"),
                )
        return {
            "status": "stored",
            "program_id": pid,
            "template_slug": template_slug,
            "echo": f"Applied template '{tmpl['name']}' with {len(resolved_sessions)} sessions.",
        }


def _load_program_templates() -> list[dict]:
    """Load program templates from the YAML data file."""
    from pathlib import Path

    import yaml
    path = Path(__file__).parent.parent / "data" / "program_templates.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []
