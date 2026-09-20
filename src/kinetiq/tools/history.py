"""get_exercise_history, get_training_history, update_insight tools."""
from __future__ import annotations
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from mcp.types import ToolAnnotations

from ..services import Services
from ..db.repos import exercises as exr
from ..db.repos import workouts as wr


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="get_exercise_history",
        description=(
            "Return every session where an exercise was performed: date, sets, "
            "top load, e1RM, tonnage, average RPE, feel/pain, and the analyzer's "
            "verdict. Includes PRs, plateau streak, trend. Use for deep dives, "
            "answering 'what did I do last time', or before deciding to swap."
        ),
        annotations=ToolAnnotations(
            title="Get Exercise History", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def get_exercise_history(
        exercise: Annotated[str, Field(description="Name or alias.")],
        limit: Annotated[int, Field(default=12, ge=1, le=60)] = 12,
    ) -> dict:
        r = exr.resolve_name(svc.db, exercise)
        if not r.exercise_id:
            return {"status": "needs_resolution", "candidates": r.candidates,
                     "echo": f"Unresolved: {exercise}"}
        rows = svc.db.execute(
            """SELECT w.performed_on, w.id AS workout_id, we.id AS wex_id, we.feel, we.pain_score
                 FROM workout_exercises we
                 JOIN workouts w ON w.id=we.workout_id
                WHERE we.exercise_id=? AND w.status<>'voided'
                ORDER BY w.performed_on DESC LIMIT ?""",
            (r.exercise_id, limit)
        ).fetchall()
        history = []
        for row in rows:
            summary = wr.summarize_exercise_at(svc.db, row["wex_id"])
            a = svc.db.execute(
                "SELECT status, next_action, next_load_kg FROM exercise_analyses "
                "WHERE workout_exercise_id=? LIMIT 1",
                (row["wex_id"],)
            ).fetchone()
            history.append({
                "performed_on": row["performed_on"],
                "workout_id": row["workout_id"],
                "feel": row["feel"], "pain_score": row["pain_score"],
                **summary,
                "status": a["status"] if a else None,
                "next_action": a["next_action"] if a else None,
                "next_load_kg": a["next_load_kg"] if a else None,
            })
        stats = svc.db.execute("SELECT * FROM exercise_stats WHERE exercise_id=?",
                                 (r.exercise_id,)).fetchone()
        prs = svc.db.execute(
            "SELECT kind, value, reps, load_kg, achieved_on FROM personal_records "
            "WHERE exercise_id=? ORDER BY achieved_on DESC LIMIT 20",
            (r.exercise_id,)
        ).fetchall()
        return {
            "exercise": {"id": r.exercise_id, "slug": r.slug, "name": r.name},
            "history": history,
            "stats": dict(stats) if stats else None,
            "prs": [dict(p) for p in prs],
        }

    @mcp.tool(
        name="get_training_history",
        description=(
            "List recent workouts (optionally filtered by date range or muscle). "
            "Returns per-session summary, performance & fatigue scores, and total "
            "sessions & PRs in the window. Use for 'how has my week/month been' "
            "questions."
        ),
        annotations=ToolAnnotations(
            title="Get Training History", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def get_training_history(
        since: Annotated[str | None, Field(default=None,
            description="'2026-01-01' or a date; defaults to last 4 weeks.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100)] = 20,
    ) -> dict:
        if since is None:
            since_iso = svc.db.execute("SELECT date('now','-28 days')").fetchone()[0]
        else:
            since_iso = since
        rows = svc.db.execute(
            """SELECT w.id, w.performed_on, w.status, w.duration_min,
                        w.session_rpe, sa.performance_score, sa.fatigue_score, sa.summary
                 FROM workouts w
                 LEFT JOIN session_analyses sa ON sa.workout_id=w.id
                WHERE w.performed_on >= ? AND w.status <> 'voided'
                ORDER BY w.performed_on DESC LIMIT ?""",
            (since_iso, limit)
        ).fetchall()
        pr_count = svc.db.execute(
            "SELECT count(*) FROM personal_records WHERE achieved_on >= ?", (since_iso,)
        ).fetchone()[0]
        return {
            "since": since_iso,
            "sessions": [dict(r) for r in rows],
            "session_count": len(rows),
            "prs_in_window": pr_count,
        }

    @mcp.tool(
        name="update_insight",
        description=(
            "Acknowledge, resolve or dismiss an analysis flag (plateau, fatigue, "
            "pain, adherence...). Dismissing an insight also cancels any linked "
            "adjustment. Keeps the briefing focused on open items."
        ),
        annotations=ToolAnnotations(
            title="Update Insight", readOnlyHint=False, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def update_insight(
        insight_id: int,
        status: Annotated[str, Field(pattern="^(acknowledged|resolved|dismissed)$")],
        resolution: Annotated[str | None, Field(default=None)] = None,
    ) -> dict:
        with svc.db.write() as c:
            c.execute(
                "UPDATE insights SET status=?, resolved_at=CASE WHEN ? IN ('resolved','dismissed') "
                "THEN datetime('now') ELSE resolved_at END, resolution=? WHERE id=?",
                (status, status, resolution, insight_id),
            )
        return {"insight_id": insight_id, "status": status}
