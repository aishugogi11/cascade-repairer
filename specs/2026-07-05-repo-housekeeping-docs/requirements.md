# Requirements — Repo housekeeping & docs (Phase 2)

## Scope

Four deliverables, all in scope for this branch (`vb/feature/repo-housekeeping-docs`):

| # | Deliverable | Notes |
|---|-------------|-------|
| 1 | **Create `README.md`** at the repo root | No README exists today — this is a from-scratch write, not a rewrite. Teammate-first: mission in ~3 sentences, then how to run (Docker, Makefile, notebooks), repo layout, deployment/CI overview, pointer to `specs/`. |
| 2 | **Clean up `AGENTS.md`** | The `# About` narrative (hackathon story, deployment intentions, backend GCP URL, initial-repo-structure notes) moves into the README. `AGENTS.md` keeps only agent working rules: branch strategy, constitution reading order, per-feature spec layout, ideas inbox, working agreements. |
| 3 | **Add the OpenAI Agents SDK skill** | `skills/openai-agents-sdk/SKILL.md` documenting the agent-with-tools patterns proven in `backend/api/hello.py`: plain agent, agent + MCP stdio servers (fetch, filesystem), and a `@function_tool` pattern with a fictitious `get_weather` tool (Delano, MN → 60°F). A matching `get_weather` example endpoint is added to `hello.py` so the skill documents working code, not theory. |
| 4 | **Trim `backend/requirements.txt`** | Remove the unused donor dependencies: `anthropic`, `langchain-community`, `langchain-text-splitters`. A repo-wide grep already confirms no backend code imports them. |

### Out of scope

- Any BigQuery schema/table work (Phase 3).
- Sabre, voice architectures, evaluation (Phases 4+).
- Touching `skills/rag/` (it mentions langchain, but it is a doc-only skill, unrelated to backend deps).
- New runtime dependencies of any kind.

## Decisions

- **`# About` narrative → README.** The README becomes the single narrative home (mission summary links to `specs/mission.md` for depth). `AGENTS.md` becomes pure working rules — no story, no URLs beyond what agents need.
- **Skill source of truth is `skills/`, not `.claude/skills/`.** The repo convention (see `Makefile` `copy-skills` target) is: author skills in `skills/<name>/SKILL.md`, then `make copy-skills` mirrors them into `.claude/skills/` and `.agents/skills/`. The new skill follows this — author once in `skills/openai-agents-sdk/`, copy via the existing target. Never hand-edit `.claude/skills/`.
- **Skill format** follows the existing pattern: YAML frontmatter with `name` and `description`, body of runnable patterns with short explanations. Patterns must match `hello.py` exactly (e.g. `Runner.run` is a classmethod; agents using MCP servers must be created and run *inside* the `async with MCPServerStdio(...)` block).
- **`get_weather` lives in `hello.py` too.** The roadmap wants "agent-with-tools patterns from `backend/api/hello.py`" — hello.py currently has MCP patterns but no `@function_tool` example, so a small `/agents_with_function_tool` endpoint is added: a `get_weather(city)` tool that returns a hardcoded 60°F for Delano, MN. The plain tool function is unit-testable without any API key.
- **Dependency trim gated by CI-equivalent test run.** Verification is the containerized pytest run (the exact CI step: `docker run --rm <image> python -m pytest tests/ -v`) plus an import grep. No manual API/notebook smoke-testing required.
- **Teammate-first README tone.** Optimized for a teammate cloning the repo on July 18 under time pressure: what this is (3 sentences), `make up` and you're running, where things live. Operational depth (Cloud Build steps, provisioning) stays in `backend/devops/README.md` and `specs/tech-stack.md` — the README links, it doesn't duplicate.

## Context

- **Tone:** plain, direct, quick-start-first. No marketing language. Commands shown exactly as run (`make up`, ports `backend:1019` / `jupyter:8020`, Jupyter token `vb`).
- **Facts the README must get right** (from `specs/` and the Makefile):
  - Hackathon: DeepLearning.AI Voice AI Hackathon — "The Complete Trip," Sabre + Vocal Bridge, July 18, 2026, Mountain View.
  - Stack: FastAPI backend (Docker), OpenAI Agents SDK (not Anthropic), BigQuery/GCS via config-driven helpers, Cloud Run via Cloud Build (PR from `vb/feature/*` → `vb/dev` fires the trigger; direct pushes do not build).
  - Backend dev URL: `https://vocal-bridge-be-dev-24105435206.us-west1.run.app/` (moves here from AGENTS.md), health check at `GET /v1/hello/gcp_check`.
  - Notebooks: `jupyter_notebook/training_course/` L2–L5 are the reference source.
- **Existing patterns to follow:**
  - Skill layout: `skills/<name>/SKILL.md` with `name`/`description` frontmatter (see `skills/rag/SKILL.md`).
  - Tests: hermetic pytest in `backend/tests/` — no GCP credentials, no `OPENAI_API_KEY` (see `backend/tests/test_gcp_check.py` for the mocking-at-helper-boundary pattern).
  - Comment style in `hello.py`: short, explains constraints (e.g. why the agent runs inside `async with`).
- **Constraint:** `AGENTS.md` working agreements say specs are only modified on explicit instruction — this spec directory itself is authorized by the `/sdd-feature-spec` invocation; the implementation must not touch other `specs/` files except marking the roadmap phase complete at the end.
