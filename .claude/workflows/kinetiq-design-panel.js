export const meta = {
  name: 'kinetiq-design-panel',
  description: 'Design the Kinetiq MCP trainer server: 3 independent proposals, judged by 3 lenses, synthesized, gap-checked',
  phases: [
    { title: 'Propose', detail: '3 independent designs from different angles' },
    { title: 'Judge', detail: '3 judges score every proposal' },
    { title: 'Synthesize', detail: 'merge winner with best ideas from runners-up' },
    { title: 'Critique', detail: 'completeness check vs requirements and verified API facts' },
  ],
}

const BRIEF = `
# Kinetiq — design brief (read fully before answering)

You are a READ-ONLY design agent working in PLAN MODE. Do NOT create, edit or write any files, do not run package installs, do not change any system state. You MAY read files under /home/ubuntu/Kinetiq and MAY use WebFetch on https://gofastmcp.com/... docs (index at https://gofastmcp.com/llms.txt) to verify API details. Your final output is a design document, not code.

## What the user wants (their words, lightly condensed — treat every bullet as a requirement)
A personal AI fitness/training agent using MCP: an AI trainer with persistent knowledge about the user that acts like a personal gym trainer over a long period.

1. Personal Profile & Context — at first setup the user provides: height, weight, age, fitness level / training experience, primary objective (muscle gain, fat loss, strength, recomposition...), secondary goals, current body measurements, available gym equipment, training schedule / days available, exercise preferences, exercises they cannot or don't want to perform, previous injuries, current physical limitations, other relevant info. Stored persistently in a database and available to the AI whenever it makes training decisions.

2. AI Trainer — behaves like a personal trainer, not a generic Q&A bot. "What should I do today?" must retrieve profile + workout history and determine an appropriate workout: warm-up, exercises, exercise order, sets, reps, suggested weight, rest time, tempo when relevant, cool-down, progression recommendations. Recommendations must be based on previous performance rather than generated independently each day.

3. Workout Logging — after training the user gives a report like:
   Bench Press: 60kg × 8, 60kg × 7, 57.5kg × 8
   Incline Dumbbell Press: 22.5kg × 10 × 3
   Lat Pulldown: 55kg × 10, 55kg × 9, 50kg × 10
   Stored in the DB. Also report: exercise felt easy/hard, pain or discomfort, fatigue, energy level, form issues, missed exercises, body weight changes, sleep/recovery info.

4. Workout Analysis — after a workout is submitted the AI analyzes it and updates training context: progressed vs previous sessions? weight/reps increasing? plateauing exercises? excessive fatigue? recovery issues? changes for the next workout? exercise modification due to discomfort? Analysis stored so future workouts use it.

5. Long-Term Context — the most important part. Never treat a conversation as new. "If I trained chest three days ago, next time I ask for a workout it should retrieve that." Day 1: bench 60kg × 8, 8, 7. Day 4: "What should I do today?" → retrieve history and recommend a progression. The DB becomes a long-term record of the training journey.

6. Science — the trainer must also look up the science behind exercises and which exercise is best for the user's goal (evidence-based selection, with sources).

The user explicitly said: "ask questions if any doubt, don't make assumptions." So: where a design choice is genuinely the user's call and not covered by the decisions below, list it under open_questions instead of silently deciding.

## Decisions already made with the user (FIXED — do not relitigate)
- Deliverable is an MCP SERVER ONLY. The user connects it to claude.ai (web) as a "custom connector" (remote MCP). There is NO CLAUDE.md persona, NO Claude Code subagents, NO custom client at runtime. Claude inside claude.ai is the trainer; the server must carry the trainer behavior via: server instructions (initialize), rich tool descriptions, a start-of-conversation briefing tool, and a ready-to-paste claude.ai Project custom-instructions text. MCP prompts/resources may be added as a bonus but claude.ai's docs only document TOOLS for connectors, so nothing essential may depend on prompts/resources.
- Language: Python 3.12 with uv. Existing repo /home/ubuntu/Kinetiq is EMPTY except a placeholder main.py, a uv-created .venv (Python 3.12.14, only pip installed), and PyCharm .idea. Not a git repo yet.
- Framework: FastMCP 4.x (PyPI "fastmcp", latest 4.0.5, docs gofastmcp.com; built on official mcp SDK 2.x). NOT the bare mcp SDK.
- Database: SQLite, single file under the repo (e.g. data/kinetiq.db), single user.
- Units: metric only (kg, cm).
- Programming model: persistent program + adaptive daily sessions. During onboarding the trainer designs a split (Upper/Lower, PPL, full body, etc.) and progression scheme matched to goal + days available, stores it; "what should I do today" picks the next session in the rotation and adjusts exercises/loads from history, fatigue and pain reports. Blocks/mesocycles and deloads are tracked.
- Exercise library: curated seed of ~120-150 common exercises authored in a data file in the repo: canonical name, aliases ("DB press" → Dumbbell Bench Press), primary/secondary muscles, equipment, movement pattern, evidence notes with citations. New exercises can be added via a tool.
- Science: live evidence tools in the server that query free research APIs directly from Python (PubMed E-utilities, Semantic Scholar Graph API, OpenAlex — network is available from the host) + a cached knowledge base in SQLite (findings per exercise/topic persisted and reused), + a curated seed of training-principles notes with citations (volume, rep ranges by goal, rest intervals, tempo, exercise order, progression models, deload, RPE/RIR, pain/injury modification heuristics). Citations in seed content must be verifiable (the implementation will verify PMIDs via the PubMed tool).
- Auth: NO login. Security by secret URL path: the MCP endpoint path contains a long random token (e.g. /mcp/<48+ random url-safe chars>) loaded from env; any other path → 404. User accepted the URL-as-password tradeoff. Design must still minimize blast radius (no destructive bulk-delete tools without safeguards, backups, rate limiting if cheap).
- Hosting: Docker Compose on this EC2 instance NOW (Ubuntu, public IP 43.205.240.62, region ap-south-1, Docker 29.x + Compose v5.x installed). Ports 5432, 8000, 8080, 7233 are already taken by another project's containers; 80/443 are free. Caddy (containerized, not on host) terminates TLS with automatic Let's Encrypt and reverse-proxies to the server. The public hostname is TBD (user picking among: nip.io IP-derived hostname like 43.205.240.62.nip.io, a free DuckDNS subdomain, or ngrok's free static domain) → treat the hostname as env var KINETIQ_DOMAIN; if ngrok is chosen the Caddy service is replaced by an ngrok container. The user must open 80/443 in the AWS security group manually (no AWS CLI/IAM on the box). The user will move to a PaaS LATER → the Dockerfile must run standalone (PORT env, SQLite on a mounted volume path), and compose must be optional glue.
- Dev tooling: the user ALSO wants a CLAUDE.md and .claude/agents/*.md for developing this repo in Claude Code (this Claude Code runs on AWS Bedrock: WebSearch is unavailable, WebFetch works). Propose which dev subagents are actually useful (e.g. an MCP tool-contract reviewer, an exercise-science content curator that verifies citations via PubMed, a test runner) and what CLAUDE.md should contain (commands, architecture map, conventions, how to run/test/deploy, how to add tools).

## Verified facts about the runtime (from docs fetched today; do not contradict)
claude.ai custom connectors (support.claude.com): available on Free/Pro/Max/Team/Enterprise (Free limited to ONE custom connector); users add via "+" → "Add custom connector" with the remote MCP server URL; connections originate from Anthropic's cloud so the server "must be reachable over the public internet"; OAuth is "typical" (optional client id/secret fields) — unauthenticated servers are not mentioned but are accepted in practice; docs describe only TOOLS ("Remote MCP servers give Claude tools it can invoke during your conversation"); connectors cannot be edited in place ("remove it first, then re-add") so a STABLE URL matters; during Research mode Claude "invokes connector tools automatically without further approval" → write tools should be clearly marked (annotations) and the design should tolerate accidental read calls; connectors are unverified and prompt-injection warnings apply (tool outputs that include fetched web/paper text must be treated as data).

FastMCP 4 API (gofastmcp.com): from fastmcp import FastMCP, Context. FastMCP(name, instructions=..., version=..., lifespan=..., middleware=[...], mask_error_details=..., strict_input_validation=..., cache_ttl=...). Tools: @mcp.tool or @mcp.tool(name=, description=, tags=, annotations=ToolAnnotations(title=, readOnlyHint=, destructiveHint=, idempotentHint=, openWorldHint=), timeout=, output_schema=). Params typed with Annotated[T, Field(description=..., ge=..., le=...)] or Literal/Enum; Pydantic models accepted as JSON objects; validation lenient by default. Returns: dict/dataclass/pydantic → structuredContent + text; str → text; ToolResult(content=..., structured_content=...) for full control. Errors: raise fastmcp.exceptions.ToolError("message") for user-visible messages. Resources: @mcp.resource("kinetiq://profile"); templates @mcp.resource("kinetiq://exercise/{name}"). Prompts: @mcp.prompt. Context param (ctx: Context) gives ctx.info/ctx.report_progress. Health/custom routes: @mcp.custom_route("/health", methods=["GET"]) (never behind auth). Run: mcp.run(transport="http", host="0.0.0.0", port=..., path="/mcp/<token>", stateless_http=True) OR app = mcp.http_app(path=..., stateless_http=True) served by uvicorn (multiple workers require stateless). Host/origin protection opt-in via host_origin_protection=True, allowed_hosts=[...]. Env: FASTMCP_STATELESS_HTTP, FASTMCP_MASK_ERROR_DETAILS. v4 REMOVED ctx.sample()/ctx.sample_step() → the server cannot call an LLM via MCP sampling; analysis must be deterministic Python + Claude's interpretation of returned data. v4 runs on mcp SDK 2.x (protocol models use snake_case field names). Python 3.10+. Testing: pytest + pytest-asyncio (asyncio_mode = "auto"); async with Client(mcp) as client: result = await client.call_tool("name", {...}); result.data / result.structured_content / result.content; list_tools(); in-memory, no network. Reverse proxy needs proxy_buffering off + long read timeouts for SSE streams (Caddy handles streaming by default; set flush_interval -1 if needed).

Research APIs (no key required): PubMed E-utilities esearch.fcgi / esummary.fcgi / efetch.fcgi (XML/JSON; ~3 req/s without API key; optional NCBI_API_KEY env raises limits; abstracts via efetch rettype=abstract). Semantic Scholar Graph API https://api.semanticscholar.org/graph/v1/paper/search?query=...&fields=title,year,abstract,tldr,citationCount,externalIds,openAccessPdf (unauthenticated ~1 req/s shared pool; optional key). OpenAlex https://api.openalex.org/works?search=...&filter=... (polite pool with mailto param). Design for graceful degradation when an API is down/rate-limited, and cache everything in SQLite.

## Success criteria for the design
- Every one of the 6 requirement areas is fully covered by concrete tools + schema + logic.
- The trainer behavior works in claude.ai with ONLY tools: a first-call briefing tool that returns everything Claude needs (profile summary, active program + where in the rotation, last N sessions summary, open insights/flags, pain/injury notes, days since each muscle group, PRs, next-session suggestion inputs) in a compact, LLM-friendly form; tool descriptions that steer Claude to call it first and to log/analyze after workouts.
- Free-text workout reports (as in the example) become structured rows; the parsing is done by Claude (it fills a structured argument) but the tool must be forgiving (aliases, "22.5kg × 10 × 3" expansion, kg/lb strings, bodyweight exercises, RPE/RIR optional, per-set notes) and must return a confirmation echo Claude can show the user.
- Analysis is deterministic and stored: per-exercise progression vs last comparable session (e1RM via Epley/Brzycki, best set, tonnage, reps at same load), PR detection, plateau detection (N sessions without e1RM/volume improvement), fatigue/recovery flags (RPE drift, energy/sleep trends, performance drop), pain flags → modification suggestions, and a stored "next-session plan adjustments" record the planner consumes. Specify formulas, thresholds, and load-increment rules by equipment (e.g. 2.5 kg barbell, 2 kg dumbbell pairs, 1 plate/notch machine) — flag any threshold the user should confirm as an open question.
- Program model: tables for programs/blocks/session templates/template exercises; rotation logic; deload triggers; how history-based suggested loads are computed for each templated exercise.
- Knowledge base: exercise library schema + evidence notes + research cache; tools to search evidence, compare exercises for a goal/muscle, and store curated findings; provenance and dates.
- Deployment: Dockerfile (uv-based, non-root, volume for /data), compose with Caddy (env KINETIQ_DOMAIN, KINETIQ_MCP_PATH_TOKEN), health endpoint, backup script (sqlite3 .backup or VACUUM INTO), logging, restart policy, exact port choice avoiding 5432/8000/8080/7233. PaaS portability notes.
- Tests: pytest in-memory Client tests per tool; fixtures with a temp SQLite DB; golden tests for the parsing and analysis math; a smoke test that runs the HTTP app and hits /health.
- Docs: README (setup, connect to claude.ai step-by-step incl. security-group and hostname steps), docs/claude-project-instructions.md (paste into claude.ai Project), CLAUDE.md, .claude/agents/*.md.
- Repo layout and module boundaries suitable for a Python package (src/kinetiq/...), with the seed data as YAML/JSON files loaded at startup (idempotent upsert), and schema migrations handled simply (versioned SQL files applied at startup).
- Keep total tool count reasonable for an LLM (roughly 15-25 tools), each with a crisp purpose; prefer a few well-designed tools over many tiny ones; prefer richer return payloads over extra round trips.
`

