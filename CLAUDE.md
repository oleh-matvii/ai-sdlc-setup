# Global working rules (AI-native SDLC)

The task flow is routed by the `ai-sdlc` skill and carried out with the Superpowers plugin (brainstorming → spec → TDD → review → finishing).
These rules extend it and apply in every repo. A project's CLAUDE.md takes precedence over this file.
lk to me in the language I write in. Banner, decision block, stage card and footer labels stay in English as below; their free-text values follow the conversation language.

## Routing
For every new task in the main conversation, invoke the `ai-sdlc` skill (the router: type × size → route) before any other action, and follow the route it gives. Its steps are done by the worker agents it names (code is written by `feature-implementer`, not the main conversation), each through its Superpowers or own skill. Questions, explanations and research without code changes are answered directly, with no routing — except an architecture or design question ("which architecture", "how should we structure", "which pattern"): dispatch the `architect` agent for it, with no banner, no build route and no files.
- Size: when unsure between two sizes take the smaller, say so in banner `decisions`, and move up if the work grows. My "do it as S/M/L" always wins.

## Route visibility: banner, decisions, stage card, footer
Goal: at any moment I can see **where you are, what you decided and why, and what's next** — without scrolling back. Four visibility points: the **banner** at the start, a **decision block** whenever you make a non-obvious choice, a **stage card** at every transition, the **footer** at the end of every response.
- Be specific to the task (files, classes, criteria, numbers, check results), never generic.
- Print each of them as a fenced ```text block so alignment survives in the terminal.
- Never collapse them. A one-line footer like `— ai-sdlc enh/M · stage ▶ PR` is a violation: the footer always has at least the header, `route`, `next` and `you` lines.

**Banner** — once at the start of a task and whenever the route changes (e.g. S turned out to be M — then `why` explains the change). `decisions` lists the routing/approach choices you already made (what was skipped or added and why); omit it only if there were none:
```text
▶ ai-sdlc · feat/M · feat/proj-5742-order-export
  why M:     enhancement of the existing OrderExporter, ~3 files, new format in the same pattern
  decisions: • reuse the OrderExporter::Pdf/Xlsx pattern → no new abstraction, architect skipped
             • no brainstorming (M) · base branch: main
  route:     spec-lite ✋ → current-behavior tests → TDD → gate → PR
  now:       spec-lite — current / target / criteria / code paths / tests / tasks
  from you:  "ok" on spec-lite
```

**Decision block** — right before acting on a non-obvious choice at any stage: picking between approaches or places for code, interpreting an ambiguous requirement, deviating from the spec, skipping/adding a step, disagreeing with a review finding, choosing a library/pattern. Not for trivia (names, formatting). If it changes the spec's Design or tasks — say so and update them.
```text
◆ decision: CSV formatting goes to OrderExporter::Csv, not the controller
  why:    mirrors the Pdf/Xlsx siblings in app/exporters/; controller stays thin
  rejected: inline in OrdersController#export — breaks the pattern, harder to test
  impact: +1 file, spec unchanged
```

**Stage card** — when you start a new stage (after ✋, after a hook message, after a subagent). `input` = what the previous stage produced that this one relies on (subagent verdict, approved spec, gate findings):
```text
▶ stage 3/5 · TDD        ✓spec-lite → ✓current-behavior tests → ▶TDD → ○gate → ○PR
  input:  spec-lite approved; 6 current-behavior specs green
  goal:   AC1–AC3 from the spec-lite, each — red test → minimal code → green
  output: green Stop-hook (rspec/rubocop), commit
```

**Footer** — the last block of every response while a routed task is active:
```text
— ai-sdlc · feat/M · feat/proj-5742-order-export · stage 3/5 TDD
  route:   ✓spec-lite → ✓current-behavior tests → ▶TDD → ○gate → ○PR
  done:    AC 2/3 (CSV export, date filter) · app/exporters/order_exporter/csv.rb, spec
  checks:  Stop-hook: rspec 14/14 ✓, rubocop ✓
  decided: CSV in OrderExporter::Csv (see ◆ above)
  next:    me — AC3 (pagination), then commit and gate
  you:     nothing
```
- `route` — the full chain with markers, not just the current stage.
- `done` — what changed in this response (files, criteria). Nothing changed — omit.
- `checks` — the latest check results from hook output (Stop-hook, gate), not your own assessment. None yet — omit.
- `decided` — one-line summary of decisions made in this response. None — omit.
- `next` — always with an owner: `me — …`. `you` — `nothing` or the concrete ask (✋ decision, a command to run).
- On ✗ add `blocker: <what exactly is red> → <what I'm doing>`. On the PR stage add `pr: <url>` and the gate verdict.
- ✓ done · ▶ now · ○ ahead · ✋ waiting for you · ✗ failed/blocked · ◆ decision.
- Mark ✓ for TDD/gate only after a hook message (`ai-sdlc ✓ …` from the Stop-hook, an `ai-sdlc [...]` line from the gate) — not from your own judgment.
- Questions, explanations, research without code changes — no banner, no decision blocks, no footer.

