"""Custom middleware that writes an audit_log row for every tool call."""
from __future__ import annotations
import logging
import time
from typing import Any

from fastmcp.server.middleware import Middleware

from ..db.repos import audit
from ..services import Services

log = logging.getLogger(__name__)


class AuditMiddleware(Middleware):
    def __init__(self, svc: Services) -> None:
        self.svc = svc

    async def on_call_tool(self, context, call_next):
        tool_name = getattr(getattr(context, "message", None), "name", "?")
        args_preview: dict[str, Any] = {}
        try:
            raw = getattr(context.message, "arguments", None)
            if isinstance(raw, dict):
                # Compress non-scalar values to prevent blowout
                for k, v in list(raw.items())[:20]:
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        args_preview[k] = v if not isinstance(v, str) else v[:200]
                    else:
                        args_preview[k] = type(v).__name__
        except Exception:
            pass
        start = time.time()
        ok = True
        error_class: str | None = None
        try:
            return await call_next(context)
        except Exception as e:  # noqa: BLE001
            ok = False
            error_class = type(e).__name__
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            audit.record(
                self.svc.db, tool_name=tool_name, args_preview=args_preview,
                ok=ok, error_class=error_class, duration_ms=duration_ms,
            )