const PROPOSAL_SCHEMA = {
  type: 'object',
  properties: {
    plan_markdown: { type: 'string', description: 'Complete design document in markdown: repo layout, DB schema (tables+columns), tool catalogue (name, params, returns, annotations, description text), analysis engine algorithms with formulas/thresholds, program model, knowledge base + research tools, briefing tool payload design, claude.ai Project instructions draft, deployment, tests, CLAUDE.md + dev agents, risks' },
    key_decisions: { type: 'array', items: { type: 'string' }, description: 'The 10-20 most important design decisions, one line each' },
    open_questions: { type: 'array', items: { type: 'string' }, description: 'Questions only the user can answer; things you would otherwise have to assume' },
  },
  required: ['plan_markdown', 'key_decisions', 'open_questions'],
}

const ANGLES = [
  { key: 'data-analytics', prompt: `YOUR ANGLE: data model and analytics first. Lead with an exact SQLite schema (DDL-level: tables, columns, types, indexes, constraints), the deterministic analysis/progression engine (formulas, thresholds, edge cases like first-ever session, changed rep ranges, unilateral exercises, bodyweight/assisted loads, missed sets), the program/rotation model, and how suggested loads are derived. Then cover tools, briefing payload, deployment, tests, docs and dev agents more briefly but completely.` },
  { key: 'trainer-ux', prompt: `YOUR ANGLE: how Claude in claude.ai will actually behave with only tools. Lead with the conversation flows (onboarding, "what should I do today", logging a report, weekly review, asking about the science of an exercise, changing goals, reporting pain) and design the tool catalogue and the briefing tool payload so each flow needs the fewest calls and Claude reliably calls the right tools first. Write the actual tool description texts and the server instructions text and the claude.ai Project instructions text. Address forgiving input parsing for workout reports. Then cover schema, analysis engine, deployment, tests, docs and dev agents more briefly but completely.` },
  { key: 'ops-security', prompt: `YOUR ANGLE: operations, security and developer experience first. Lead with the Dockerfile, compose (Caddy variant and ngrok variant), env/secrets handling for the secret path token, port choice, health checks, backups/restore, logging, upgrade path, PaaS portability, hardening against accidental data loss (soft deletes, undo of last log, confirmations), rate limiting, handling untrusted text from research APIs (prompt-injection hygiene), the pytest strategy, the CLAUDE.md content and the .claude/agents definitions (which agents, their tools/prompts). Then cover schema, tools, analysis engine, briefing payload and docs more briefly but completely.` },
]

