"""Structured JSON logging with token redaction."""
from __future__ import annotations
import json
import logging
import sys
import time
from collections.abc import Iterable


class RedactingFilter(logging.Filter):
    """Replace every occurrence of any sensitive value in log messages with ``***``."""

    def __init__(self, values: Iterable[str] = ()) -> None:
        super().__init__()
        self.values: list[str] = [v for v in values if v]

    def add(self, value: str) -> None:
        if value and value not in self.values:
            self.values.append(value)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.values:
            return True
        msg = record.getMessage()
        redacted = msg
        for v in self.values:
            redacted = redacted.replace(v, "***")
        if redacted != msg:
            record.msg = redacted
            record.args = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("tool", "duration_ms", "ok", "request_id", "event"):
            v = record.__dict__.get(key)
            if v is not None:
                payload[key] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO", fmt: str = "json", secrets: Iterable[str] = ()) -> RedactingFilter:
    """Install root logger config; return the redacting filter for later additions."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    redactor = RedactingFilter(secrets)
    handler.addFilter(redactor)
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Silence overly chatty libraries.
    for name in ("httpx", "httpcore", "asyncio", "uvicorn.access"):
        logging.getLogger(name).setLevel(max(logging.WARNING, root.level))
    return redactor
