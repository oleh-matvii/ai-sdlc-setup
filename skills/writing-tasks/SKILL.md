---
name: writing-tasks
description: Use on the ai-sdlc feat L/XL route after the spec is approved and the architect has written its Design section - writes tasks.md next to spec.md, an ordered checklist of small tasks, each mapped to acceptance criteria, for one feature-implementer to execute. Not for M (the spec-lite has its own Tasks section) or routes without a spec.
---

# Writing tasks

`tasks.md` turns the spec's **what** (acceptance criteria) and its `## Design` (**how**) into an ordered checklist that one `feature-implementer` executes and ticks. There is no plan document in between.

Write it in the main conversation after the architect has filled `## Design`, then show design + tasks together for one ✋.

## Where it lives
`docs/specs/<YYYY-MM-DD-topic>/tasks.md`, next to `spec.md`.

## What goes in
- **In:** numbered, ordered tasks, each traceable to criteria `ACx`, with explicit dependencies.
- **Out:** the purpose, criteria or design restated — link to `spec.md` instead.

## Task rules
- Small enough to implement and verify in one sitting; a task that needs an "and" is two tasks.
- Every task covers at least one criterion; every criterion is covered by some task.
- Earlier tasks unblock later ones; name each real dependency.
- Prefer vertical slices (a narrow path through every layer it touches, verifiable on its own) over layer-by-layer tasks.
- Prefactoring first: make the change easy, then make the easy change.
- A wide mechanical change (renaming a column, retyping a shared symbol) goes expand–contract: add the new form beside the old, migrate callers in batches (one task per directory/package, each depending on the expand), remove the old form last.
- Each task names the test that proves it (the first red test from the Design's testing shape for task 1).

## Template
```markdown
# <Feature> — tasks

**Spec:** ./spec.md (criteria and `## Design`)

- [ ] 1. <task> — <what it delivers> (covers: AC1)
- [ ] 2. <task> — <what it delivers> (covers: AC2, AC3, depends on: 1)
```

## Progress
The implementer ticks `- [x]` when a task is implemented and green, and keeps one indented line under the current task: `in progress: <done> — next: <remaining>`. When the implementation diverges, it updates `tasks.md` (and the spec's `## Design`) in the same commit. A new session resumes from the first unticked task.

## Handoff
Show the design and the task list together and ask whether the granularity is right and each dependency really gates its task; iterate until the user's "ok" (✋). Then dispatch one `feature-implementer` for the whole list.
