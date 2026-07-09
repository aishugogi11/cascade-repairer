# Plan — Repo housekeeping & docs (Phase 2)

Task groups are independently implementable; suggested order puts the code change (with its CI gate) first so docs describe the final state.

## 1. Dependency trim

1.1. Remove `anthropic`, `langchain-community`, `langchain-text-splitters` from `backend/requirements.txt`.
1.2. Re-run the import grep to confirm nothing in `backend/` references the removed packages (`anthropic`, `langchain`).
1.3. Rebuild the backend image and run the CI-equivalent test step: `docker compose build backend`, then run pytest inside the built image (mirrors `backend/devops/cloudbuild.yaml` step `run-pytest`).

## 2. `get_weather` function-tool example in hello.py

2.1. Add a module-level `get_weather(city: str)` function to `backend/api/hello.py` decorated with `@function_tool` (from the `agents` package), returning a hardcoded fictitious result: Delano, MN → 60°F. Keep the plain Python function importable/testable (e.g. define `_get_weather` and wrap it, or use the SDK's pattern for accessing the underlying function).
2.2. Add a `GET /agents_with_function_tool` endpoint that builds an `Agent` with `tools=[get_weather]` (same `gpt-4.1-mini` model and comment style as the existing endpoints) and runs it via `Runner.run`.
2.3. Add a hermetic test in `backend/tests/` asserting the underlying weather function returns the 60°F Delano answer and that the router still imports — no `OPENAI_API_KEY`, no network.

## 3. OpenAI Agents SDK skill

3.1. Author `skills/openai-agents-sdk/SKILL.md` with `name`/`description` frontmatter and these sections, each with a code pattern lifted from (and consistent with) `backend/api/hello.py`:
   - Plain agent, no tools (`/agents_no_mcp` pattern): `Agent` + `Runner.run` classmethod.
   - Function tools: the `@function_tool get_weather` pattern (Delano, MN → 60°F), passing `tools=[...]` to the Agent.
   - MCP stdio servers: in-process Python servers (`mcp-server-fetch` via `python -m`, and the repo's own `backend/mcp_servers/filesystem_server.py`), with the create-and-run-inside-`async with` rule called out.
   - Gotchas: `Runner.run` is a classmethod; `max_turns`; MCP fetch can only retrieve URLs it's given (no search); result is a `RunResult` — return `result.final_output`.
3.2. Run `make copy-skills` so the skill lands in `.claude/skills/` and `.agents/skills/`.

## 4. README

4.1. Create root `README.md` with sections:
   - **What this is** — 3-sentence mission (hackathon, "The Complete Trip", hackathon-ready foundation), link to `specs/mission.md`.
   - **Quick start** — prerequisites (Docker), `make up`, backend at `localhost:1019/v1/hello/hello_world`, Jupyter at `localhost:8020/?token=vb`, useful Makefile targets (`make help`).
   - **Repo layout** — one line each for `backend/`, `jupyter_notebook/`, `specs/`, `skills/`, `about/`, `TODO.md`.
   - **Stack at a glance** — FastAPI + OpenAI Agents SDK, BigQuery/GCS helpers, three voice architectures coming from L2–L5 notebooks; link to `specs/tech-stack.md`.
   - **Deployment** — Cloud Run dev URL, health check endpoint, one paragraph on the PR-to-`vb/dev` Cloud Build trigger; link to `backend/devops/README.md` for provisioning detail.
   - **Background** — the condensed `# About` narrative (hackathon acceptance, course notebooks as reference source, GCP deployment approach).

## 5. AGENTS.md cleanup

5.1. Remove the `# About` narrative, `# Backend GCP URL`, and `# Initial repo structure` sections (now covered by the README).
5.2. Keep and tidy: project context (backend dir), branch strategy, constitution reading order, per-feature specs, ideas inbox, working agreements. Add a one-line pointer to the README for project background.
5.3. Cross-check that nothing removed from AGENTS.md is lost — every load-bearing fact (dev URL, CI trigger behavior) must exist in README or `specs/`.

## 6. Validation & wrap-up

6.1. Work through `validation.md` (automated then manual).
6.2. Mark Phase 2 `[x] COMPLETE` in `specs/roadmap.md`.