phase('Propose')
const proposals = (await parallel(ANGLES.map(a => () =>
  agent(`${BRIEF}\n\n${a.prompt}\n\nProduce a complete, self-contained design. Be concrete (names, columns, formulas, file paths). Where the brief leaves a real user choice open, put it in open_questions rather than guessing.`, {
    label: `propose:${a.key}`, phase: 'Propose', schema: PROPOSAL_SCHEMA, agentType: 'Plan',
  }).then(p => p && ({ ...p, angle: a.key }))
))).filter(Boolean)
log(`${proposals.length}/3 proposals received`)
if (proposals.length === 0) return { error: 'no proposals' }

const JUDGE_SCHEMA = {
  type: 'object',
  properties: {
    scores: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          angle: { type: 'string' },
          completeness: { type: 'number', description: '0-10 coverage of all 6 requirement areas + fixed decisions' },
          correctness: { type: 'number', description: '0-10 FastMCP/MCP/SQLite/API correctness vs verified facts' },
          claude_ai_practicality: { type: 'number', description: '0-10 will Claude in claude.ai behave as a trainer with these tools' },
          deployment_soundness: { type: 'number', description: '0-10 compose/Caddy/secret path/backups/PaaS portability' },
          total: { type: 'number' },
          strengths: { type: 'array', items: { type: 'string' } },
          weaknesses: { type: 'array', items: { type: 'string' } },
          factual_errors: { type: 'array', items: { type: 'string' }, description: 'Specific claims that contradict the verified facts or are likely wrong' },
        },
        required: ['angle', 'completeness', 'correctness', 'claude_ai_practicality', 'deployment_soundness', 'total', 'strengths', 'weaknesses', 'factual_errors'],
      },
    },
    best_ideas_to_graft: { type: 'array', items: { type: 'string' }, description: 'Ideas from non-winning proposals that the final plan must keep' },
  },
  required: ['scores', 'best_ideas_to_graft'],
}

