# Validation Report — Repo housekeeping & docs
**Branch:** vb/feature/repo-housekeeping-docs    **Commit:** d526c8f + staged worktree    **Date:** 2026-07-06

## Summary
PARTIAL / FAIL: the automated backend validation passes, dependency removal is verified, the OpenAI Agents SDK skill mirrors are in sync, and most documentation move criteria are satisfied. The fresh-clone walkthrough fails because README and `Makefile` advertise Jupyter at `http://localhost:8020/?token=vb`, but the running Jupyter server is configured with `--IdentityProvider.token=blonter`; following the documented URL lands on the login page instead of Lab.

Validation caveat: while checking whether moved deployment facts appeared in README/specs, one broad `rg` command printed two matching lines from this feature's `plan.md`. Those lines were not used as pass/fail evidence; results below are based on `validation.md`, implementation files, tests, and observed behavior.

## Criterion-by-criterion results
- **Criterion:** Automated 1 — container pytest passes inside the built backend image, including the new `get_weather` test.
- **Status:** PASS
- **Evidence:** `docker compose build backend` exited 0 and produced `vocal-bridge-training-backend:latest`. `docker run --rm vocal-bridge-training-backend python -m pytest tests/ -v` exited 0: 11 passed, 1 warning in 1.49s. Weather tests passing: `tests/test_weather_tool.py::test_weather_for_delano_is_60f`, `test_weather_delano_case_insensitive`, `test_weather_unknown_city_declines`, `test_get_weather_is_a_function_tool`, `test_function_tool_route_registered`.
- **Notes:** The Docker test command required sandbox escalation to access the Colima Docker socket.

- **Criterion:** Automated 2 — removed backend deps are really gone.
- **Status:** PASS
- **Evidence:** `rg -n 'anthropic|langchain' backend/requirements.txt` returned no matches. `rg -n 'import anthropic|from anthropic|import langchain|from langchain' backend -g '*.py'` returned no matches. `backend/requirements.txt` contains FastAPI/OpenAI/GCP/test deps only; no `anthropic`, `langchain-community`, or `langchain-text-splitters`.
- **Notes:** The backend image builds cleanly without those deps.

- **Criterion:** Automated 3 — weather tool assertion is hermetic and imports `api.hello` without credentials.
- **Status:** PASS
- **Evidence:** `backend/api/hello.py` defines `_get_weather` as a plain callable returning `The weather in Delano, MN is sunny and 60°F.` for Delano and wraps it with `function_tool`. `backend/tests/test_weather_tool.py` imports `main`, `_get_weather`, and `get_weather`; pytest passed inside the container without GCP credentials or `OPENAI_API_KEY`.
- **Notes:** The route registration is tested without invoking the OpenAI-backed endpoint.

- **Criterion:** Automated 4 — skill copy is in sync.
- **Status:** PASS
- **Evidence:** `diff -r skills/openai-agents-sdk .claude/skills/openai-agents-sdk` exited 0. `diff -r skills/openai-agents-sdk .agents/skills/openai-agents-sdk` also exited 0.
- **Notes:** I did not run `make copy-skills` because validation should not rewrite generated mirrors; the current mirrors are already identical for this skill.

- **Criterion:** Manual 1 — fresh-clone README walkthrough works: `make up`, backend URL, Jupyter URL, README links.
- **Status:** FAIL
- **Evidence:** `docker compose up --build -d` exited 0; `docker compose ps` showed backend up on `1019` and Jupyter up/healthy on `8020`. `curl -i http://localhost:1019/v1/hello/hello_world` returned `HTTP/1.1 200 OK` with a hello JSON body. `curl -i 'http://localhost:8020/?token=vb'` returned `302 Location: /lab?token=vb`; following redirects returned `200 http://localhost:8020/login?next=%2Flab%3Ftoken%3Dvb`, not an authenticated Lab session. `docker compose logs jupyter` shows the server starts with `--IdentityProvider.token=blonter`. `jupyter_notebook/Dockerfile` also hardcodes `--IdentityProvider.token=blonter`, while README and `Makefile` document `?token=vb`.
- **Notes:** README relative links checked by path existence: `specs/mission.md`, `specs/tech-stack.md`, and `backend/devops/README.md` exist.

