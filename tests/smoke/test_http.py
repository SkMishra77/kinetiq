"""ASGI-level smoke: /health and unknown paths."""
import pytest
from httpx import AsyncClient, ASGITransport

from kinetiq.app import build_asgi_app


@pytest.mark.asyncio
async def test_health_route(settings):
    settings.mcp_path_token = "x" * 64
    app = build_asgi_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            r = await c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


@pytest.mark.asyncio
async def test_wrong_path_404(settings):
    settings.mcp_path_token = "x" * 64
    app = build_asgi_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            r = await c.post("/mcp/wrong-token", json={"jsonrpc":"2.0","id":1,"method":"initialize"})
    assert r.status_code == 404
