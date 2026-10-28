---
name: ai-sdlc
description: Use at the start of every new task in the main conversation (feature, enhancement, bug fix, refactor, chore, config or dependency change, test-only or docs-only work) before any other action - the ai-sdlc router that sets the task type and size, picks the route, its ✋ checkpoints and the worker agent and skill for every step. Not for pure questions or explanations with no code change.
---

# ai-sdlc router

The main conversation routes every new task here before acting on it: determine type and size, announce the route with the banner, then follow the chain, dispatching the worker agent each step names. Questions, explanations and research without code changes get no routing.

## Routes: type × size
At the start of a task determine its **type** and **size**, announce the route (banner — see "Route visibility" in the global CLAUDE.md) and follow it.

**Type** — branch prefix `<type>/<ticket>-<slug>` (e.g. `feat/proj-5742-order-export`):
`feat/` new feature · `enh/` enhancement of existing behavior · `fix/` bug · `refactor/` no behavior change · `tech/` (chore) dependencies, config, CI.
If the team doesn't use `enh/`, the branch is `feat/` and the type is set in the spec (`**Type:** enh`) — that takes precedence over the prefix.

**Size:** S — a line/condition, one file · M — enhancement within an existing pattern · L — new module/flow · XL — several modules → split into several L (separate specs, branches, PRs) + an ADR for irreversible decisions.
When unsure between two sizes, take the smaller, say so in banner `decisions`, and move up (new banner) if the work grows. My "do it as S/M/L" always wins.

The spec (`docs/specs/<YYYY-MM-DD-topic>/spec.md`) starts with the lines `**Type:** <type>`, `**Size:** <S|M|L|XL>` and `**Status:**` — the review gate reads them. There is no plan document: L/XL keep the design in the spec's `## Design` and the tasks in `tasks.md` next to it; M keeps its tasks in the spec-lite's `## Tasks`.

| Route | Chain (✋ = waiting for my "ok"; [..] = only when its condition holds) |
|---|---|
| feat L/XL | brainstorming → [grill-me ✋, offered when large or risky] → spec.md ✋ → **architect** (`## Design` in spec.md) → [**api-researcher**, if an unfamiliar library/API] → tasks.md → design + tasks ✋ → **feature-implementer** (whole tasks.md, TDD) → [**test-engineer**, edge cases/regression] → [**docs-updater**, if public behavior/config/setup changed] → simplify → gate → PR → /retro |
| feat/enh M | [brainstorming-lite ✋, if unclear] → [**api-researcher**, if an unfamiliar library/API] → spec-lite (current → target → criteria → code paths → tests → tasks) ✋ → [**architect**, if a new abstraction: `## Design` in the spec-lite] → **feature-implementer** (tests for the current behavior of the touched code → TDD per spec task) → [**docs-updater**] → gate → PR |
| any S | [brainstorming-lite ✋, if unclear] → **feature-implementer** (TDD) → gate → PR (no spec) |
| fix | **bug-triager** (skip for S if the cause is evident from the report/stack trace) → [brainstorming-lite ✋, if the fix needs a decision] → **feature-implementer**: failing test ✋ → **feature-implementer** (resumed): fix → gate → PR |
| refactor | **architect** (smells, target design, steps; report in chat) ✋ → **feature-implementer**: characterization tests ✋ → **feature-implementer** (resumed): small steps, each green → simplify → gate → PR |
| tech (chore) | [brainstorming-lite ✋, if the change needs a decision] → [**api-researcher**, for an upgrade with breaking changes] → **feature-implementer**: change → gate (review only) → PR |
| test-only | **test-engineer** → gate → PR |
| docs-only | **docs-updater** → gate → PR |
| review-only | **code-reviewer** on the current branch (no build route) |
| architecture question | **architect** answers in its report (no banner, no build route, no files) |

- **Approved spec already exists:** when the task's `spec.md` is approved (and, on L/XL, its `## Design` and `tasks.md`), skip the earlier steps — no brainstorming, `writing-specs`, architect or `writing-tasks` again: show the banner with the remaining route and dispatch one `feature-implementer` for the unticked tasks.
- **grill-me on risky L/XL:** when a feat L/XL is large or risky (a one-way door, several modules, many open questions), offer `anthropic-skills:grill-me` after brainstorming and before spec.md; run it only on my "yes", and its answers go into the spec.
- **Architecture question:** a design question with no code change ("which architecture", "how should we structure", "which pattern") goes to `architect` instead of a direct answer; relay its recommendation.

Approved tests on the fix and refactor routes, at every size: the failing test / characterization tests get my "ok" (✋) before the fix or refactor steps, even for an S fix or when I ask for speed. After that, the implementer changes an approved test only when it is needed, and reports every such change (file, what, why); the main conversation relays it to me in one line. There is no lock.

## Who does each step, and through which skill

