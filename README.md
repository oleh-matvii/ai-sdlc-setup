# ai-sdlc-setup

An AI-native SDLC setup for [Claude Code](https://docs.claude.com/en/docs/claude-code), built on top of the [Superpowers](https://github.com/obra/superpowers) plugin. It is a global `~/.claude` configuration: instructions, a routing skill, worker agents and Python hooks that make every coding task follow the same route and enforce its checks deterministically.

## The flow

1. **Route.** The `ai-sdlc` skill classifies each task by type (feat, enh, fix, refactor, tech, test-only, docs-only) and size (S, M, L, XL) and picks a route with its user checkpoints (✋).
2. **Spec.** M and larger get a spec in `docs/specs/<YYYY-MM-DD-topic>/` with numbered EARS acceptance criteria: a spec-lite with its own tasks on M, or spec + architect's `## Design` + `tasks.md` on L/XL.
3. **TDD.** The `feature-implementer` agent writes the tests first and the code after; the Stop hook runs rubocop/rspec/eslint (or the repo's `.claude/checks.json`) and sends the session back while anything is red.
4. **Gate.** Before `git push`, `gh pr create` or `gh pr ready`, the review-gate hook runs independent `code-reviewer` and `acceptance-checker` sessions on base..HEAD, plus a deterministic TDD check, and denies the command while the review is red.
5. **PR.** The PR body carries the chain status (`hooks/ai-sdlc/chain-status --md`) and the unaddressed minor findings.
6. **Retro.** After the PR the `retro` skill reads the session and the per-repo mistake log and proposes rule lines (or a hook/lint when a rule did not hold), applied only after the user's "ok".

The route is visible throughout: a banner, decision blocks, stage cards and a footer (see `CLAUDE.md`).

## Layout

| Path | What it holds |
|---|---|
| `CLAUDE.md` | Global working rules: routing, visibility (banner/decision/stage/footer), artifacts, verification, review gate, learning loop, security |
| `agents/` | Worker agents: `feature-implementer`, `test-engineer`, `bug-triager`, `architect`, `api-researcher`, `docs-updater`, and the gate's `code-reviewer`, `acceptance-checker` |
| `skills/ai-sdlc/` | The router: type × size → route, checkpoints, and which agent and skill run each step |
| `skills/writing-specs/`, `skills/writing-tasks/` | Spec / spec-lite format with EARS criteria; `tasks.md` for L/XL |
| `skills/architecture/` | Stack-agnostic architecture guidance (zoom levels, styles, patterns by force, trade-offs) with stack notes in `references/` |
| `skills/retro/` | Retrospective: mistake-log escalation into REVIEW.md / CLAUDE.md rules or hooks |
| `skills/repo-setup/` | `/repo-setup`: drafts a project's CLAUDE.md and REVIEW.md |
| `skills/harnessing-llm-output/` | Rules for app code that calls an LLM (schema, validation retry, prompt version) |
| `hooks/ai-sdlc/` | Hooks: `post_edit.py` (records edits, auto-format), `stop_check.py` (checks before stop), `review_gate.py` (review gate), `secret_guard.py` (asks before touching secrets), `validate_worker_report.py` (worker report structure), `retro_trigger.py` (retro after a PR), shared `common.py`, `learn_log.py`, `hook_decision_log.py`; CLIs `chain-status`, `review-gate` and `trust-checks`; unit tests `test_*.py` |
| `scripts/` | `build-routing-evals.py` and `eval-routing.zsh` (routing evals), `review-classes.py` (mistake-log aggregate), `hook-stats.py` (hook decision log summary), with tests |
| `evals/routing/` | Routing eval cases (`cases.json`) and the eval wrapper plugin manifest |
| `settings.json` | The hook registrations and plugins this setup needs (merged by `install.sh`) |
| `install.sh`, `tests/` | Installer (symlinks into `~/.claude`, settings merge) and its tests |
| `examples/` | Sanitized, invented illustrations: a mistake log, a spec-lite, a review-gate report |

## Prerequisites

- Claude Code
- The `superpowers` plugin (`superpowers@claude-plugins-official`)
- `python3` (the hooks are Python 3.9 compatible)
- Optional: the `layered-rails` plugin (`layered-rails@layered-rails-skills`) for Rails design work; `anthropic-skills:grill-me` is offered on risky L/XL features if installed
- `gh` for the PR steps

## Install

The repo is the source; `~/.claude` gets symlinks to it, so `git pull` updates the setup in place. The hooks and scripts reference `$HOME/.claude/...`, which the links satisfy.

```sh
git clone <this repository URL> ai-sdlc-setup
cd ai-sdlc-setup
./install.sh --dry-run   # show what would change
./install.sh
```

`install.sh`:
- symlinks `CLAUDE.md`, each `agents/*.md`, each `skills/<name>/`, `hooks/ai-sdlc/`, each `scripts/*` file, `evals/routing/cases.json` and `evals/routing/.claude-plugin` into `~/.claude`;
- moves any existing target that is not already the right symlink to `~/.claude/backups/ai-sdlc-setup-<timestamp>/` first (your own `CLAUDE.md` included — merge it back by hand if you want parts of it); re-running is safe;
- never overwrites `~/.claude/settings.json`: it adds the repo's hook entries whose command is not there yet and the missing `enabledPlugins` / `extraKnownMarketplaces` keys, keeps everything else (backing up the original), and creates the file when absent. Invalid JSON there stops the install untouched.

Then install the plugins from inside Claude Code (`/plugin`) and start a new session.

Switches (user-only; the hooks deny Claude from flipping them): `hooks/ai-sdlc/review-gate status|skip|off|on`, `AI_SDLC_REVIEW_GATE=0`, `AI_SDLC_STOP_CHECKS=0`.

## Project checks and trust

By default the Stop check runs rubocop/rspec on Ruby files and eslint on JS/TS files. A repo can replace that with its own named commands in `.claude/checks.json`, for example `{"lint": "ruff check .", "test": {"command": "pytest -q", "timeout": 600}}`. Each command runs through a shell from the repo root.

Because a cloned repo could put anything there, its commands run only after you approve that exact file:

```sh
! ~/.claude/hooks/ai-sdlc/trust-checks            # in Claude Code, from inside the repo
~/.claude/hooks/ai-sdlc/trust-checks /path/to/repo # or from your own terminal
```

`trust-checks` prints the commands and records the file's sha256 for the repo root in `~/.claude/state/ai-sdlc/trusted-checks.json`. A new or changed `checks.json` is not run: the Stop check warns, names the file and the command above, and falls back to the built-in checks without blocking. The review gate denies Claude from running `trust-checks` or writing into `~/.claude/state/ai-sdlc/` from the shell (`touch`, `rm`, `mv`, `ln`, `tee`, `sed -i`, redirects, `cp`, `install`), and the secret guard asks before its Write/Edit tools touch that directory. A determined agent can still write the store through an interpreter (for example `python3 -c`), so trust guards against accidents and untrusted repos; it is not a sandbox.

## Routing evals

The evals check that `CLAUDE.md`, the skills and the agents still route tasks correctly. Each case in `evals/routing/cases.json` has a prompt and the criteria an LLM judge grades the transcript against.

```sh
~/.claude/scripts/eval-routing.zsh                 # all cases, 1 run each, capped at $5
~/.claude/scripts/eval-routing.zsh --case 'fix-*'  # a subset; extra args pass through to `claude plugin eval`
```

`eval-routing.zsh` first runs `build-routing-evals.py`, which generates (and `.gitignore` excludes) the per-case `evals/routing/evals/<case>/` prompts with the full `CLAUDE.md` embedded, plus symlinks `evals/routing/skills/` (your enabled global skills and the installed Superpowers skills) and `evals/routing/agents`. Then it runs `claude plugin eval` on `~/.claude/evals/routing`.

Unit tests for the hooks, scripts and installer (the installer tests use a temporary `HOME`):

```sh
python3 -m unittest discover -s hooks/ai-sdlc -p 'test_*.py'
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Examples

`examples/` holds sanitized, invented illustrations, not real data:
- `examples/learn/review-log.md` — a per-repo mistake log in the format the gate and retro use (`~/.claude/learn/<repo>/review-log.md`), including a `promoted` line and a repeat that is a rule candidate;
- `examples/specs/2026-09-14-order-csv-export/spec.md` — a spec-lite (M);
- `examples/gate-report.md` — a review-gate chain line and report.
