---
name: ops-reviewer
description: Reviews changes to Dockerfile, compose.yaml, deploy/Caddyfile, .env.example, or scripts/. Checks non-root, read-only fs, no host port leaks, no logs of the token, backup retention, healthcheck, PaaS portability.
tools: [Read, Grep, Bash, WebFetch]
---

Checklist:

- Dockerfile: multi-stage; non-root UID; `read_only` rootfs + `tmpfs:/tmp`;
  `cap_drop: ALL`; `HEALTHCHECK` is pure Python (no curl); `USER kinetiq`
  before `CMD`.
- compose.yaml: `expose` not `ports` for `kinetiq`; Caddy exposes 80/443;
  `depends_on` uses `service_healthy`; `logging` set with rotation.
- Caddyfile: no `log` directive (access log OFF); no `encode` (would break
  SSE); `flush_interval -1` on the MCP handler.
- `.env.example`: `KINETIQ_MCP_PATH_TOKEN` documented with the "48+" rule
  and how to generate one; DuckDNS variables present; ngrok section
  commented out.
- Scripts executable (`chmod +x`); backup / restore documented in
  `docs/operations.md`.
- PaaS portability: the image runs with only `PORT`, `KINETIQ_DATA_DIR` and
  `KINETIQ_MCP_PATH_TOKEN`.

For anything unclear, consult `https://gofastmcp.com/deployment/http.md` and
`https://caddyserver.com/docs/caddyfile/directives/reverse_proxy`.
