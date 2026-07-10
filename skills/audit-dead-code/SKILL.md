---
name: audit-dead-code
description: >
  Audit a Python / FastAPI backend for unreachable and unused code and produce
  an evidence-backed, confidence-tiered report. Combines ruff + vulture +
  deadcode with an AST safety net that suppresses framework false positives
  (route handlers, Pydantic/SQLAlchemy fields, dependency-injected params,
  __all__ exports), plus a cross-stack pass that flags endpoints no client
  calls. Use this whenever the user wants to find dead code, unused functions,
  unreachable branches, orphaned endpoints, or clean up / reduce complexity in a
  Python backend before a release or refactor — even if they don't say the words
  "dead code". READ-ONLY: it reports candidates, it never deletes.
allowed-tools: Bash, Read, Grep, Glob
---

# Audit Dead Code

Find unreachable and unused code in a Python (FastAPI-oriented) backend and
report it with evidence, confidence tiers, and framework false positives already
filtered out.

## Core principle: this is an audit, not a delete

Dead-code detection in Python is formally **undecidable** — dynamic dispatch,
`getattr`, decorator registration, and string-based lookups mean no static tool
can be certain. So every item this skill emits is a **review candidate**, never
an instruction to delete. This skill is read-only by construction: it carries no
code-editing tools and the analyzers run in report mode only. Removal is a
separate, human-gated step. When a user asks to "just remove it all", surface the
report first and let them confirm per item — a confidently-wrong "unused" that
deletes a live route handler is the failure mode to avoid.

## When to use

Trigger on: cleaning up before a release, reducing codebase complexity, finding
unused functions/classes/imports, finding unreachable branches, auditing which
API endpoints are still called after a client change, or any "is this still used?"
question about a Python backend.

## Requirements

The engine wraps three PyPI tools. Install once (all three are optional — the
script degrades gracefully if one is missing, but you want all three):

```bash
pip install ruff vulture deadcode
```

`ruff` gives sound, zero-false-positive import/variable checks; `vulture` adds
unused functions/classes plus **unreachable-code** detection and confidence
scores; `deadcode` provides an independent AST corroboration signal (findings
confirmed by two tools are promoted to high confidence).

Known issue: `deadcode` 2.4.1 (latest as of mid-2026) crashes on Python ≥3.14
because it still uses `ast.Str`, removed in 3.14. Run the audit under Python
3.10–3.13 (e.g. inside the project's container) to get all three engines.

The report header shows per-engine status (`ruff ✓ · vulture ✓ · deadcode ✗`),
so a missing or crashed analyzer is visible instead of silently shrinking
coverage. If **no** analyzer runs at all, the script refuses to emit a report
and exits 2 — zero engines must never look like a clean bill of health.

## Quickstart

Run the orchestrator (from this skill's `scripts/` directory or by absolute path):

```bash
# Audit a whole package (recommended scope — see note below)
python3 scripts/audit_dead_code.py path/to/app

# Add the cross-stack endpoint pass: flag routes no client references
python3 scripts/audit_dead_code.py path/to/app \
  --client-glob "path/to/frontend/**/*.ts" \
  --client-glob "path/to/ios/**/*.swift"

# Machine-readable output for further processing
python3 scripts/audit_dead_code.py path/to/app --format json --output audit.json

# CI gate: exit non-zero if any high-confidence / unreachable items remain
python3 scripts/audit_dead_code.py path/to/app --fail-on high
```

### Always audit whole packages, not single files

vulture and deadcode only see the files you hand them. If you audit
`services/billing.py` alone, a function used only by `services/api.py` will look
dead. Point the tool at the package root (`app/`, `src/`) so cross-module
imports resolve. Auditing a single file is only safe for a leaf module with no
external callers.

## The two passes, and why they're separate

**1. Python pass** (`ruff` + `vulture` + `deadcode`, then AST filtering).
Finds unused functions, classes, imports, variables, and unreachable code.
The AST safety net then drops the framework patterns that fool every linter:

- functions registered by a live decorator (`@app.get`, `@router.post`,
  `@app.websocket`, `@app.on_event`, Celery `@*.task`, etc.) — the framework
  invokes them, so they are never "called" in your source;
- class-level fields of Pydantic `BaseModel` / `BaseSettings`, SQLAlchemy
  declarative bases, `Enum`, and `TypedDict` — those are schema, not dead vars;
- dependency-injected parameters (`= Depends(...)`, `Annotated[X, Depends()]`,
  `Security`, `Header`, `Query`, ...) reported as "unused arguments";
- names re-exported through `__all__`; dunder methods; pytest `test_*`.

**2. Cross-stack endpoint pass** (only with `--client-glob`).
Here's the gap no Python linter can close: a route is *always* "live" to a
linter because a decorator registered it — yet it's dead if nothing calls it.
This pass extracts every FastAPI route via AST, then greps each route's path
(and its stable literal segments, so templated paths like `/users/{id}/posts`
still match) across the client globs you provide — Swift, TypeScript, Go, any
language. Routes with no client reference, excluding infrastructure paths
(`/health`, `/metrics`, `/docs`, ...), are reported as removal candidates.

## Generalizing beyond default FastAPI conventions

Defaults are tuned for FastAPI + Pydantic + SQLAlchemy and work with zero
config. To adapt to another stack or custom decorators, pass `--config
audit.toml` (see `config/audit.example.toml`). You can extend live decorators,
DI markers, schema base classes, ignore-name patterns, infra paths, and excludes:

```toml
[audit_dead_code]
live_decorators = ["*.get", "*.post", "myframework.handler", "*.subscribe"]
schema_bases    = ["BaseModel", "Base", "MyORMBase"]
di_markers      = ["Depends", "Inject", "Provide"]
infra_paths     = ["/health", "/metrics", "/internal"]
```

## Output format

Markdown report with these sections, in this order:

```
# Dead Code Audit Report: <target>
<engine status line: ruff ✓ · vulture ✓ · deadcode ✗ (reason)>
<summary counts + review-candidate disclaimer>
## High confidence — safe to remove (verify no dynamic use)
## Unreachable code — after return/raise/break
## Medium confidence — review needed
## Low confidence — hints only         (only if present)
## Endpoint reachability (vs client code)   (only with --client-glob)
<collapsible: suppressed framework false positives, with reasons>
```

Each finding row carries the item, kind, `file:line`, evidence (the analyzer
message + confidence %), and which tools flagged it.

## Interpreting the tiers

- **High** — flagged by `ruff` (sound), or corroborated by 2+ tools, or vulture
  ≥90%. Safe to remove after a quick check for dynamic/string-based use.
- **Unreachable** — code after `return`/`raise`/`break`/`continue`. Almost
  always safe; occasionally a guard left during debugging.
- **Medium** — single-tool, 60–89% confidence. Read the code before acting.
- **Low** — hints only; expect noise.
- **Endpoint removal candidates** — no client reference found. Confirm the route
  isn't called by a client outside your globs (mobile app, partner integration,
  cron/webhook) before removing.

## Recommended workflow

1. Run the Python pass on the package root; skim the suppressed section once to
   confirm the false-positive filtering matches your conventions (tune
   `--config` if not).
2. Act on **High** and **Unreachable** first — highest signal.
3. If the backend has clients, run the endpoint pass with every client glob you
   can reach; treat candidates as questions, not verdicts.
4. Remove in small, reviewable commits; re-run the audit after — deleting dead
   code often exposes more dead code that was only reachable through it.
