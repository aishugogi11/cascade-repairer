---
name: sdd-constitution-brownfield
description: Creates a "constitution" for an existing (brownfield) project — a mission statement, tech-stack overview, and phased roadmap — written as markdown files in a specs/ directory. Use when starting work on an existing codebase to clarify goals and plan implementation. Trigger when the user says "create the constitution", "brownfield constitution", "set up specs for this repo", or invokes /sdd-constitution-brownfield.
---

# Constitution for a brownfield project

Goal: produce three files in a `specs/` directory — `mission.md`, `tech-stack.md`, and `roadmap.md` — that capture the project's purpose, technology, and implementation plan.

## 1. Gather context
Read whatever of these exist: `AGENTS.md` (look for a `# Project` section), `README.md`, and `TODO.md`. If they're missing or thin, infer the project's purpose and stack by inspecting the source tree, dependency manifests (e.g. package.json, pyproject.toml), and entry points. Note in the relevant output file when an expected source was missing.

## 2. Interview the user
Before writing any files, use the `AskUserQuestion` tool to ask clarifying questions covering these three areas:
- **Mission** — what problem the project solves and its long-term goal.
- **Target audience** — who uses it and their primary needs.
- **Tech-stack gaps** — known weaknesses, planned migrations, or constraints.

Group these into a single round of questions.

## 3. Write the files
- `mission.md` — mission statement, target audience, and success criteria.
- `tech-stack.md` — current languages, frameworks, services, and infrastructure, plus the gaps surfaced in the interview.
- `roadmap.md` — high-level implementation order derived from `TODO.md` and the interview, broken into small, sequential phases. Keep each phase narrowly scoped. Write phase headings so they can later be marked `[x] COMPLETE` — this is the done-marker the rest of the SDD skills (`sdd-feature-spec`, `sdd-implement-feature`, `sdd-changelog`, etc.) read and write.

Do not write any files until the `AskUserQuestion` answers are received.

## After writing
Stage all three files with `git add` and propose a commit message — **do not run `git commit`**. Per `AGENTS.md` `## Commits` / `## PRs`, the user commits and opens any PR.

## Usage

```
/sdd-constitution-brownfield
```