const LENSES = [
  'an experienced strength & conditioning coach who also builds training software; you judge whether the trainer logic, progression engine, program model and analysis thresholds are physiologically sound and evidence-based, and whether the flows feel like a real coach',
  'a senior Python backend engineer who knows MCP, FastMCP 4 and SQLite deeply; you judge API correctness against the verified facts, schema quality, module boundaries, testability and maintainability; you may WebFetch gofastmcp.com docs to check claims',
  'a security/ops engineer; you judge the deployment (Docker, Caddy, secret path, ports), secret handling, backups, PaaS portability, blast-radius controls, prompt-injection hygiene, and how the claude.ai connector will really behave (stable URL, tools-only surface, Research-mode auto-invocation)',
]

phase('Judge')
const proposalsText = proposals.map(p => `\n\n=============== PROPOSAL "${p.angle}" ===============\n${p.plan_markdown}\n\nKEY DECISIONS:\n- ${p.key_decisions.join('\n- ')}\n\nOPEN QUESTIONS:\n- ${p.open_questions.join('\n- ')}`).join('')
const judgements = (await parallel(LENSES.map((lens, i) => () =>
  agent(`${BRIEF}\n\nYou are JUDGE ${i + 1}: ${lens}.\n\nScore EVERY proposal below on the four criteria (0-10 each, total = sum, max 40). Be harsh and specific; list factual errors verbatim. Then list the best ideas from the non-top proposals that must be grafted into the final plan.${proposalsText}`, {
    label: `judge:${i + 1}`, phase: 'Judge', schema: JUDGE_SCHEMA, agentType: 'Plan',
  })
))).filter(Boolean)