## Artifacts
- The spec is committed to the repo in `docs/specs/<YYYY-MM-DD-topic>/`: `spec.md` with numbered EARS criteria, plus the architect's `## Design` and `tasks.md` on L/XL; on M a spec-lite with its own `## Tasks`. There is no plan document. Don't start implementing an M-or-larger task without an approved spec (and approved design + tasks on L/XL).
- When the implementation diverges from the spec's Design or tasks — update them in the same commit (acceptance-checker checks alignment).
- ADR (`docs/adr/NNNN-name.md`) — only for XL and irreversible decisions (DB schema, public APIs/events).
- Don't create or change project config (CLAUDE.md, REVIEW.md, `.claude/`, `.github/workflows/`) without my direct request — `/repo-setup` exists for that.

## Verification (hooks exist — don't bypass them)
- "Done" means: tests and linter are green and you saw their output. The `ai-sdlc` Stop-hook runs rubocop/rspec/eslint on changed files itself — or the repo's `.claude/checks.json` commands when it has one — and sends you back if anything is red.
- **Red first:** every test is observed red before it counts. A test written after the code is checked by breaking or removing the behavior it names, confirming it fails, then restoring; a test that stays green either way is rewritten or deleted.
  <!-- why: a test that passes with or without the behavior proves nothing (source: desktop setup) · class: vacuous-test-assertion · added: 2026-10-27 · review-when: a hook or the gate checks red-before-green itself -->
- If a hook blocks — fix the cause. Don't weaken tests, don't add `rubocop:disable`, don't change linter config to pass the check.
- Bug fix and refactor: I approve the tests (✋) before the fix or refactor steps. If a later step changes an approved test, say so in one line (file, what changed, why) — there is no lock.
- Only I toggle ai-sdlc switches (review-gate, stop-checks-off) — the hook will deny you.

## Review (review gate)
- Before `git push`, `gh pr create`, `gh pr ready` the hook itself runs independent `code-reviewer` and `acceptance-checker` sessions on base..HEAD. Don't run them separately before push — that's a duplicate.
- The gate also checks TDD deterministically: feat/enh/fix with code changes but no test changes — rejected; refactor that changes existing tests — rejected.
- `git commit` and push — as separate commands (the gate reviews the committed HEAD).
- Red gate: fix blocker/major findings and not-done criteria, commit, retry. If you disagree with a finding — explain it to me, don't work around it. Full report — the path in the gate message.
- In the PR description include the output of `~/.claude/hooks/ai-sdlc/chain-status --md` and the gate's unaddressed minor findings.
- Verify review comments (human or AI) technically; don't agree automatically.

## Learning
- **Mistake log** — `~/.claude/learn/<repo>/review-log.md`, line `YYYY-MM-DD | <class> | <source> | <branch> | <file:line or -> | <gist>`. `class` — the mechanism of the mistake, 2–4 words kebab-case (`missing-authz-scope`, not `order-export-bug`); reuse an existing class from the log if it fits. The gate logs its own blocker/major findings (source `review`); you add: `user` (I corrected how you wrote code), `post-done` (bug after "done"), `check` (returned by acceptance-checker). Don't log one-off slips with no pattern.
- **My corrections:** when I reject or correct your action — say in one line what you misunderstood; a code mistake goes to the log (`user`), a preference about working or communication style goes to memory as feedback (my words + why). Don't record requirement changes.
- **Escalation:** class already in the log (second time, different task) → propose ONE line in the project's REVIEW.md (or in this file if not repo-specific); repeat after a rule (`promoted` in the log) → propose a hook/lint. Write the rule only after my "ok". The gate flags repeats itself (`ai-sdlc learn`).
- **Say when you write:** every entry in the log, REVIEW.md, CLAUDE.md or memory — one line in the response: what and to which file. Never write silently.
- **Retro runs itself:** after a PR (the `retro_trigger` hook tells you) or at the end of a notable task without a PR, run the `retro` skill yourself — don't just remind me. It only proposes: rules, hooks and log compaction are written only after my "ok"; nothing worth proposing → one line.

## Global config changes
- After editing `~/.claude/CLAUDE.md`, skills or agents run `~/.claude/scripts/eval-routing.zsh` (up to ~$5; single case — `--case <name>`) and show per-case results. A task that was misrouted in real work gets added as a case to `~/.claude/evals/routing/cases.json`.

## Compaction
- Preserve: route and footer, decisions made so far (◆), the spec and tasks paths with the current `in progress` line, acceptance criteria, changed files, check commands and their latest result, open gate findings, pending ✋.

## Security
- Never include customer PII in responses, commits, PRs, logs or artifact files.
- Don't edit `.env*`, keys or credentials without my confirmation (the hook will ask) and never commit them.
- Prod (live/production namespaces, production feature-flag environments, infrastructure apply/destroy) — only with my explicit permission.
