---
name: retro
description: Use when the user runs /retro or asks for a retrospective/lessons learned, and automatically - right after a PR is created (the retro_trigger hook says so) or at the end of a notable task without a PR - extracts recurring mistakes and corrections from the current session and the cross-session mistake log (~/.claude/learn/<repo>/review-log.md), and proposes concise additions to the project's CLAUDE.md or REVIEW.md (or a hook/lint for rules that did not hold) and log compaction for approval. Writes no rule, hook or log compaction without the user's ok.
---

# Retro: learning from the session

Goal — Claude doesn't repeat the same mistakes in this repo. Mechanism from the AI-native SDLC playbook:
"if Claude made the same mistake twice — a line appears in CLAUDE.md".

## Automatic run
Started three ways, same steps: by the `retro_trigger` hook right after a successful `gh pr create` (its context line names the PR), by the main conversation itself at the end of a notable task without a PR, or by `/retro`.
- Run it in the main conversation without being asked; announce it in one line (`retro: <PR url or task>`).
- If after step 2 (Filter) nothing remains and step 6 has no compaction or cleanup candidate — print one line `retro: nothing to propose` and stop, no questions.
- Otherwise ask once: the step 4 proposal and the step 6 candidates together, one approval round.

**Needs the user's "ok":** never write CLAUDE.md, REVIEW.md, hooks, lint config or the log compaction/cleanup without it. The only write without asking is step 1a (appending this session's mistakes to the log, as the global CLAUDE.md requires). Don't commit.

## Steps

1. **Collect signals from the current session** (only from it, invent nothing):
   - where the user corrected you or rejected an approach;
   - `ai-sdlc` Stop-hook blocks (rubocop/rspec/eslint) and what caused them;
   - review gate findings (code-reviewer, acceptance-checker; full report — the path in the gate message) and other reviewers' findings that had to be fixed;
   - commands that failed from not knowing the project (wrong test command, wrong path, wrong convention).
   - **cross-session mistake log** `~/.claude/learn/<repo>/review-log.md` (`<repo>` = name of the git root folder): classes that occurred in ≥2 different branches/tasks are the main candidates. Run `python3 ~/.claude/scripts/review-classes.py` for the aggregate: classes on ≥2 branches of a repo, classes in ≥2 repos (global CLAUDE.md candidates), promoted classes that recurred (`NOT HOLDING`), and malformed log lines (fix them while compacting in step 6).

1a. **Append to the log** this session's mistakes that aren't there yet (source `user` / `post-done` / `check`; format — global CLAUDE.md, "Learning"). Each entry — one line in the response: `Logged: <class> (<source>) → <path>`.

2. **Filter.** Keep only what is:
   - specific to this repo and not obvious from the code;
   - likely to recur;
   - expressible as a one-line instruction.
   Drop one-offs and anything already in CLAUDE.md / REVIEW.md (read them first).

3. **Sort by file:**
   - project `CLAUDE.md` — how to work: commands, conventions, architecture pitfalls;
   - project `REVIEW.md` — what to watch for in review;
   - global `~/.claude/CLAUDE.md` — only if the lesson applies to all repos.

4. **Show the proposal** as a short diff, together with the step 6 candidates: for each line — where it came from (which session episode). At most 5 lines at a time. CLAUDE.md must stay within one page — if it would grow longer, propose what to remove.
   Every proposed REVIEW.md rule carries its provenance on the next line (the same format `/repo-setup` uses):
   ```markdown
   - <the rule, one line checkable against a diff>
     <!-- why: <the episode or repeat behind it> · class: <log class or -> · added: YYYY-MM-DD · review-when: <change that makes it obsolete> -->
   ```
   When reading an existing REVIEW.md, a rule whose `review-when` has come true is a candidate for removal.

   Escalation ladder from the log: class occurred a second time → a rule line; a class with a `promoted` line occurred again → the rule doesn't hold, propose a deterministic control (a hook in `~/.claude/hooks/ai-sdlc/`, a rubocop/eslint rule) instead of another line of text.

5. **Wait for approval.** Apply only the approved lines and step 6 items. Don't commit — say the changes are ready to commit.

6. **Compact the log** (proposed in step 4, applied only after "ok"): for each promoted class, replace all its lines with one —
   `YYYY-MM-DD | <class> | promoted | - | <REVIEW.md or CLAUDE.md> | N occurrences, <first>..<last date>`.
   Classes with a single entry and no repeat for 90+ days — propose deleting.
   Report what was applied: `Collapsed: <class>, <n> entries → <path>` / `Deleted: <class> → <path>` / `Rule added: <short> → <file>`.

If the repo has no CLAUDE.md yet — suggest `/repo-setup` instead of creating the file here.
Don't include customer PII, secrets or log data in proposals.
