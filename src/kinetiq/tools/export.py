"""export_training_data, import_training_data tools."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db.repos import exercises as exr
from ..db.repos import workouts as wr
from ..services import Services


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="export_training_data",
        description=(
            "Bulk export training data as JSON. Scopes: 'workouts', 'checkins', "
            "'profile', 'all'. Use for backups or moving to another tool."
        ),
        annotations=ToolAnnotations(
            title="Export Data", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def export_training_data(
        scope: Annotated[str, Field(default="all",
            pattern="^(all|workouts|checkins|profile)$")] = "all",
        since: Annotated[str | None, Field(default=None)] = None,
        limit: Annotated[int, Field(default=500, ge=1, le=5000)] = 500,
    ) -> dict:
        out: dict = {"scope": scope, "since": since}
        if scope in ("profile", "all"):
            from ..db.repos.profile import profile_snapshot
            out["profile"] = profile_snapshot(svc.db)
        if scope in ("workouts", "all"):
            args = [limit]
            where = "status <> 'voided'"
            if since:
                where += " AND performed_on >= ?"
                args = [since, limit]
            rows = svc.db.execute(
                f"SELECT * FROM workouts WHERE {where} ORDER BY performed_on DESC LIMIT ?",
                tuple(args),
            ).fetchall()
            workouts = []
            for r in rows:
                w = dict(r)
                w["exercises"] = [dict(x) for x in svc.db.execute(
                    "SELECT * FROM workout_exercises WHERE workout_id=? ORDER BY order_no",
                    (r["id"],)
                ).fetchall()]
                for we in w["exercises"]:
                    we["sets"] = [dict(s) for s in svc.db.execute(
                        "SELECT * FROM sets WHERE workout_exercise_id=? ORDER BY set_no",
                        (we["id"],)
                    ).fetchall()]
                workouts.append(w)
            out["workouts"] = workouts
        if scope in ("checkins", "all"):
            args = [limit]
            where = "1=1"
            if since:
                where += " AND checkin_on >= ?"
                args = [since, limit]
            rows = svc.db.execute(
                f"SELECT * FROM checkins WHERE {where} ORDER BY checkin_on DESC LIMIT ?",
                tuple(args),
            ).fetchall()
            out["checkins"] = [dict(r) for r in rows]
        return out

    @mcp.tool(
        name="import_training_data",
        description=(
            "Import training history from a JSON payload. Supports Kinetiq "
            "export format (round-trip), or a generic format: "
            "`{workouts: [{performed_on, exercises: [{exercise, sets: "
            "[{load_kg, reps, rpe}]}]}]}`. Exercise names are resolved "
            "against the library; unresolved names are returned for "
            "correction. Duplicate dates+exercises are skipped. Use when "
            "the user wants to bring in past data."
        ),
        annotations=ToolAnnotations(
            title="Import Training Data", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def import_training_data(
        workouts: Annotated[list[dict], Field(
            min_length=1,
            description="List of workout dicts with performed_on and exercises.")],
        dry_run: Annotated[bool, Field(default=False)] = False,
    ) -> dict:
        imported = 0
        skipped = 0
        errors: list[dict] = []
        unresolved: list[dict] = []

        for w in workouts:
            date = w.get("performed_on")
            if not date:
                errors.append({"error": "missing performed_on", "workout": w})
                continue

            existing = svc.db.execute(
                "SELECT id FROM workouts WHERE performed_on=? AND status<>'voided'",
                (date,),
            ).fetchone()
            if existing:
                skipped += 1
                continue

            exercises = w.get("exercises", [])
            if not exercises:
                errors.append({"error": "no exercises", "performed_on": date})
                continue

            resolved: list[tuple[int, dict, list[dict]]] = []
            has_unresolved = False
            for ex in exercises:
                name = ex.get("exercise") or ex.get("name") or ""
                res = exr.resolve_name(svc.db, name)
                if not res.exercise_id:
                    unresolved.append({"input": name, "candidates": res.candidates})
                    has_unresolved = True
                    continue
                sets_data = ex.get("sets", [])
                resolved.append((res.exercise_id, ex, sets_data))

            if has_unresolved:
                continue

            if dry_run:
                imported += 1
                continue

            wid = wr.create_workout(
                svc.db, performed_on=date,
                program_id=None, template_id=None, planned_session_id=None,
                block_id=None, status="completed",
                wellness={
                    "energy": w.get("energy"),
                    "fatigue": w.get("fatigue"),
                    "sleep_hours": w.get("sleep_hours"),
                    "session_rpe": w.get("session_rpe"),
                    "bodyweight_kg": w.get("bodyweight_kg"),
                },
                raw_report=None, notes=w.get("notes"),
            )
            for order, (eid, ex, sets_data) in enumerate(resolved, start=1):
                wex_id = wr.add_workout_exercise(
                    svc.db, wid, order_no=order, exercise_id=eid,
                    template_exercise_id=None, was_planned=False, skipped=False,
                    feel=ex.get("feel"), pain_score=ex.get("pain_score"),
                    pain_location=None, form_notes=ex.get("form_notes"),
                    notes=ex.get("notes"),
                )
                for sno, s in enumerate(sets_data, start=1):
                    wr.add_set(
                        svc.db, wex_id, set_no=sno,
                        load_kg=s.get("load_kg") or s.get("weight_kg") or s.get("weight"),
                        added_kg=s.get("added_kg"),
                        assisted_kg=s.get("assisted_kg"),
                        reps=s.get("reps"),
                        duration_s=s.get("duration_s"),
                        distance_m=s.get("distance_m"),
                        rpe=s.get("rpe"),
                        rir=s.get("rir"),
                        side=s.get("side", "both"),
                        is_warmup=bool(s.get("is_warmup")),
                        to_failure=bool(s.get("to_failure")),
                    )
            imported += 1

        result: dict = {
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:20],
        }
        if unresolved:
            result["unresolved"] = unresolved
            result["echo"] = (f"Imported {imported}, skipped {skipped}. "
                               f"{len(unresolved)} exercise names could not be resolved.")
        else:
            result["echo"] = f"Imported {imported} workouts, skipped {skipped} duplicates."
        if dry_run:
            result["status"] = "dry_run"
        return result
