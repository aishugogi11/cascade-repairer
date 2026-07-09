---
name: sdd-validation-todo
description: Reads a validation-report.md and triages every finding into a bucketed TODO.md for the primary implementation agent — DECISIONS NEEDED (human answers first), IMPLEMENTATION TASKS, and PROCESS/ENVIRONMENT. Reads and writes only Markdown; writes no code, edits no specs, creates no branch. Run after sdd-validate-feature produces a report. Trigger when the user says "triage the validation report", "validation todo", "turn the report into a TODO", or invokes /sdd-validation-todo.
---

# Validation Report → TODO

Reads a validation report and produces a triaged `TODO.md` the primary implementation agent will
work against. This skill only reads and writes Markdown — it writes no code, edits no specs, and
creates no branch. Run it after `sdd-validate-feature` has produced `validation-report.md`.

## Resolve the config

- **FEATURE_DIR** — the feature directory that was validated, e.g. `specs/YYYY-MM-DD-<feature-name>/`.
- **REPORT** — `FEATURE_DIR/validation-report.md` (the report to triage).
- **TODO_PATH** — where the triaged list is written. Default: repo-root `TODO.md` (the inbox).

Read REPORT and `FEATURE_DIR/validation.md`. You MAY read source code only to confirm a finding.
You write nothing except TODO_PATH.

## Your one job

Convert every finding in the report into exactly one of three buckets, then write TODO_PATH. The
critical rule: **a spec-vs-code conflict is NOT a task — it is a decision the human must make
first.** Never resolve a conflict yourself, and never phrase a conflict as a fix instruction. If
you cannot tell whether a finding is a real gap or a spec disagreement, put it in DECISIONS as a
question.

## The three buckets

1. **DECISIONS NEEDED (human answers first)** — anything where `validation.md` and the
   implementation disagree, anything the report marked AMBIGUOUS, and every item in the report's
   "Gaps in validation.md" section. Phrase each as a yes/no or either/or question, state both
   options with their consequence, and leave a blank `→ DECISION:` line for the human. These block
   the tasks under them.
2. **IMPLEMENTATION TASKS (ready once decisions are made)** — concrete gaps where code or tests are
   missing and the fix is unambiguous (e.g. a named test that doesn't exist, a missing UI element a
   criterion requires). For each: what to add, which file, and the acceptance criterion ID it
   satisfies. If a task depends on a decision, mark it `(blocked by D#)`.
3. **PROCESS / ENVIRONMENT (likely not implementation work)** — git hygiene, spec typos, untracked
   files, and test failures that look environmental rather than behavioral. For any cluster of
   failures, state the suspected single root cause from the report's "Risks" section and mark it
   "diagnose before scheduling" rather than listing each failure as a task.

## What you MUST NOT do

- Do not turn a spec-vs-code conflict into a fix instruction.
- Do not decide contract questions (status codes, inference sources, gate meaning) — those go in DECISIONS.
- Do not write code, edit specs, edit the report, or create a branch.
- Do not instruct the primary agent to "make the report pass." The TODO contains specific,
  criterion-linked work, not "turn everything green."

## Output: write TODO_PATH in this shape

```markdown
# TODO —  (from validation report )

## DECISIONS NEEDED (answer before implementation)
- **D1:** 
  - Option A:  — consequence: 
  - Option B:  — consequence: 
  → DECISION:
- **D2:** …

## IMPLEMENTATION TASKS (ready once decisions made)
- [ ]  — file:  — satisfies:  (blocked by D# if any)
- [ ] …

## PROCESS / ENVIRONMENT (not necessarily code)
- [ ] 
- [ ]  — suspected root cause:  — diagnose before scheduling

## Untestable from this workspace (carry to manual/PR checklist)
- 
```

## Hand-off note

This writes to the same `TODO.md` inbox that `sdd-roadmap-from-todo` later triages into the roadmap.
That loop is intentional — but the **DECISIONS NEEDED** items are not roadmap-ready until the human
fills in their `→ DECISION:` lines. Don't promote unanswered decisions into the roadmap.

## Tone

Terse and specific. "Add EditSaveRoundTripTests asserting edit mode routes to PUT — file:
assessor_iosTests.swift — satisfies V1.3" beats "improve test coverage." After writing TODO_PATH,
print a one-line summary: counts per bucket and the number of unanswered decisions blocking work.

## Usage

```
/sdd-validation-todo
```