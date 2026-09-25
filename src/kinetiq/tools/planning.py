"""plan_next_session tool."""
from __future__ import annotations

import json
from datetime import date as _date
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db.repos import analysis as anal
from ..db.repos import exercises as exr
from ..db.repos import issues as iss
from ..db.repos import programs as prg
from ..domain.dates import parse_date, today
from ..engine.increments import increment_for
from ..engine.planner import TemplateExerciseCtx, plan_session
from ..services import Services


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="plan_next_session",
        description=(
            "Build today's workout from the active program and the user's history. "
            "Returns the next template in the rotation (or `template_id`/`focus` "
            "override) with per-exercise `suggested_load_kg` derived from history "
            "and pending adjustments, `basis` explaining the source, warm-up "
            "with ramp sets on the first compound, cool-down, alternatives for "
            "exercises blocked by active issues, and any warnings. Never invents "
            "loads — if history is missing, returns `mode:'calibrate'` with a "
            "ramp protocol. Use after get_briefing when the user asks 'what "
            "should I do today?' or before every workout."
        ),
        annotations=ToolAnnotations(
            title="Plan Next Session", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def plan_next_session(
        template_id: Annotated[int | None, Field(default=None,
            description="Override the rotation with a specific template id.")] = None,
        session_date: Annotated[str | None, Field(default=None,
            description="ISO date, or 'today' (default) / 'yesterday'.")] = None,
        energy: Annotated[int | None, Field(default=None, ge=1, le=5,
            description="Today's energy 1-5. Optional; if given adjusts load & sets.")] = None,
        sleep_hours: Annotated[float | None, Field(default=None, ge=0, le=16)] = None,
        time_available_min: Annotated[int | None, Field(default=None, ge=10, le=240)] = None,
    ) -> dict:
        program = prg.program_with_templates(svc.db)
        if not program:
            raise ToolError("no active program — call create_program first")
        templates = program["templates"]
        if not templates:
            raise ToolError("active program has no templates")
        if template_id is not None:
            tpl = next((t for t in templates if t["id"] == template_id), None)
            if not tpl:
                raise ToolError("template_id not in active program")
        else:
            idx = (program["next_template_index"] or 0) % len(templates)
            tpl = templates[idx]

        block = program.get("active_block") or {"kind": "accumulation",
                                                 "load_multiplier": 1.0,
                                                 "volume_multiplier": 1.0,
                                                 "rir_offset": 0}
        session_date_iso = parse_date(session_date, svc.settings.timezone).isoformat()

        # Build TemplateExerciseCtx list
        open_iss = iss.open_issues(svc.db)
        avoid_ids: set[int] = set()
        avoid_patterns: set[str] = set()
        load_cap_pct = 1.0
        for i in open_iss:
            r = i.get("restrictions") or {}
            for eid in r.get("avoid_exercise_ids", []) or []:
                avoid_ids.add(int(eid))
            for p in r.get("avoid_patterns", []) or []:
                avoid_patterns.add(p)
            cap = r.get("load_cap_pct")
            if cap and cap < load_cap_pct:
                load_cap_pct = cap

        pending = _pending_map(svc.db)

        ctxs: list[TemplateExerciseCtx] = []
        # profile equipment overrides for increments
        eq_overrides: dict[str, float] = {}
        for row in svc.db.execute("SELECT equipment, increment_kg FROM profile_equipment "
                                    "WHERE increment_kg IS NOT NULL").fetchall():
            eq_overrides[row["equipment"]] = row["increment_kg"]

        for te in tpl["exercises"]:
            eid = te["exercise_id"]
            # last analysis + stats
            stats = svc.db.execute(
                "SELECT last_top_load_kg, last_e1rm_kg, last_performed_on, plateau_count, trend "
                "FROM exercise_stats WHERE exercise_id=?", (eid,)
            ).fetchone()
            last_a = svc.db.execute(
                """SELECT ea.next_load_kg, ea.next_rep_target FROM exercise_analyses ea
                     JOIN session_analyses sa ON sa.id=ea.session_analysis_id
                     JOIN workouts w ON w.id=sa.workout_id
                    WHERE ea.exercise_id=? AND w.status<>'voided'
                    ORDER BY sa.computed_at DESC LIMIT 1""",
                (eid,)
            ).fetchone()
            pending_load = pending.get(eid, {}).get("load")
            pending_pct = pending.get(eid, {}).get("load_pct")
            pending_swap = pending.get(eid, {}).get("swap_to")
            issue_cap = None
            if te["exercise_id"] in avoid_ids or te.get("movement_pattern") in avoid_patterns:
                subs = exr.substitutes_for(svc.db, eid, limit=3)
                if subs:
                    pending_swap = subs[0]["id"]
            if load_cap_pct < 1.0:
                issue_cap = load_cap_pct
            increment = increment_for(te["equipment"], eq_overrides,
                                        te.get("increment_kg") or te.get("ex_default_increment"))
            days_since = None
            if stats and stats["last_performed_on"]:
                try:
                    d = _date.fromisoformat(stats["last_performed_on"])
                    days_since = (today(svc.settings.timezone) - d).days
                except Exception:
                    days_since = None
            subs = exr.substitutes_for(svc.db, eid, limit=3)
            ctxs.append(TemplateExerciseCtx(
                exercise_id=eid, slug=te["exercise_slug"], name=te["exercise_name"],
                movement_pattern=te.get("movement_pattern") or "other",
                equipment=te["equipment"], primary_muscles=te["primary_muscles"],
                sets=te["sets"], rep_min=te["rep_min"], rep_max=te["rep_max"],
                target_rir=(te.get("target_rir") or 2) + int(block.get("rir_offset") or 0),
                rest_s=te.get("rest_s") or 90, tempo=te.get("tempo"),
                role=te.get("role") or "primary",
                is_optional=bool(te.get("is_optional")),
                superset_group=te.get("superset_group"),
                increment_kg=increment,
                template_start_load=te.get("start_weight_kg"),
                last_top_load=stats["last_top_load_kg"] if stats else None,
                last_e1rm=stats["last_e1rm_kg"] if stats else None,
                last_performed_on=stats["last_performed_on"] if stats else None,
                last_analysis_next_load=last_a["next_load_kg"] if last_a else None,
                last_analysis_next_reps=last_a["next_rep_target"] if last_a else None,
                plateau_streak=(stats["plateau_count"] or 0) if stats else 0,
                trend=(stats["trend"] or None) if stats else None,
                pending_adj_load=pending_load,
                pending_adj_load_pct=pending_pct,
                pending_adj_swap_to=pending_swap,
                issue_load_cap_pct=issue_cap,
                substitutes=subs,
            ))

        # Use latest checkin fallback for readiness if energy/sleep not passed
        if energy is None or sleep_hours is None:
            latest = svc.db.execute(
                "SELECT energy, sleep_hours FROM checkins ORDER BY checkin_on DESC LIMIT 1"
            ).fetchone()
            if latest:
                energy = energy or latest["energy"]
                sleep_hours = sleep_hours or latest["sleep_hours"]

        # rough days_since_last across the whole session = min across exercises with history
        history_days = [c.last_performed_on for c in ctxs if c.last_performed_on]
        session_days_since = None
        if history_days:
            recent = max(history_days)
            try:
                session_days_since = (today(svc.settings.timezone) - _date.fromisoformat(recent)).days
            except Exception:
                pass

        plan = plan_session(
            date_iso=session_date_iso,
            template_id=tpl["id"], template_name=tpl["name"], focus=tpl.get("focus"),
            target_muscles=tpl.get("target_muscles") or [],
            block=block,
            exercises=ctxs,
            energy=energy, sleep_hours=sleep_hours,
            days_since_last=session_days_since,
            time_available_min=time_available_min,
        )
        # Persist a planned_sessions row (idempotent per date+template)
        with svc.db.write() as c:
            c.execute("DELETE FROM planned_sessions WHERE planned_on=? AND template_id=?",
                       (session_date_iso, tpl["id"]))
            c.execute(
                """INSERT INTO planned_sessions(planned_on, program_id, template_id, plan_json,
                        readiness_json, created_at)
                   VALUES(?, ?, ?, ?, ?, datetime('now'))""",
                (session_date_iso, program["id"], tpl["id"],
                 json.dumps(_plan_dict(plan)),
                 json.dumps({"energy": energy, "sleep_hours": sleep_hours})),
            )
        return _plan_dict(plan)


def _plan_dict(plan) -> dict:
    return {
        "date": plan.date, "template_id": plan.template_id,
        "template_name": plan.template_name, "focus": plan.focus,
        "target_muscles": plan.target_muscles,
        "block": plan.block,
        "warmup": plan.warmup, "cooldown": plan.cooldown,
        "est_minutes": plan.est_minutes,
        "warnings": plan.warnings, "rationale": plan.rationale,
        "exercises": [{
            "order": pe.order, "exercise": pe.exercise, "exercise_id": pe.exercise_id,
            "slug": pe.slug, "role": pe.role, "sets": pe.sets,
            "rep_range": pe.rep_range, "target_rir": pe.target_rir,
            "rest_s": pe.rest_s, "tempo": pe.tempo,
            "suggested_load_kg": pe.suggested_load_kg, "mode": pe.mode,
            "basis": pe.basis, "notes": pe.notes,
            "last_performance": pe.last_performance,
            "substitutes": pe.substitutes,
            "warmup_ramp": pe.warmup_ramp,
            "superset_group": pe.superset_group,
        } for pe in plan.exercises],
    }


def _pending_map(db) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for a in anal.get_pending_adjustments(db, limit=60):
        eid = a.get("exercise_id")
        if eid is None:
            continue
        v = a.get("value") or {}
        cur = out.setdefault(eid, {})
        if a["adjustment_type"] == "load":
            cur["load"] = v.get("load_kg")
        elif a["adjustment_type"] == "load_pct":
            cur["load_pct"] = v.get("pct")
        elif a["adjustment_type"] == "swap":
            cur["swap_to"] = v.get("substitute_id")
        elif a["adjustment_type"] == "note":
            cur["note"] = v.get("text")
    return out