const totals = {}
for (const j of judgements) for (const s of j.scores) totals[s.angle] = (totals[s.angle] || 0) + s.total
const ranked = Object.entries(totals).sort((a, b) => b[1] - a[1])
log(`Ranking: ${ranked.map(([k, v]) => `${k}=${v}`).join(', ')}`)
const winner = proposals.find(p => p.angle === (ranked[0] && ranked[0][0])) || proposals[0]
const grafts = judgements.flatMap(j => j.best_ideas_to_graft)
const allErrors = judgements.flatMap(j => j.scores.flatMap(s => s.factual_errors.map(e => `[${s.angle}] ${e}`)))
const allWeak = judgements.flatMap(j => j.scores.flatMap(s => s.weaknesses.map(e => `[${s.angle}] ${e}`)))

phase('Synthesize')
const synth = await agent(`${BRIEF}\n\nYou are the SYNTHESIZER. Three proposals were judged. The winner is "${winner.angle}". Produce ONE final, authoritative design document that starts from the winner and grafts in the best ideas from the others, fixes every factual error and weakness listed, and keeps the fixed decisions. It must be concrete enough that an engineer can implement it without further design work: exact repo layout, exact DDL, exact tool catalogue (names, parameter models, return shapes, annotations, the description text Claude will see), the briefing payload shape, analysis formulas + thresholds, program/rotation/deload logic, knowledge base + research tool design, Dockerfile/compose/Caddy/env, tests, docs, CLAUDE.md outline, .claude/agents list with purpose. Mark anything the user still has to decide as OPEN QUESTION inline and also list them in open_questions. Keep it scannable (headings, tables, bullets).\n\nBEST IDEAS TO GRAFT:\n- ${grafts.join('\n- ')}\n\nFACTUAL ERRORS TO FIX:\n- ${allErrors.join('\n- ')}\n\nWEAKNESSES TO ADDRESS:\n- ${allWeak.join('\n- ')}${proposalsText}`, {
  label: 'synthesize', phase: 'Synthesize', schema: PROPOSAL_SCHEMA, agentType: 'Plan', effort: 'xhigh',
})
if (!synth) return { error: 'synthesis failed', ranked, judgements }

