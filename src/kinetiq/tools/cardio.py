"""log_cardio, get_cardio_history tools."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db.repos import cardio as cr
from ..domain.dates import parse_date
from ..services import Services


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="log_cardio",
        description=(
            "Log a cardio or conditioning session (running, cycling, rowing, "
            "swimming, walking, HIIT, etc.). Use when the user reports "
            "non-resistance activity. Stores duration, distance, heart rate, "
            "zone and intensity."
        ),
        annotations=ToolAnnotations(
            title="Log Cardio", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def log_cardio(
        activity: Annotated[str, Field(
            pattern="^(run|bike|row|swim|walk|hiit|elliptical|stair_climb|jump_rope|other)$",
            description="Activity type.")],
        performed_on: Annotated[str | None, Field(default=None,
            description="'today' (default), 'yesterday', or ISO date.")] = None,
        duration_min: Annotated[int | None, Field(default=None, ge=1, le=600)] = None,
        distance_km: Annotated[float | None, Field(default=None, ge=0)] = None,
        avg_hr: Annotated[int | None, Field(default=None, ge=30, le=220)] = None,
        max_hr: Annotated[int | None, Field(default=None, ge=30, le=250)] = None,
        zone: Annotated[str | None, Field(default=None,
            pattern="^(zone1|zone2|zone3|zone4|zone5)$")] = None,
        intensity: Annotated[str | None, Field(default=None,
            pattern="^(easy|moderate|hard)$")] = None,
        calories_est: Annotated[int | None, Field(default=None, ge=0)] = None,
        notes: Annotated[str | None, Field(default=None)] = None,
    ) -> dict:
        date_iso = parse_date(performed_on, svc.settings.timezone).isoformat()
        cid = cr.log_cardio(
            svc.db, performed_on=date_iso, activity=activity,
            duration_min=duration_min, distance_km=distance_km,
            avg_hr=avg_hr, max_hr=max_hr, zone=zone,
            intensity=intensity, calories_est=calories_est, notes=notes,
        )
        echo_parts = [f"{activity} on {date_iso}"]
        if duration_min:
            echo_parts.append(f"{duration_min} min")
        if distance_km:
            echo_parts.append(f"{distance_km} km")
        if intensity:
            echo_parts.append(intensity)
        return {
            "cardio_id": cid,
            "performed_on": date_iso,
            "echo": "Logged cardio: " + " · ".join(echo_parts),
        }

    @mcp.tool(
        name="get_cardio_history",
        description=(
            "Return recent cardio/conditioning sessions. Use when the user "
            "asks 'how much cardio have I done' or 'show my running log'. "
            "Includes a weekly summary."
        ),
        annotations=ToolAnnotations(
            title="Get Cardio History", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def get_cardio_history(
        since: Annotated[str | None, Field(default=None,
            description="ISO date; defaults to last 4 weeks.")] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=100)] = 20,
    ) -> dict:
        sessions = cr.cardio_history(svc.db, since=since, limit=limit)
        weekly = cr.weekly_cardio_summary(svc.db)
        return {
            "sessions": sessions,
            "weekly_summary": weekly,
        }
