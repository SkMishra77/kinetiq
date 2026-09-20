"""ASGI factory for uvicorn."""
from __future__ import annotations

from .server import create_server
from .settings import Settings


def build_asgi_app(settings: Settings | None = None):
    settings = settings or Settings()
    mcp, _svc = create_server(settings)
    kw: dict = {}
    if settings.host_protection == "strict":
        kw["host_origin_protection"] = True
        kw["allowed_hosts"] = [settings.domain, "localhost", "127.0.0.1"]
    return mcp.http_app(
        path=settings.mcp_url_path() if settings.mcp_path_token else "/mcp",
        stateless_http=settings.stateless_http,
        **kw,
    )


# For `uvicorn kinetiq.app:app`
app = None  # lazily built by cli.serve; keep here as a symbol placeholder
