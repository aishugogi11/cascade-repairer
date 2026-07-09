# Validation — Repo housekeeping & docs (Phase 2)

## Automated

Run from the repo root unless noted.

1. **Container pytest (the CI gate).** Build and test inside the image, mirroring `backend/devops/cloudbuild.yaml`:
   ```bash
   docker compose build backend
   docker run --rm vocal-bridge-training-backend python -m pytest tests/ -v
   ```
   All tests pass, including the new `get_weather` test. (Adjust the image name to whatever `docker compose build` produces locally.)
2. **Removed deps are really gone.** All three assertions hold:
   - `grep -E 'anthropic|langchain' backend/requirements.txt` → no matches.
   - `grep -rE 'import anthropic|from anthropic|import langchain|from langchain' backend --include='*.py'` → no matches.
   - The image builds cleanly without them (covered by step 1's build).
3. **Weather tool assertion.** The new test asserts the underlying weather function returns a 60°F answer for Delano, MN, and imports `api.hello` without `OPENAI_API_KEY` or GCP credentials set (hermetic).
4. **Skill copy is in sync.** After `make copy-skills`: `diff -r skills/openai-agents-sdk .claude/skills/openai-agents-sdk` → no differences.

## Manual

1. **Fresh-clone walkthrough.** Follow README top to bottom as a new teammate: `make up`, hit `http://localhost:1019/v1/hello/hello_world`, open `http://localhost:8020/?token=vb`. Every command works as written; every relative link in the README resolves.
2. **AGENTS.md is pure working rules.** No narrative, no personal story, no GCP URL. Branch strategy, constitution order, per-feature specs, ideas inbox, and working agreements all still present.
3. **Nothing lost in the move.** The dev Cloud Run URL, health-check endpoint, and CI trigger behavior (PR from `vb/feature/*` into `vb/dev`; direct pushes don't build) each appear in README or `specs/`.
4. **Skill accuracy.** Every code pattern in `skills/openai-agents-sdk/SKILL.md` matches working code in `backend/api/hello.py` (imports, `Runner.run` classmethod usage, `async with` MCP rule, `get_weather` → Delano, MN → 60°F).
5. **Optional live check** (needs `OPENAI_API_KEY` in the local env): `GET /v1/hello/agents_with_function_tool` returns an answer containing 60°F for Delano.

## Tone check

- README reads teammate-first: mission in ≤3 sentences before any detail; quick start reachable within the first screen; no marketing adjectives; commands copy-pasteable.
- Skill doc is terse and pattern-oriented, matching `skills/rag/SKILL.md`'s show-the-code style, with gotchas stated as one-liners.

## Definition of done

- [ ] All four automated checks pass.
- [ ] Manual checks 1–4 verified (5 optional).
- [ ] `backend/requirements.txt` no longer lists `anthropic`, `langchain-community`, `langchain-text-splitters`.
- [ ] `README.md` exists at repo root and covers mission, quick start, layout, stack, deployment, background.
- [ ] `AGENTS.md` contains only agent working rules.
- [ ] `skills/openai-agents-sdk/SKILL.md` exists and is mirrored into `.claude/skills/`.
- [ ] Phase 2 marked `[x] COMPLETE` in `specs/roadmap.md`.
