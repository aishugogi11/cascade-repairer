---
name: sdd-preflight
description: Pre-flight checklist run between SDD cycles — before picking up the next roadmap item or wrapping up for now. Verifies git state (uncommitted work, unmerged feature branch), surfaces the next roadmap candidate for the user to confirm, and prompts a context clear. Trigger when the user says "preflight", "pre-flight", "am I clear to start the next phase", "post planning", or invokes /sdd-preflight.
---

# Pre-flight

A short gate between features: confirm the last cycle is fully closed before opening the next one.
Some checks the agent can verify; one is the user's judgment; one the agent cannot verify for
itself. Be honest about which is which — don't report a check as passed that you didn't actually run.

Read `AGENTS.md` `## Branch Strategy` first to learn the names of the stable and integration branches in this repo — every check below references "the stable branch" rather than hardcoding `main`. Also read `## Commits` / `## PRs` so you don't suggest the agent perform either. **If `AGENTS.md` defines multiple components** (frontend/backend, or several services, each potentially with its own naming convention and working directory), run every check below in **each** component and report the result per component.

## 1. Unfinished work? (agent verifies)
git status --short
git branch --show-current
Report whether the working tree is clean and which branch you're on. For multi-component repos, run this in each component's working dir and report one line per component. Uncommitted changes or being on a stale feature branch in any component means the last cycle isn't closed — flag it.

## 2. Last feature branch merged into the integration/stable branch? (agent verifies)

Using the branch name(s) from `AGENTS.md` `## Branch Strategy` (call it `<STABLE>`), check whether the most recent feature branch was merged in:
git branch --merged <STABLE>
git log --oneline <STABLE> -5
If a feature branch still exists unmerged, or `<STABLE>` doesn't contain the last feature's commits,
say so. For multi-component repos, run this in each component's working dir — a phase isn't closed until **all** its component branches have merged into their respective stable branches. Per the SDD flow, features merge into the branch named in `## Branch Strategy` (typically via a user-opened PR — see `## PRs`) before the next cycle starts.

## 3. Is the next roadmap item the right thing? (user decides)

Read `specs/roadmap.md` and identify the first phase not marked `[x] COMPLETE` — the candidate
next item. Present it to the user and ask them to confirm it's still the right thing to do now, or
whether priorities shifted (in which case point them to `sdd-roadmap-from-todo` or `sdd-replan`).
This is the user's call, not yours — surface it, don't decide it.

## 4. Context cleared? (agent cannot verify — prompt the user)

An agent can't confirm its own context is clear. Remind the user: if you're about to start the next
feature, clear the agent's context first (`/clear`) so the next cycle starts clean and stays out of
the "dumb zone." State plainly that this is a manual step you can't verify for them.

## Output

A short status line per check: ✅ verified clear / ⚠️ needs attention / ◻️ user action required.
End with a one-line verdict: clear to proceed to the next phase, or the specific thing to resolve first.

## Usage
/sdd-preflight

