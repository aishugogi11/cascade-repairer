---
name: sdd-constitution-greenfield
description: Creates a "constitution" for a new (greenfield) project — a mission statement, tech-stack overview with database schema, and phased roadmap — written as markdown files in a specs/ directory. Use as the first step of spec-driven development when starting a project from scratch, before any feature work. Trigger when the user says "create the constitution", "greenfield constitution", "start a new project", "set up specs", or invokes /sdd-constitution-greenfield.
---

# Constitution for a greenfield project

Goal: produce three files in a `specs/` directory — `mission.md`, `tech-stack.md`, and `roadmap.md` — that anchor the project before any code is written. Build them in order, since each depends on the one before it.

## Context
This is the first step of spec-driven development. The repo is new or near-empty, so there is no existing codebase to infer from and no `TODO.md` to derive the roadmap from — the constitution comes from the interview. Read `README.md` and `AGENTS.md` (look for a `# Project` section) if they exist, for any project context the user has already dumped in; otherwise proceed from the interview alone.

You must use the `AskUserQuestion` tool before writing each file. Do not write to disk until you have the answers for that file.

## 1. mission.md
Use the `AskUserQuestion` tool to ask about mission, target audience, and success criteria. Then write `mission.md` covering:
- The problem the project solves and its long-term goal.
- Who uses it and their primary needs.
- What success looks like.

## 2. tech-stack.md
Read `mission.md`, then use the `AskUserQuestion` tool to ask about languages, frameworks, services, infrastructure, and the data model. Then write `tech-stack.md` covering:
- Frontend, backend, and any LLM/AI components, with their frameworks.
- Testing approach, deployment target, and CI/CD.
- The database schema — include the tables and their key fields.

## 3. roadmap.md
Read `mission.md` and `tech-stack.md`, then use the `AskUserQuestion` tool to ask about implementation priorities and sequencing. Then write `roadmap.md` as a high-level implementation order broken into small, sequential phases. Keep each phase narrowly scoped — these become the feature branches in later SDD steps. Write phase headings so they can later be marked `[x] COMPLETE` — this is the done-marker the rest of the SDD skills (`sdd-feature-spec`, `sdd-implement-feature`, `sdd-changelog`, etc.) read and write.

## After writing
Stage all three files with `git add` and propose a commit message — **do not run `git commit`**. Per `AGENTS.md` `## Commits` / `## PRs`, the user commits and opens any PR. Then tell the user to review the git diff and request changes through you (editing the files via this agent) rather than hand-editing, so the constitution stays agent-maintained.

## Usage

```
/sdd-constitution-greenfield
```