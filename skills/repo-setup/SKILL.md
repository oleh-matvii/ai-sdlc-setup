---
name: repo-setup
description: Use only when the user explicitly runs /repo-setup or asks to set up AI-SDLC files for the current repository - drafts the project CLAUDE.md and REVIEW.md from the codebase and explains how to enable automated PR review. Creates files only after approval and never commits.
---

# Repo setup: the project layer of AI-SDLC

The global layer (Superpowers, `ai-sdlc` hooks, `~/.claude/CLAUDE.md`) already works everywhere.
This skill adds to the current repo what is specific to it.

## Rules
- First read what already exists: CLAUDE.md, REVIEW.md, `.claude/`, `.github/workflows/`, README, `bin/`. Extend what exists, don't overwrite.
- Show a draft of each file and wait for approval before writing.
- Don't commit or push anything. These are team files — remind the user they're best added in a separate PR.

## 1. CLAUDE.md (up to one page)
Explore the repo and fill in only what isn't obvious from the code:
- **Commands:** setup, run, tests (full suite and a single file), linter, types/security (e.g. `bin/rspec`, `bin/rubocop`, `bin/brakeman`).
- **Architecture:** 5–10 lines — main parts, where things live, how they connect.
- **Conventions:** what differs from framework defaults.
- **Pitfalls:** external services, feature flags, protected paths (prod infra), VCR cassettes with sensitive data, etc.
- **Verification:** which command proves a change works.
Don't duplicate global rules from `~/.claude/CLAUDE.md`.

## 1a. Stop-hook checks (`.claude/checks.json`)
The `ai-sdlc` Stop-hook has built-in checks only for Ruby (rubocop, mapped rspec) and JS/TS (eslint). When the repo's stack is something else (Python, Go, Elixir, ...) or the built-ins are the wrong commands for it, propose a `.claude/checks.json` with the commands from the CLAUDE.md **Verification** line. It replaces the built-ins for this repo; each command runs from the repo root, red blocks the stop, a timeout or a DB/connection error only warns:
```json
{"lint": "ruff check .", "test": {"command": "pytest -q", "timeout": 600}}
```
Keep the commands fast (lint plus the quick test subset; default timeout 300 s per command). Show the draft and write it only after approval, like the other files.

## 2. REVIEW.md
A checklist for AI review of this repo's PRs (and for local `/code-review`):
- Correctness and regressions; alignment with the spec and its `## Design` from `docs/specs/`, if present.
- Stack-specific security (for Rails: strong params, authorization, SQL/N+1, mass assignment, secrets).
- Tests: is there a regression test for a fix, are existing tests not weakened.
- Repo specifics from CLAUDE.md (protected paths, flags, migrations).
- Format: findings by severity, no style nits the linter catches.

Each rule is one line checkable against a diff, followed on the next line by its provenance, so a later retro can tell why it exists and when to drop it:
```markdown
- Every new controller action is authorized through the policy (`authorize`), including JSON endpoints.
  <!-- why: two PRs exposed records of other accounts · class: missing-authz-scope · added: YYYY-MM-DD · review-when: authorization moves out of controllers -->
```
`class` is the mistake class from `~/.claude/learn/<repo>/review-log.md` when the rule comes from it, otherwise `-`; `review-when` names the change that would make the rule obsolete.

## 3. Automated PR review (explain only, don't set it up yourself)
Advise the user to run the built-in `/install-github-app` command in this repo — it installs the GitHub App and a workflow with `anthropics/claude-code-action`. After that the workflow should be told to review against REVIEW.md. If the repo's CI isn't GitHub Actions (e.g. CircleCI) — say so and propose a `claude -p` variant in their CI.

## 4. Summary
List of created/changed files and what's left to do manually.
