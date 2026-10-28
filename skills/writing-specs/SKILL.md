---
name: writing-specs
description: Use on the ai-sdlc feat L/XL route after brainstorming, and on the feat/enh M route, to write the task's spec - docs/specs/<YYYY-MM-DD-topic>/spec.md with Type/Size/Status, scope and numbered EARS acceptance criteria (L/XL), or the spec-lite with current/target behavior, criteria, code paths, tests and its own Tasks section (M). Not for S, fix, refactor, tech, test-only or docs-only work.
---

# Writing specs

The spec is the source of truth for **what** we build and **why**, and the document the user approves. There is no plan document: on L/XL the architect adds the **how** as a `## Design` section of this same file and the tasks go to `tasks.md` next to it (`writing-tasks`); on M the spec-lite carries its own `## Tasks`.

Write it in the main conversation: on L/XL after `superpowers:brainstorming` (its result goes here, not into a separate Superpowers design doc, and nothing is handed to `writing-plans`), on M after brainstorming-lite if one ran.

## Where it lives
One folder per task: `docs/specs/<YYYY-MM-DD-topic>/spec.md`. `tasks.md` and the research notes (`research.md`, `api-research.md`) go into the same folder. Commit the folder with the work.

## Header (both variants)
The first lines, read by the review gate:
```markdown
**Type:** feat | enh
**Size:** M | L | XL
**Status:** Draft | Approved (<who>, <date>)
```

## Spec (feat L/XL)
```markdown
# <Feature>

## Purpose
The problem and why it matters, one paragraph.

## Scope
**In:** what this task delivers.
**Out:** what it deliberately leaves out (name it).

## Acceptance criteria (EARS)
- AC1. WHEN <trigger> [WHILE <state>], THE SYSTEM SHALL <response>.
- AC2. IF <condition>, THEN THE SYSTEM SHALL <response>.

## Constraints
Tech, performance, security/PII, compatibility, rollout, deadlines.

## Open questions
Each with a recommendation; settle them before the design.
```
- **In:** purpose, scope, criteria, constraints, open questions. **Out:** architecture, files, patterns, tasks, code — the architect's `## Design` and `tasks.md` hold those. A snippet that pins a requirement more precisely than prose (a state machine, a schema shape) may sit next to its criterion.
- The architect later appends `## Design` (chosen option, structure per zoom level, interfaces, test seams, fitness function, ADR link); options and research stay in `research.md` and are linked from it. Don't write that section yourself.

## Spec-lite (feat/enh M)
```markdown
# <Change>

## Current behavior
What the touched code does today, with `path:line`.

## Target behavior
What it does after the change.

## Acceptance criteria (EARS)
- AC1. WHEN <trigger>, THE SYSTEM SHALL <response>.

## Code paths
The files/units to change, and the existing pattern followed.

## Tests
The current-behavior tests to pin first, then the new tests per criterion.

## Tasks
- [ ] 1. <task> (covers: AC1)
- [ ] 2. <task> (covers: AC2, depends on: 1)
```
No `tasks.md` and no plan for M. When the architect is dispatched on M (new abstraction), it adds a short `## Design` above `## Tasks`.

## Acceptance criteria are the contract
- Numbered `AC1…` so tasks, tests, the implementer's report and `acceptance-checker` refer to them by id.
- Each one testable: a trigger and an observable response. "Works well" or "is fast" without a number is a defect.
- A criterion with no task is a gap; a task with no criterion is scope creep.

## Handoff
- **L/XL:** show the spec → ✋ the user's "ok" (set `Status: Approved`) → `architect` writes `## Design` → `writing-tasks` writes `tasks.md` → one ✋ on design + tasks → `feature-implementer`.
- **M:** show the spec-lite → ✋ → [`architect`, if a new abstraction] → `feature-implementer` runs its `## Tasks`.
