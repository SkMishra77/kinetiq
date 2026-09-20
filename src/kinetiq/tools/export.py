"""export_training_data tool — bulk JSON dump."""
from __future__ import annotations
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field
from mcp.types import ToolAnnotations

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
