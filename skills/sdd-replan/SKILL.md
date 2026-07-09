---
name: sdd-replan
description: Reconciles the constitution (specs/mission.md, specs/tech-stack.md, specs/roadmap.md) with what was learned after a feature shipped — on a dedicated replanning branch. Updates mission/tech-stack if reality has drifted, re-scopes the roadmap, and surfaces the downstream impact on existing specs and code for the user to approve. Use after a feature is complete and merged, before starting the next one. Trigger when the user says "replan", "replanning", "update the constitution", or invokes /sdd-replan.
---

# Replan

Runs after a feature is done. Replanning is the one SDD step that flows *upward*: a shipped
feature may mean the constitution no longer matches reality. This skill reconciles
`specs/mission.md`, `specs/tech-stack.md`, and `specs/roadmap.md` with what you now know, then
surfaces what that implies for existing specs and code — without silently rewriting shipped work.

## Before starting

- Read `AGENTS.md` — specifically `## Branch Strategy` (for the integration and stable branch names + the replanning-branch convention) and `## Commits` / `## PRs` (for who runs commits and merges).
- If the last feature branch is not merged into the stable branch named in `## Branch Strategy` and you are not on that branch with a clean tree, use the `AskUserQuestion` tool to confirm whether to proceed on the current branch instead.
  If there's unfinished or unmerged feature work, stop and tell the user — replan after it lands.
- Create the replanning branch(es) per `AGENTS.md` `## Branch Strategy` (commonly something like `replan/<date>`):
  - **Single-component repo:** one branch in the repo root.
  - **Multi-component repo** (frontend, backend, or several services each with their own convention and possibly their own working dir/git repo): create a matching replanning branch in **each component whose constitution this replan will touch** — use a shared `<date>` slug so the branches correlate. If you're unsure which components are affected, list the impacted components from `## Tech Stack` + the feature you're reconciling and ask the user with `AskUserQuestion` before branching.
  ```
  # single:
  git checkout -b <replanning branch per AGENTS.md ## Branch Strategy>

  # multi-component, repeated per affected component:
  ( cd <component-dir> && git checkout -b <component-specific replanning branch> )
  ```
- Read the full constitution (`specs/mission.md`, `specs/tech-stack.md`, `specs/roadmap.md`) and
  the just-completed feature's spec directory.

## 1. Triage pending TODO.md items

If `TODO.md` has un-triaged items that belong in this replan, run `sdd-roadmap-from-todo` to
promote them into the roadmap before reconciling. Do not duplicate that triage logic here — that
skill owns promote/backlog/drop. If `TODO.md` is empty or already triaged, skip this step.

## 2. Reconcile the constitution with reality

Compare the constitution against what the shipped feature actually established:
- **tech-stack.md** — did the feature introduce a dependency, service, schema change, or pattern
  the document doesn't reflect? Update it (including the database schema tables) to match what
  now exists.
- **mission.md** — did scope, audience, or success criteria shift? Update only if genuinely
  changed; don't churn it for its own sake.
- **roadmap.md** — re-order or re-scope upcoming phases in light of what shipped.

Make these edits on the replanning branch.

## 3. Surface downstream impact — do NOT auto-rewrite shipped work

If a constitution change implies that an existing feature spec or already-shipped code is now
inconsistent (e.g. tech-stack now mandates a pattern the old code doesn't follow), do **not**
silently edit completed specs or rewrite shipped code. Instead, produce a short impact list:
- which existing spec(s) or module(s) the change affects,
- what would need to change,
- whether it's worth a follow-up phase.

Use `AskUserQuestion` to let the user decide per item: fold into an upcoming roadmap phase, open a
new phase, or accept the drift and note it. Only after approval should anything shipped be touched —
and a code change is its own feature, routed back through `sdd-feature-spec`, not done here.

## 4. (Optional) Tests from the updated constitution

If the constitution change introduces new invariants worth guarding (a required pattern, a schema
constraint), propose tests that encode them. Add them only with user agreement.

## 5. Stage and hand off

Stage the replanning changes on the branch (`git add`) and propose a commit message (e.g. `chore(replan): <date> — update tech-stack, re-scope roadmap`) — **do not run `git commit`**. Per `AGENTS.md` `## Commits` / `## PRs`, the user owns commits, PRs, and merges (including replan merges to the stable branch).

Summarize for the user:
- constitution edits and why,
- roadmap changes,
- the downstream-impact decisions still owed,
- any proposed tests,
- the proposed commit message.

## Constraints

- Work on the replanning branch; never edit the constitution directly on the stable branch named in `AGENTS.md` `## Branch Strategy`.
- Never silently rewrite a completed feature spec or shipped code — surface and get approval first.
- Don't churn `mission.md`/`tech-stack.md` for cosmetic reasons; edit only where reality has drifted.
- Roadmap phases stay marked with the `[x] COMPLETE` heading convention the rest of the SDD skills depend on.
- Per `AGENTS.md` `## Commits` / `## PRs`: stage changes, never run `git commit`, never open or merge PRs.

## Usage
/sdd-replan
