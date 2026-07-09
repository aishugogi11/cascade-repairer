---
name: sdd-roadmap-from-todo
description: Triages raw items from TODO.md into specs/roadmap.md as properly phased, prioritized entries — promote / backlog / drop — without creating any git branch. Use when TODO.md has accumulated unvetted ideas that need to be folded into the roadmap, or as the recurring entry point after a constitution exists. Trigger when the user says "add to roadmap", "triage the TODO", "roadmap from todo", or invokes /sdd-roadmap-from-todo.
---

# Roadmap from TODO

`TODO.md` is the disposable inbox — raw, unvetted, messy on purpose. This skill triages those
items into `specs/roadmap.md` as clean, ordered, phased work. It edits one file (`roadmap.md`)
and creates no branch — branching happens later in `sdd-feature-spec`.

## Before starting

Read for context (do not edit yet):
- `AGENTS.md` — for the project identity (`# Project` section) and for `## Commits` / `## PRs` (who handles commits and merges, including for roadmap-only changes).
- `README.md` — for any project context the user has dumped in.
- The constitution: `specs/mission.md`, `specs/tech-stack.md`, and the current `specs/roadmap.md`.
- `TODO.md` — the items to triage.

This skill assumes a constitution already exists. If `specs/roadmap.md` is missing, stop and tell
the user to create the constitution first (`sdd-constitution-greenfield` or the brownfield variant).

## 1. Interview — BEFORE writing to disk

Use `AskUserQuestion` with **3 grouped questions in one call**, covering:

| Header | Question focus |
|--------|---------------|
| **Items** | Which TODO entries to promote now vs. backlog vs. drop |
| **Priority** | Where promoted items sit relative to existing upcoming phases — what's next in line |
| **Phasing** | How to split promoted items into small, independently shippable phases |

Do **not** edit `roadmap.md` until the user has answered all three.

## 2. Triage each TODO item

Sort every item into exactly one bucket:
- **Promote** — add to `specs/roadmap.md` as a properly phased entry, placed in priority order per
  the interview. These go *next in line* to get done.
- **Backlog** — keep but not now: a backlog section, not the active priority list.
- **Drop** — remove from `TODO.md`.

## 3. Write the roadmap

For each promoted item:
- Add it as a phase entry in priority order, scoped small enough to ship independently.
- Copy the **original TODO text verbatim** into the entry (e.g. under a `> **TODO:** …` blockquote),
  so the developer's raw intent is preserved directly in the roadmap.
- Use the `[x] COMPLETE` heading convention for marking done-ness that the rest of the SDD skills
  rely on (new phases start unmarked).

Keep `roadmap.md` clean and ordered. Update its date/"last updated" line if it has one.

## 4. Hand off

Summarize for the user: what was promoted (and where it landed in priority), what was backlogged,
what was dropped. Stage the `roadmap.md` (and `TODO.md`) changes with `git add` and propose a
commit message — **do not run `git commit`**. Per `AGENTS.md` `## Commits` / `## PRs`, the user
commits and opens the PR, **even for roadmap-only updates on the stable branch**.

## Constraints

- **Do NOT create any git branch.** This skill only updates `roadmap.md` (and trims `TODO.md`).
  Feature branches are created later by `sdd-feature-spec`.
- Do not write feature specs, `plan.md`, `requirements.md`, or `validation.md` — that's `sdd-feature-spec`.
- Do not touch `mission.md` or `tech-stack.md` — constitution edits are `sdd-replan`.
- Promoted phases must be small and independently shippable, consistent with how `sdd-feature-spec`
  consumes them.

## Usage

```
/sdd-roadmap-from-todo
```
