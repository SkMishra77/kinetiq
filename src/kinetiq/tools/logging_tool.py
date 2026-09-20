"""log_workout, amend_workout, analyze_workout tools."""
from __future__ import annotations
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from mcp.types import ToolAnnotations

from ..services import Services
from ..domain.models import ExerciseEntry, WellnessInput
from ..domain.dates import parse_date
from ..db.repos import exercises as exr
from ..db.repos import workouts as wr
from ..db.repos import analysis as anal
from ..db.repos import programs as prg
from ..db.repos import profile as pr
from ..parsing.sets_shorthand import parse_shorthand
from ..engine.analyzer import (
    analyse_session, ExerciseInput, SetInput,
)


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="log_workout",
        description=(
            "Store a completed workout AND analyse it in one call. Accepts a "
            "list of exercises with either structured `sets` or a raw "
            "`sets_shorthand` string per exercise. Recognised shorthand: "
            "'60kg × 8, 60 × 7, 57.5 × 8' / '22.5kg × 10 × 3' / '3 x 10 @ 22.5' / "
            "'bw × 12' / 'bw+10 × 8' / 'assisted 20 × 5' / '@RPE 8' / 'RIR 2' / "
            "'each' for unilateral / '(warmup) 40 × 8'. Also stores wellness "
            "(energy, fatigue, sleep, bodyweight) and per-exercise pain/feel/form "
            "notes. Ambiguous names are returned in `resolution.unresolved` and "
            "the tool returns status='needs_resolution' without writing — retry "
            "with corrected names or set `allow_new_exercises=true` to create "
            "provisional exercises flagged for later cleanup."
        ),
        annotations=ToolAnnotations(
            title="Log Workout", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def log_workout(
        exercises: Annotated[list[ExerciseEntry], Field(min_length=1,
            description="One entry per exercise in performed order.")],
        performed_on: Annotated[str | None, Field(default=None,
            description="'today' (default), 'yesterday', or ISO date.")] = None,
        template_id: Annotated[int | None, Field(default=None,
            description="Link this workout to a session template (advances rotation).")] = None,
        wellness: WellnessInput | None = None,
        duration_min: Annotated[int | None, Field(default=None, ge=5, le=360)] = None,
        notes: Annotated[str | None, Field(default=None)] = None,
        raw_report: Annotated[str | None, Field(default=None,
            description="Original text the user pasted, kept for audit.")] = None,
        allow_new_exercises: Annotated[bool, Field(default=False,
            description="Create provisional exercises for names that don't resolve.")] = False,
        dry_run: Annotated[bool, Field(default=False,
            description="Parse and preview only; do not write.")] = False,
    ) -> dict:
        date_iso = parse_date(performed_on, svc.settings.timezone).isoformat()

        # Phase 1: resolve every exercise name and parse each entry's sets.
        parsed: list[tuple[ExerciseEntry, int, dict, list[SetInput], list[str]]] = []
        unresolved: list[dict] = []
        for entry in exercises:
            res = exr.resolve_name(svc.db, entry.exercise)
            eid = res.exercise_id
            if not eid:
                if allow_new_exercises:
                    # Provisional: create a stub exercise so logging can succeed
                    created = exr.create_exercise(
                        svc.db, name=entry.exercise, movement_pattern="other",
                        equipment="other", load_type="external",
                        primary_muscles=[], is_compound=True,
                        default_increment_kg=2.5, source="user",
                    )
                    eid = created["id"]
                    exr.add_alias(svc.db, eid, entry.exercise)
                    # Mark as needs_review
                    with svc.db.write() as c:
                        c.execute("UPDATE exercises SET needs_review=1 WHERE id=?", (eid,))
                else:
                    unresolved.append({"input": entry.exercise, "candidates": res.candidates})
                    continue
            ex_row = exr.get_by_id(svc.db, eid)
            sets: list[SetInput] = []
            warnings: list[str] = []
            if entry.sets:
                sets = [SetInput(
                    load_kg=s.load_kg, added_kg=s.added_kg, assisted_kg=s.assisted_kg,
                    reps=s.reps, duration_s=s.duration_s, distance_m=s.distance_m,
                    rpe=s.rpe, rir=s.rir, side=s.side, is_warmup=s.is_warmup,
                    to_failure=s.to_failure, is_bodyweight=s.is_bodyweight,
                ) for s in entry.sets]
            if entry.sets_shorthand:
                try:
                    r = parse_shorthand(entry.sets_shorthand)
                except ValueError as e:
                    raise ToolError(f"could not parse '{entry.exercise}' sets: {e}")
                warnings += r.warnings
                for s in r.sets:
                    sets.append(SetInput(
                        load_kg=s.load_kg, added_kg=s.added_kg, assisted_kg=s.assisted_kg,
                        reps=s.reps, duration_s=s.duration_s, distance_m=s.distance_m,
                        rpe=s.rpe, rir=s.rir, side=s.side, is_warmup=s.is_warmup,
                        to_failure=s.to_failure, is_bodyweight=s.is_bodyweight,
                    ))
            if not sets and entry.status not in ("skipped", "substituted"):
                warnings.append(f"no sets parsed for {entry.exercise}")
            parsed.append((entry, eid, ex_row or {}, sets, warnings))

        if unresolved and not allow_new_exercises:
            return {
                "status": "needs_resolution",
                "unresolved": unresolved,
                "echo": ("Some exercise names could not be resolved. Correct the names "
                         "or call again with allow_new_exercises=true to create "
                         "provisional entries."),
            }

        # If template_id is supplied, look up per-exercise template rows so we can
        # feed rep_min/rep_max/target_rir into the engine (drives correct
        # progression classification).
        template_by_exercise: dict[int, dict] = {}
        if template_id is not None:
            for te in svc.db.execute(
                "SELECT * FROM template_exercises WHERE template_id=? AND active=1",
                (template_id,),
            ).fetchall():
                template_by_exercise[te["exercise_id"]] = dict(te)
        program_row = prg.get_active(svc.db) or {}
        default_prog_rule = program_row.get("progression_model") or "double_progression"

        # Build ExerciseInput list with history for analyzer
        bw_kg = pr.latest_bodyweight(svc.db)
        engine_inputs: list[ExerciseInput] = []
        for entry, eid, ex_row, sets, _w in parsed:
            te = template_by_exercise.get(eid, {})
            prev = wr.previous_exposure(svc.db, eid, before_on=date_iso)
            prev_metrics = wr.summarize_exercise_at(svc.db, prev["wex_id"]) if prev else {}
            prev_pain: list[int] = []
            if prev:
                pp = svc.db.execute(
                    "SELECT pain_score FROM workout_exercises WHERE exercise_id=? "
                    "AND pain_score IS NOT NULL ORDER BY id DESC LIMIT 3",
                    (eid,)
                ).fetchall()
                prev_pain = [r["pain_score"] for r in pp]
            engine_inputs.append(ExerciseInput(
                exercise_id=eid,
                slug=ex_row.get("slug") or "",
                name=ex_row.get("name") or entry.exercise,
                movement_pattern=ex_row.get("movement_pattern") or "other",
                equipment=ex_row.get("equipment") or "other",
                increment_kg=(te.get("increment_kg")
                               or ex_row.get("default_increment_kg") or 2.5),
                laterality=ex_row.get("laterality") or "bilateral",
                load_type=ex_row.get("load_type") or "external",
                bodyweight_load_factor=float(ex_row.get("bodyweight_load_factor") or 1.0),
                sets=sets,
                rep_min=te.get("rep_min"),
                rep_max=te.get("rep_max"),
                target_rir=te.get("target_rir") or 2,
                progression_rule=(te.get("progression_rule") or default_prog_rule),
                template_exercise_id=te.get("id"),
                skipped=(entry.status == "skipped"),
                feel=entry.feel,
                pain_score=entry.pain_score,
                form_notes=entry.form_notes,
                prev_top_load_kg=prev_metrics.get("top_load_kg"),
                prev_best_e1rm_kg=prev_metrics.get("best_e1rm_kg"),
                prev_tonnage_kg=prev_metrics.get("tonnage_kg"),
                prev_avg_rpe=prev_metrics.get("avg_rpe"),
                prev_reps_at_top_load=prev_metrics.get("reps_at_top_load"),
                previous_pain=prev_pain,
                bodyweight_kg=(wellness.bodyweight_kg if wellness and wellness.bodyweight_kg else bw_kg),
            ))

        wellness_dict = wellness.model_dump() if wellness else {}
        out = analyse_session(engine_inputs, session_wellness=wellness_dict)

        if dry_run:
            return {
                "status": "dry_run",
                "would_store": {
                    "performed_on": date_iso,
                    "exercises": [{"exercise": v.name, "sets_summary": _summary(v)}
                                    for v in out.per_exercise],
                },
                "analysis_summary": out.summary,
            }

        # Persist
        wid = wr.create_workout(
            svc.db, performed_on=date_iso,
            program_id=(prg.get_active(svc.db) or {}).get("id"),
            template_id=template_id,
            planned_session_id=None,
            block_id=(prg.get_active(svc.db) or {}).get("active_block", {}).get("id")
                        if prg.get_active(svc.db) else None,
            status="completed", wellness=wellness_dict,
            raw_report=raw_report, notes=notes,
        )
        for i, (entry, eid, ex_row, sets, _w) in enumerate(parsed, start=1):
            wex_id = wr.add_workout_exercise(
                svc.db, wid, order_no=i, exercise_id=eid,
                template_exercise_id=template_by_exercise.get(eid, {}).get("id"),
                was_planned=(template_id is not None),
                skipped=(entry.status == "skipped"),
                feel=entry.feel, pain_score=entry.pain_score,
                pain_location=entry.pain_location,
                form_notes=entry.form_notes, notes=entry.notes,
            )
            # Store sets with computed metrics
            v = next(x for x in out.per_exercise if x.exercise_id == eid)
            v.workout_exercise_id = wex_id
            for cs, sin in zip(v.computed_sets, sets):
                wr.add_set(
                    svc.db, wex_id, set_no=cs.set_no,
                    load_kg=sin.load_kg,
                    added_kg=sin.added_kg,
                    assisted_kg=sin.assisted_kg,
                    reps=sin.reps, duration_s=sin.duration_s,
                    distance_m=sin.distance_m, rpe=sin.rpe, rir=sin.rir,
                    side=sin.side, is_warmup=sin.is_warmup,
                    to_failure=sin.to_failure,
                    effective_load_kg=cs.effective_load_kg,
                    e1rm_kg=cs.e1rm_kg, e1rm_reliable=cs.e1rm_reliable,
                    volume_kg=cs.volume_kg,
                )
        # Persist analysis
        anal.store(svc.db, wid, out)
        # Advance rotation if we linked to a template
        if template_id is not None:
            program = prg.get_active(svc.db)
            if program:
                prg.advance_rotation(svc.db, program["id"])

        return {
            "status": "stored",
            "workout_id": wid,
            "performed_on": date_iso,
            "echo": _echo(out),
            "analysis": {
                "engine_version": out.engine_version,
                "performance_score": out.performance_score,
                "fatigue_score": out.fatigue_score,
                "adherence_pct": out.adherence_pct,
                "summary": out.summary,
                "flags": out.flags,
                "per_exercise": [_verdict_dict(v) for v in out.per_exercise],
            },
        }

    @mcp.tool(
        name="amend_workout",
        description=(
            "Correct or void a single workout. Actions: edit_wellness, edit_notes, "
            "void_session (soft-delete, requires confirm=True). Re-runs analysis "
            "on the edited workout. Always describe the change to the user and "
            "get their agreement before calling with confirm=True."
        ),
        annotations=ToolAnnotations(
            title="Amend Workout", readOnlyHint=False, destructiveHint=True,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def amend_workout(
        workout_id: int,
        action: Annotated[str, Field(pattern="^(edit_wellness|edit_notes|void_session)$")],
        confirm: Annotated[bool, Field(default=False)] = False,
        wellness: WellnessInput | None = None,
        notes: Annotated[str | None, Field(default=None)] = None,
        void_reason: Annotated[str | None, Field(default=None)] = None,
    ) -> dict:
        row = svc.db.execute("SELECT * FROM workouts WHERE id=?", (workout_id,)).fetchone()
        if not row:
            raise ToolError("workout not found")
        if action == "void_session":
            if not confirm:
                raise ToolError("void_session requires confirm=true")
            with svc.db.write() as c:
                c.execute("UPDATE workouts SET status='voided', voided_at=datetime('now'), "
                          "void_reason=?, updated_at=datetime('now') WHERE id=?",
                          (void_reason, workout_id))
            return {"status": "voided", "workout_id": workout_id}
        if action == "edit_notes":
            if notes is None:
                raise ToolError("edit_notes requires notes")
            with svc.db.write() as c:
                c.execute("UPDATE workouts SET notes=?, updated_at=datetime('now') WHERE id=?",
                          (notes, workout_id))
            return {"status": "updated", "workout_id": workout_id}
        if action == "edit_wellness":
            if not wellness:
                raise ToolError("edit_wellness requires wellness")
            w = wellness.model_dump()
            with svc.db.write() as c:
                c.execute(
                    """UPDATE workouts SET
                           session_rpe=COALESCE(?, session_rpe),
                           energy=COALESCE(?, energy),
                           fatigue=COALESCE(?, fatigue),
                           sleep_hours=COALESCE(?, sleep_hours),
                           sleep_quality=COALESCE(?, sleep_quality),
                           stress=COALESCE(?, stress),
                           soreness_level=COALESCE(?, soreness_level),
                           bodyweight_kg=COALESCE(?, bodyweight_kg),
                           updated_at=datetime('now')
                        WHERE id=?""",
                    (w.get("session_rpe"), w.get("energy"), w.get("fatigue"),
                     w.get("sleep_hours"), w.get("sleep_quality"), w.get("stress"),
                     w.get("soreness_level"), w.get("bodyweight_kg"), workout_id),
                )
            return {"status": "updated", "workout_id": workout_id}
        raise ToolError(f"unsupported action: {action}")

    @mcp.tool(
        name="analyze_workout",
        description=(
            "Re-run the deterministic analysis for one workout — useful after "
            "editing sets or when the engine version bumps."
        ),
        annotations=ToolAnnotations(
            title="Analyze Workout", readOnlyHint=False, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def analyze_workout(workout_id: Annotated[int, Field(ge=1)]) -> dict:
        row = svc.db.execute("SELECT * FROM workouts WHERE id=?", (workout_id,)).fetchone()
        if not row:
            raise ToolError("workout not found")
        # Rebuild ExerciseInput list from stored sets/exercises
        wex_rows = svc.db.execute(
            "SELECT * FROM workout_exercises WHERE workout_id=? ORDER BY order_no",
            (workout_id,)
        ).fetchall()
        inputs: list[ExerciseInput] = []
        bw_kg = None
        if row["bodyweight_kg"]:
            bw_kg = row["bodyweight_kg"]
        else:
            bw_kg = pr.latest_bodyweight(svc.db)
        for we in wex_rows:
            ex_row = exr.get_by_id(svc.db, we["exercise_id"]) or {}
            sets = svc.db.execute(
                "SELECT * FROM sets WHERE workout_exercise_id=? ORDER BY set_no",
                (we["id"],)
            ).fetchall()
            prev = wr.previous_exposure(svc.db, we["exercise_id"],
                                         before_on=row["performed_on"])
            prev_metrics = wr.summarize_exercise_at(svc.db, prev["wex_id"]) if prev else {}
            inputs.append(ExerciseInput(
                exercise_id=we["exercise_id"],
                slug=ex_row.get("slug") or "",
                name=ex_row.get("name") or "",
                movement_pattern=ex_row.get("movement_pattern") or "other",
                equipment=ex_row.get("equipment") or "other",
                increment_kg=ex_row.get("default_increment_kg") or 2.5,
                load_type=ex_row.get("load_type") or "external",
                bodyweight_load_factor=float(ex_row.get("bodyweight_load_factor") or 1.0),
                sets=[SetInput(
                    load_kg=s["load_kg"], added_kg=s["added_kg"], assisted_kg=s["assisted_kg"],
                    reps=s["reps"], duration_s=s["duration_s"], distance_m=s["distance_m"],
                    rpe=s["rpe"], rir=s["rir"], side=s["side"] or "both",
                    is_warmup=bool(s["is_warmup"]),
                    to_failure=bool(s["to_failure"]),
                    is_bodyweight=(ex_row.get("load_type") in ("bodyweight", "bodyweight_plus", "assisted")),
                ) for s in sets],
                skipped=bool(we["skipped"]),
                feel=we["feel"], pain_score=we["pain_score"],
                prev_top_load_kg=prev_metrics.get("top_load_kg"),
                prev_best_e1rm_kg=prev_metrics.get("best_e1rm_kg"),
                prev_tonnage_kg=prev_metrics.get("tonnage_kg"),
                prev_avg_rpe=prev_metrics.get("avg_rpe"),
                prev_reps_at_top_load=prev_metrics.get("reps_at_top_load"),
                bodyweight_kg=bw_kg,
            ))
        out = analyse_session(inputs, session_wellness={
            "energy": row["energy"], "fatigue": row["fatigue"],
            "sleep_hours": row["sleep_hours"], "sleep_quality": row["sleep_quality"],
            "soreness_level": row["soreness_level"],
        })
        anal.store(svc.db, workout_id, out)
        return {"workout_id": workout_id, "engine_version": out.engine_version,
                 "summary": out.summary,
                 "per_exercise": [_verdict_dict(v) for v in out.per_exercise]}


def _summary(v) -> str:
    return f"{v.top_load_kg}×{v.reps_at_top_load} · e1RM {v.best_e1rm_kg} · {v.status}"


def _verdict_dict(v) -> dict:
    return {
        "exercise": v.name, "exercise_id": v.exercise_id, "slug": v.slug,
        "status": v.status,
        "top_load_kg": v.top_load_kg, "reps_at_top_load": v.reps_at_top_load,
        "best_e1rm_kg": v.best_e1rm_kg, "delta_e1rm_pct": v.delta_e1rm_pct,
        "tonnage_kg": v.tonnage_kg, "delta_tonnage_pct": v.delta_tonnage_pct,
        "avg_rpe": v.avg_rpe, "rpe_delta": v.rpe_delta,
        "sets_completed": v.sets_completed,
        "next_action": v.next_action, "next_load_kg": v.next_load_kg,
        "next_rep_target": v.next_rep_target,
        "reason": v.reason,
        "prs": v.prs,
        "pain_action": v.pain_action, "pain_reason": v.pain_reason,
    }


def _echo(out) -> list[str]:
    lines = []
    for v in out.per_exercise:
        if v.status == "skipped":
            lines.append(f"{v.name}: skipped")
            continue
        cur = f"{v.name}: "
        cur += f"{v.top_load_kg}×{v.reps_at_top_load}" if v.top_load_kg is not None else "(no working set)"
        if v.best_e1rm_kg:
            cur += f" · e1RM {v.best_e1rm_kg:.1f}"
        if v.delta_e1rm_pct is not None:
            cur += f" ({v.delta_e1rm_pct:+.1f}%)"
        cur += f" · {v.status}"
        if v.next_action != "hold" and v.next_load_kg is not None:
            cur += f" → next {v.next_action.replace('_', ' ')} to {v.next_load_kg}"
        lines.append(cur)
    return lines
