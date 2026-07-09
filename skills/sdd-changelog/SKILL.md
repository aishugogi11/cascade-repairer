---
name: sdd-changelog
description: Archives completed roadmap phases from specs/roadmap.md into specs/changelog.md, compressed to title, completion date, and a one-sentence outcome with a link back to the spec directory. Use when phases are finished and the roadmap should track only open/upcoming work, or when asked to "update the changelog" / "move completed phases out of the roadmap."
---

# Changelog Skill

Keeps `specs/roadmap.md` focused on open and upcoming work by moving every completed
phase into `specs/changelog.md`. The blow-by-blow task lists stay in each phase's spec
directory and in git history — the changelog is the compressed index of what shipped.

## What counts as "completed"

A phase is completed if its heading carries the `[x] COMPLETE` marker, **including** phases
marked `[x] COMPLETE (implementation; manual QA / stakeholder sign-off pending)`. The header
marker is authoritative — move it regardless of leftover `[ ]` verification checkboxes.

When a moved phase still has open items, do not drop them silently:
- Note the pending state in its one-sentence outcome (e.g. *"implementation complete, manual QA pending"*).
- If a later open phase depends on that sign-off, leave a one-line breadcrumb in the roadmap's priority list pointing to the changelog.

## Process

### Step 1: Read the roadmap

Read `specs/roadmap.md`. Identify every phase heading with the `[x] COMPLETE` marker. List the
spec directories under `specs/` so each completed phase can be matched to its folder.

### Step 2: Confirm the QA-pending judgment call

If any completed phase has open `[ ]` items (manual QA, stakeholder sign-off, operational
TODOs), use `AskUserQuestion` once to confirm handling. Default offered options:
- **Move all COMPLETE phases** — header marker is authoritative; note QA-pending in the outcome.
- **Keep QA-pending in roadmap** — move only fully verified phases.
- **Move, but flag open items** — move all, but carry leftover `[ ]` items into a short "Open follow-ups" list at the top of the roadmap.

Skip the question if every completed phase is fully verified.

### Step 3: Create or update specs/changelog.md

If `specs/changelog.md` does not exist, create it with this header:

```markdown
# <Project> Changelog (for the project name, see `AGENTS.md` # Project section)

Completed roadmap phases, compressed to title, completion date, and outcome. Full
task-level detail lives in each phase's spec directory (linked where one exists) and in
git history. Open and upcoming work stays in [roadmap.md](roadmap.md).

Ordered newest phase first.

---
```

Append one entry per completed phase, **newest phase first** (descending phase number;
place replanning checkpoints in their chronological slot). Entry format:

```markdown
## Phase <N> — <Title>
**Completed:** <date> [· **Spec:** [specs/<dir>/](<dir>/)]

<One sentence describing the outcome — what shipped and why it mattered.>
```

Rules for each entry:
- **Completion date** — use the explicit date if the phase states one ("Completed: 2026-04-30"); otherwise the release it shipped in ("April 2026 (v1.0.8)") or the month. Never invent a precise date; a spec-folder creation date is a proxy, not a completion date.
- **Spec link** — link to `specs/<dir>/` only where a directory exists (paths are relative to the `specs/` folder, so omit the leading `specs/` in the link target). Several phases may share one spec dir (e.g. a batched hotfix); link each to the same folder. If no spec dir exists, omit the link.
- **One sentence** — outcome, not task list. Compress mercilessly; the detail is in the spec dir.

### Step 4: Trim the roadmap

Remove every completed phase block from `specs/roadmap.md`. Keep:
- The title and intro (add a line: *"Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work."*).
- The "Implementation Order" priority list — but strip references to phases now in the changelog and update its date.
- The "Current State" snapshot, "Future Considerations", and "Implementation Notes" sections (orientation, not phases).
- All open / upcoming phase blocks, untouched.

### Step 5: Verify

```bash
cd specs
grep -c "\[x\] COMPLETE" roadmap.md              # expect 0
grep "^## Phase" roadmap.md                      # only open/upcoming phases
grep -c "^## Phase\|^## Replanning" changelog.md  # entry count
```

Confirm no open phase was dropped and no completed phase was left behind.

## Hand off

Stage the changes to `specs/changelog.md` and `specs/roadmap.md` with `git add` and propose a commit message — **do not run `git commit`**. Per `AGENTS.md` `## Commits` / `## PRs`, the user commits and opens the PR (yes, even for changelog/roadmap-only updates on the stable branch).

## Usage
/sdd-changelog

## Output

- `specs/changelog.md` — created or appended, one compressed entry per completed phase. Staged for the user to commit.
- `specs/roadmap.md` — trimmed to open/upcoming phases, pointing at the changelog. Staged for the user to commit.