- **Criterion:** Manual 2 — `AGENTS.md` is pure working rules and keeps required sections.
- **Status:** PASS
- **Evidence:** `AGENTS.md` contains project context, branch strategy, constitution order, per-feature specs, skills, ideas inbox, and working agreements. It does not contain the dev Cloud Run URL or long project narrative.
- **Notes:** The file is concise and rule-focused.

- **Criterion:** Manual 3 — moved deployment facts were not lost.
- **Status:** PASS
- **Evidence:** README documents the dev Cloud Run URL, `GET /v1/hello/gcp_check`, and Cloud Build PR trigger behavior from `vb/feature/*` into `vb/dev` with direct pushes not building. `AGENTS.md` also retains the branch/trigger rule.
- **Notes:** Facts also remain in `specs/tech-stack.md` and `specs/changelog.md`.

- **Criterion:** Manual 4 — OpenAI Agents SDK skill accuracy.
- **Status:** PASS
- **Evidence:** `skills/openai-agents-sdk/SKILL.md` documents `Agent`, `Runner`, `function_tool`, and `MCPServerStdio` patterns reflected in `backend/api/hello.py`: `Runner.run` used as a classmethod, MCP agents created/run inside `async with`, and `get_weather` / `_get_weather` returning Delano, MN → 60°F.
- **Notes:** The skill is terse and pattern-oriented.

- **Criterion:** Manual 5 — optional live check of `/v1/hello/agents_with_function_tool`.
- **Status:** UNTESTABLE
- **Evidence:** Not run; validation.md marks this optional and says it needs `OPENAI_API_KEY` in the local environment.
- **Notes:** Existing tests cover route registration and the underlying tool function, not the live OpenAI call.

- **Criterion:** Tone check — README teammate-first, quick start visible, no marketing tone, commands copy-pasteable; skill terse and code-oriented.
- **Status:** FAIL
- **Evidence:** README has the quick start in the first screen and the skill is terse. However, one documented command path is not copy-pasteable as written: `http://localhost:8020/?token=vb` does not authenticate because the container uses token `blonter`.
- **Notes:** If the token mismatch is fixed, this likely becomes PASS.

- **Criterion:** Definition of done checklist.
- **Status:** FAIL
- **Evidence:** Automated checks pass; `backend/requirements.txt` removed the named backend deps; README exists; AGENTS is rules-only; `skills/openai-agents-sdk/SKILL.md` exists and mirrors to `.claude`; roadmap marks Phase 2 `[x] COMPLETE`. Manual check 1 fails due the Jupyter token mismatch.
- **Notes:** The roadmap currently says `implementation; manual QA pending`, which matches this validation result.

## Missing tests
- README/Jupyter token consistency has no automated test. Proposed test: `backend/tests/test_validator_docs_contract.py::test_readme_jupyter_token_matches_dockerfile`, asserting the token in README/Makefile matches `--IdentityProvider.token=...` in `jupyter_notebook/Dockerfile`.
- README relative links have no automated test. Proposed test: `backend/tests/test_validator_docs_contract.py::test_readme_relative_links_exist`, parsing README markdown links and asserting local targets exist.
- Skill mirror sync has no automated test. Proposed test: `backend/tests/test_validator_skill_sync.py::test_openai_agents_skill_mirror_matches_source`, comparing `skills/openai-agents-sdk` to `.claude/skills/openai-agents-sdk`.
- AGENTS rules-only shape has no automated test. Proposed test: `backend/tests/test_validator_docs_contract.py::test_agents_md_has_required_sections_and_no_cloud_run_url`, checking required headings and absence of `vocal-bridge-be-dev`.

## Gaps in validation.md
- Should the Jupyter token be standardized to `vb`, or should README/Makefile keep the existing `blonter` token until a separate notebook cleanup phase?
- Should "removed deps are really gone" apply only to `backend/requirements.txt`, or also to `jupyter_notebook/requirements.txt`? The full-stack build still installs `anthropic` from the Jupyter requirements.
- Should validators run `make copy-skills` even though it rewrites generated mirrors, or is a direct `diff -r` acceptable when the mirrors are already present?

## Risks not covered by validation.md
- `backend/api/hello.py` still imports `trace` from `agents` without using it.
- `backend/api/hello.py` root route returns `TESTING TO SEE IF THIS WORKS`; not part of this feature's criteria, but it is still rough user-facing behavior.
- Donor-specific files remain under `backend/promotion_scripts/` and include `blonter` values; roadmap Phase 3 says these will be replaced later, so this is not a Phase 2 failure.
