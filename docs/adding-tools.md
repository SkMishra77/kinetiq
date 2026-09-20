# Adding a new MCP tool

## Template

Each tool description follows this shape:

> **Purpose in ≤ 15 words.**
> Call when: `<what user said / state>`
> Returns: `<echo, side effects, structured payload keys>`
> Cautions: `<confirmations, units, date handling>`

Example (`log_workout`):

> Store a completed workout and analyze it against history. Call when the
> user reports what they did. Returns the normalized echo, a resolution report
> and the analysis. Ask about pain details before logging if the user
> mentions discomfort.

## Checklist

- [ ] Model in `domain/models.py` if the input isn't already a primitive.
- [ ] Repo function in `db/repos/*.py` (SQL only).
- [ ] Engine function under `engine/*.py` (pure) for any logic.
- [ ] Register in `tools/<group>.py` with `@mcp.tool(annotations=...)`.
- [ ] Test in `tests/tools/test_<tool>.py` using the in-memory `Client(server)`.
- [ ] Update `EXPECTED_TOOLS` in `tests/tools/test_tool_contracts.py`.
- [ ] If it changes trainer behaviour, update
  `docs/claude-project-instructions.md`.