const CRITIC_SCHEMA = {
  type: 'object',
  properties: {
    gaps: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          requirement: { type: 'string' },
          gap: { type: 'string' },
          fix: { type: 'string' },
          severity: { type: 'string', description: 'blocker | major | minor' },
        },
        required: ['requirement', 'gap', 'fix', 'severity'],
      },
    },
    api_errors: { type: 'array', items: { type: 'string' }, description: 'Claims in the plan that contradict verified FastMCP/claude.ai facts' },
    unjustified_assumptions: { type: 'array', items: { type: 'string' }, description: 'Places where the plan silently decided something the user should be asked' },
    verdict: { type: 'string' },
  },
  required: ['gaps', 'api_errors', 'unjustified_assumptions', 'verdict'],
}

phase('Critique')
const critique = await agent(`${BRIEF}\n\nYou are the COMPLETENESS CRITIC. Check the final design below against EVERY bullet of the 6 requirement areas, every fixed decision, every success criterion, and the verified runtime facts. For each gap say exactly what to add. Flag any silent assumption the user should be asked about (the user insisted: no assumptions). Be exhaustive but only report real gaps.\n\n=============== FINAL DESIGN ===============\n${synth.plan_markdown}\n\nKEY DECISIONS:\n- ${synth.key_decisions.join('\n- ')}\n\nOPEN QUESTIONS ALREADY LISTED:\n- ${synth.open_questions.join('\n- ')}`, {
  label: 'critic', phase: 'Critique', schema: CRITIC_SCHEMA, agentType: 'Plan', effort: 'xhigh',
})

return {
  ranked,
  judge_summaries: judgements.map((j, i) => ({ judge: i + 1, scores: j.scores.map(s => ({ angle: s.angle, total: s.total })) })),
  final_plan_markdown: synth.plan_markdown,
  key_decisions: synth.key_decisions,
  open_questions: synth.open_questions,
  proposal_open_questions: proposals.map(p => ({ angle: p.angle, open_questions: p.open_questions })),
  critique,
}
