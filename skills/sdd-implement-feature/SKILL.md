---
name: sdd-implement-feature
description: Implements the current feature branch against its spec — working through plan.md task group by task group, validating against validation.md, and marking the phase complete in specs/roadmap.md. Use after a feature spec exists (plan.md, requirements.md, validation.md in a dated specs/ directory) and you're ready to write code. Trigger when the user says "implement the plan", "implement the feature", "build this phase", or invokes /sdd-implement-feature.
---

# Implement Feature

Implements the spec on the current feature branch. Assumes `sdd-feature-spec` has already
run: there is a dated spec directory under `specs/` with `plan.md`, `requirements.md`, and
`validation.md`, and you are on the feature branch for this phase.

## Before starting

Read `AGENTS.md` — specifically `## Branch Strategy` (for the branch(es) you should be on) and `## Commits` / `## PRs` (for who handles commits, merges, and PRs in this repo).

Confirm the working state. If any of these is wrong, stop and tell the user rather than guessing:
- You are on the correct feature branch per `AGENTS.md` `## Branch Strategy`, not the stable branch. (`git branch --show-current`)
- **For multi-component repos** (e.g. `./frontend` + `./backend`, or multiple services, each with its own branch convention and possibly its own git repo): you are on the matching feature branch in **every** component this phase touches. Check each component's working directory; flag any that's on the wrong branch.
- The feature's spec directory exists and contains `plan.md`, `requirements.md`, and `validation.md`.
- The working tree is clean enough to start (no unrelated uncommitted changes) in every affected component.

Read all three spec files, plus `specs/mission.md` and `specs/tech-stack.md`, before writing code.
`plan.md` is the build order; `requirements.md` is the scope and the decisions; `validation.md`
is the bar the work must clear.

## Implement

Work through `plan.md` one numbered task group at a time, in order. For each group:
- Implement its sub-tasks, following the conventions and stack in `specs/tech-stack.md` — no new dependencies without user approval.
- Write the tests the group calls for. Every new file gets at least basic unit-test coverage.
- Per `AGENTS.md` `## Commits`, stage the group as a logical unit (`git add`) and propose a commit message referencing the phase (e.g. `feat(phase-N): <task group>`). **Do not run `git commit`** — the user runs it. For multi-component repos, stage in each affected component's working dir; if the task group spans components, propose one message per component (each prefixed so the user can pair them up, e.g. `feat(ui)(phase-N): …` and `feat(be)(phase-N): …`). Hand off after each group so the user can commit before you start the next one (or batch the hand-off at the end if the user prefers, but keep groups staged separately so the message-per-group structure is preserved).

Do not jump ahead or batch unrelated groups together; the group boundaries in `plan.md`
exist so the work is reviewable and independently revertible by the user.

## Validate

When the plan is implemented, work through `validation.md`:
- Run the automated checks — the project's test and typecheck/lint commands (see `AGENTS.md` ## Commands). They must pass.
- Confirm each automated acceptance criterion has a test that actually asserts it; if one is missing, add it.
- List the manual checks (walkthrough, behaviour, edge cases, tone) for the user to run — these are not yours to mark passed.

If automated checks fail, fix the implementation and re-run. Do not edit `validation.md` to make
it pass; if you believe a criterion is wrong, raise it with the user.

## Mark complete and hand off

Update `specs/roadmap.md` for this phase:
- If every criterion in `validation.md` is satisfied, mark the phase heading `[x] COMPLETE`.
- If the code is done but manual QA / stakeholder sign-off is still outstanding, mark the heading
  `[x] COMPLETE (implementation; manual QA pending)` so `sdd-changelog` archives it correctly.

Stage the roadmap update (don't commit it — see `AGENTS.md` `## Commits`). Then stop and hand back to the user for review with a short summary:
- which task groups were staged and the proposed commit message for each,
- automated check results,
- the manual checks still owed,
- anything that diverged from `plan.md` and why.

Per `AGENTS.md` `## PRs`, leave the PR, merge, and branch deletion entirely to the user.

## If the plan is wrong

If implementation reveals the plan is flawed — a task group can't be built as specified, or scope
was missed — stop and tell the user. Small tweaks: ask whether to adjust in place. Larger gaps:
recommend revising the spec (re-run `sdd-feature-spec` for this phase) rather than improvising a
divergent implementation.

## Constraints

- Stay on the current feature branch (per `AGENTS.md` `## Branch Strategy`); never switch to or stage on the stable branch.
- Per `AGENTS.md` `## Commits` / `## PRs`: stage with `git add`, never run `git commit`, never push, never open or merge PRs. The user owns all of those.
- Respect the tech stack in `specs/tech-stack.md`; no new dependencies without approval.
- Never edit specs (`plan.md`, `requirements.md`, `validation.md`) to make implementation easier — change the code, or raise the spec issue with the user.

## Usage

```
/sdd-implement-feature
```
