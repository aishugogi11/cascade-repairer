---
name: sdd-feature-spec
description: Kicks off a new feature by finding the next incomplete phase in specs/roadmap.md, creating a git branch, interviewing the user about scope/decisions/context, and writing a dated spec directory under specs/ containing plan.md, requirements.md, and validation.md. Trigger when the user says "feature spec", "next phase", "start the next feature", or invokes /sdd-feature-spec.
---

# Feature Spec

## Workflow

### 1. Find the next phase

Read `specs/roadmap.md`. The next phase is the first phase heading not marked `[x] COMPLETE`. Note its name to derive the branch and directory name.

### 2. Create the branch(es)

RULES: MUST ADHERE to the strategy defined in `AGENTS.md` `## Branch Strategy`. Read that section and construct branch names from it — do not invent your own scheme. Branch off the integration branch named there (e.g. `dev`), not the stable branch.

**Multi-component repos.** `AGENTS.md` may define more than one component, service, frontend, or backend — each potentially with its own naming convention and its own working directory or git repo (e.g. `ui/feature/<name>` rooted in `./frontend`, `be/feature/<name>` rooted in `./backend`, plus one per service). When that's the case:

1. Cross-reference `## Branch Strategy` with `## Tech Stack` (and any `## Components` / `## Services` section) to enumerate every component this phase touches. If the phase's scope makes the affected set ambiguous, ask the user with `AskUserQuestion` which components are in scope before creating any branch.
2. For each in-scope component, create a branch using **that component's convention** (e.g. `ui/feature/<phase-slug>` in `./frontend`, `be/feature/<phase-slug>` in `./backend`). Run `git checkout -b` in each component's working directory — they may be separate git repos.
3. Use a single shared `<phase-slug>` across all the branches so they're easy to correlate during review.

**Single-component repos.** If `AGENTS.md` defines only one component (or none, e.g. a docs-only repo), create one branch using that convention; or, if the section is ambiguous about feature-branch naming, ask the user with `AskUserQuestion` before creating it.

```
# one component (or docs):
git checkout -b <branch name per AGENTS.md ## Branch Strategy>

# multi-component, repeated per component in its own working dir:
( cd <component-dir> && git checkout -b <component-specific branch name> )
```

### 3. Interview the user — BEFORE writing any files

Use `AskUserQuestion` with exactly **3 questions in one call**:

| Header | Question focus |
|--------|---------------|
| **Scope** | What the feature collects, exposes, or does — fields, behaviour, data shape |
| **Decisions** | Key implementation choices — storage, visibility, validation, UX pattern |
| **Context** | Tone, constraints, or anything shaping the spec — copy style, stack limits, open questions |

Do **not** write any files until the user has answered all three questions.

### 4. Read guidance files

Read `specs/mission.md` and `specs/tech-stack.md` before drafting.

### 5. Create the spec directory

Name: `specs/YYYY-MM-DD-<feature-name>/` using today's date.

#### `requirements.md`
- Scope section: what is and is not included; field/data table if applicable
- Decisions section: choices made and why (draw from user answers)
- Context section: tone rules, stack pointers, existing patterns to follow

#### `plan.md`
- Numbered task groups appropriate to the feature (for example: Data → Components → Page & Route → Navigation → Tests)
- Each group has numbered sub-tasks; groups should be independently implementable

#### `validation.md`
- Automated: project test and typecheck commands pass; specific assertions required
- Manual: walkthrough, behaviour, edge cases
- Tone check if the feature has user-facing copy
- Definition of done

## Constraints

- Respect the existing tech stack defined in `specs/tech-stack.md` — no new dependencies without user approval
- Follow existing conventions and patterns already established in the codebase
- Keep feature scope focused and independently shippable

## Usage
/sdd-feature-spec