| Step | Who | Runs through |
|---|---|---|
| brainstorming (L/XL) | main conversation | `superpowers:brainstorming`; its result goes into spec.md via `writing-specs` — no separate Superpowers design doc, no handoff to `writing-plans` |
| spec.md (L/XL), spec-lite (M) | main conversation | `writing-specs`; acceptance criteria numbered `AC1…` in EARS form: `WHEN <trigger> [WHILE <state>] THE SYSTEM SHALL <response>`; spec-lite tasks are `- [ ]` checkboxes |
| brainstorming-lite | main conversation | the format below |
| grill-me (risky L/XL, on my "yes") | main conversation | `anthropic-skills:grill-me` |
| design (`## Design` in the spec), refactor steps | `architect` | `architecture` (+ `layered-rails`); options and research stay in the spec folder's `research.md` |
| tasks.md (L/XL) | main conversation | `writing-tasks`; every task is `- [ ] N. … (covers: ACx[, depends on: N])` |
| triage | `bug-triager` | `superpowers:systematic-debugging`, up to the root cause |
| library/API research | `api-researcher` | Context7 + official docs → a research notes file |
| tests + code | `feature-implementer` | `superpowers:test-driven-development` (+ `architecture` when it creates a unit, + `harnessing-llm-output` when the change calls an LLM or edits a prompt the app sends) |
| edge cases, test-only | `test-engineer` | `superpowers:test-driven-development` |
| docs | `docs-updater` | the team's docs-hub skill (if installed) for a team docs hub, else its own prompt |
| simplify | main conversation | built-in `simplify`, one pass over the branch diff, before the gate |
| gate | the review-gate hook | `code-reviewer` + `acceptance-checker`, automatic on push / PR — never dispatch them yourself before a push |
| gate findings | `feature-implementer` (resumed) | `superpowers:receiving-code-review` |
| finish | main conversation | `superpowers:verification-before-completion`, then push/PR through the gate (`superpowers:finishing-a-development-branch`) |
| retro (every route, after the PR; or at the end of a notable task without one) | main conversation, automatically — after `gh pr create` the `retro_trigger` hook tells it to | `retro`: proposes rules / log compaction for ✋, writes nothing before my "ok"; nothing to propose → one line |

Not used: `superpowers:writing-plans`, `superpowers:executing-plans`, `superpowers:subagent-driven-development` — the spec (`writing-specs`), `tasks.md` (`writing-tasks`) and one `feature-implementer` replace them, even when a Superpowers skill hands off to them.

## Dispatching workers
- **Roles:** the main conversation routes, talks to me (✋, decisions), dispatches one worker at a time, relays their reports, runs simplify, push, PR and retro. It writes no production code or tests itself on any route, S and tech included — `feature-implementer` does (or `test-engineer` / `docs-updater` on their routes).
- **One implementer per spec:** one `feature-implementer` executes the whole `tasks.md` (L/XL) or the spec-lite's `## Tasks` (M) in order. No implementer, check or review per task.
- **Phases at ✋:** a checkpoint inside the implementer's work (fix: failing test; refactor: characterization tests) ends its phase: it reports and stops. After my "ok", resume the same implementer with SendMessage for the next phase; dispatch a fresh one with the spec, tasks and commit pointers only if it cannot be resumed. Gate findings also go back to the same implementer.
- **Every brief** carries: route, type/size, branch and base, the phase and its stop point, and pointers to the spec, `tasks.md`, research notes and relevant commits (paths, not pasted content); the bug-triager report, which has no file, goes in verbatim.
- **Reports:** check each report against the worker's Output section before the next step; a report missing its structure or its check results goes back once. Relay what the worker changed, its check results and blockers in the stage card/footer.
- **Progress lives in the tasks:** the implementer ticks `- [x]` in `tasks.md` (L/XL) or the spec-lite's `## Tasks` (M) per finished task and keeps one `in progress: … — next: …` line under the current one; when the implementation diverges it updates the spec's `## Design`/tasks in the same commit. Show me each progress change; a new session resumes from the first unticked task.

## Brainstorming-lite
Optional step for S, M, fix and tech; full brainstorming (→ spec) stays only for feat L/XL.
- Run it when at least one holds:
  - the requirement has ≥2 reasonable readings that lead to different behavior (unclear scope, edge cases, who/when/what limits);
  - fix: the cause is known, but the correct expected behavior is a product decision, or there are ≥2 viable fixes with real trade-offs (patch the symptom vs fix the data/flow, migrate existing records or not);
  - tech: there are ≥2 viable approaches with real trade-offs (upgrade path or target version, which config/CI option, migrate everything now vs incrementally, keep vs replace a dependency);
  - I ask for it ("let's think it through", "brainstorm", "what are the options?").
- Don't run it when the requirement, fix or tech change is unambiguous — then say in banner `decisions` why it was skipped. Never run full Superpowers brainstorming for S/M/fix/tech, even if the skill suggests it.
- Format: only the questions that block a decision (one at a time, multiple choice when possible) → 2–3 options with trade-offs and your recommendation → ✋ my choice. No document of its own: the result goes into the spec-lite (M), the failing test's expected behavior (fix) or a ◆ decision block (S, tech — the chosen option goes into the implementer's brief).
- For fix it runs after bug-triager (it needs the root cause) and before the failing test (the test encodes the chosen behavior).
- For tech it runs before api-researcher, unless the decision depends on the research — then after it.

Architecture decisions follow the `architecture` skill (codebase-first, no unnecessary patterns).
