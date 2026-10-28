#!/usr/bin/env python3
"""PreToolUse (Bash): the ai-sdlc review gate.

1. User-only switches: denies Bash commands that turn off ai-sdlc checks
   (review-gate, writes to ~/.claude/state/ai-sdlc).
2. Review gate: before `git push`, `gh pr create` or `gh pr ready`, runs two independent
   headless sessions on base..HEAD (`claude -p --agent code-reviewer` and `--agent acceptance-checker`)
   and lets the command through only when both are green for the current HEAD.
   Type and size come from the header of the branch's spec (`docs/specs/<topic>/spec.md`:
   `Type:`, `Size: S|M|L|XL`; legacy: a `docs/superpowers/plans/` doc), else the branch prefix
   (feat/ enh/ fix/ refactor/ tech|chore/) and the diff. Before any agent runs, a deterministic TDD check:
   feat/enh/fix code changes need test changes; refactor must not modify existing tests.
   - green for this HEAD already -> instant pass (cache)
   - red -> deny with the findings (max 3 in a row, then ask the user)
   - the agents failed to run -> ask the user
Off switch: AI_SDLC_REVIEW_GATE=0, `review-gate off`, or one-shot `review-gate skip` (user only).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import hook_decision_log  # noqa: E402
import learn_log  # noqa: E402

MAX_BLOCKS = 3
MAX_REASON = 6000
SKILLS_DIR = os.path.expanduser("~/.claude/skills/architecture")
TYPE_PREFIXES = [
    ("feat", ("feat", "feature")),
    ("enh", ("enh", "enhancement", "improve")),
    ("fix", ("fix", "bugfix", "hotfix", "bug")),
    ("refactor", ("refactor", "refactoring")),
    ("chore", ("chore", "tech", "deps", "dependabot", "ci", "docs", "build")),
]
CODE_EXT = (".rb", ".rake", ".js", ".jsx", ".ts", ".tsx", ".vue", ".mjs", ".cjs")
NOT_CODE_RE = re.compile(r"(^|/)(config|db|docs|bin|vendor|public|script|\.github|\.storybook)/"
                         r"|\.stories\.[jt]sx?$|\.d\.ts$|(^|/)[^/]*\.config\.[cm]?[jt]s$")
SPEC_DIR = "docs/specs/"
LEGACY_SPEC_DIR = "docs/superpowers/specs/"
LEGACY_PLAN_DIR = "docs/superpowers/plans/"
SIZE_RE = re.compile(r"^\W*size\W*:?\W*(S|M|L|XL)\b", re.I | re.M)
TYPE_RE = re.compile(r"^\W*type\W*:?\W*(feat|enh|fix|refactor|chore|tech)\b", re.I | re.M)

# A command word starts after a separator, a subshell paren or an opening quote (`bash -c 'git push'`)
# and ends before one; a plain regex, no shell lexer.
CMD_START = r"(^|[;&|(\s\"'`])"
CMD_END = r"(?=$|[\s;&|)\"'`])"
GATED_RE = re.compile(CMD_START + r"(git\s+push|gh\s+pr\s+(create|ready))" + CMD_END)
PUSH_NO_REVIEW_RE = re.compile(r"\s(--delete|-d|--tags)" + CMD_END)
SEGMENT_END_RE = re.compile(r"[;&|)\n]")
COMMIT_RE = re.compile(CMD_START + r"git\s+commit" + CMD_END)
USER_ONLY_RE = re.compile(r"(^|[/\s(;&|\"'`])review-gate[\"']?\s+(off|skip|on)\b")
STATE_WRITE_RE = re.compile(r"((\btouch|\brm|\bmv|\bln|\btee|sed\s+-i)\s|>)[^\n;&|]*state/ai-sdlc")

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "changes_requested"]},
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["blocker", "major", "minor", "question"]},
                "location": {"type": "string"},
                "issue": {"type": "string"},
                "fix": {"type": "string"},
                "class": {"type": "string"},
            },
            "required": ["severity", "location", "issue", "class"],
        }},
    },
    "required": ["verdict", "summary", "findings"],
}
ACCEPT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ready", "ready_with_followups", "not_ready"]},
        "criteria_source": {"type": "string"},
        "criteria": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "criterion": {"type": "string"},
                "status": {"type": "string", "enum": ["done", "partial", "not_done", "unverified"]},
                "evidence": {"type": "string"},
            },
            "required": ["criterion", "status", "evidence"],
        }},
        "verification_needed": {"type": "array", "items": {"type": "string"}},
        "design_alignment": {"type": "string", "enum": ["matches", "updated", "diverged", "no_spec"]},
        "summary": {"type": "string"},
    },
    "required": ["status", "criteria_source", "criteria", "design_alignment", "summary"],
}
GIT_READ = "Bash(git diff:*) Bash(git log:*) Bash(git show:*) Bash(git blame:*) Bash(git grep:*)"
TOOLS = {
    "code-reviewer": "Read Grep Glob StructuredOutput " + GIT_READ,
    "acceptance-checker": "Read Grep Glob StructuredOutput " + GIT_READ
                          + " Bash(bin/rspec:*) Bash(bundle exec rspec:*) Bash(rspec:*)"
                          + " Bash(npx jest:*) Bash(npx vitest run:*) Bash(yarn jest:*) Bash(bun test:*)",
}
MODELS = {
    "code-reviewer": os.environ.get("AI_SDLC_REVIEW_MODEL", "claude-opus-5-5"),
    "acceptance-checker": os.environ.get("AI_SDLC_ACCEPT_MODEL", "claude-opus-5-5"),
}
EFFORT = os.environ.get("AI_SDLC_REVIEW_EFFORT", "high")


def decide(decision, reason, log_reason, repo, system=None):
    """Print the decision, log it (log_reason: short, no command or review text), exit."""
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": decision,
                                  "permissionDecisionReason": reason}}
    if system:
        out["systemMessage"] = system
    print(json.dumps(out))
    sys.stdout.flush()
    hook_decision_log.log_decision("review_gate", decision, log_reason, tool="Bash", repo=repo)
    sys.exit(0)


def note(system, context=None):
    out = {"systemMessage": system}
    if context:
        out["hookSpecificOutput"] = {"hookEventName": "PreToolUse", "additionalContext": context}
    print(json.dumps(out))
    sys.exit(0)


def claude_bin():
    for c in (shutil.which("claude"), os.path.expanduser("~/.local/bin/claude"), "/usr/local/bin/claude"):
        if c and os.access(c, os.X_OK):
            return c
    return None


def base_ref(root):
    head = common.git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    cands = ([head] if head else []) + ["origin/main", "origin/master", "main", "master"]
    for c in cands:
        if common.git(root, "rev-parse", "--verify", "--quiet", c + "^{commit}"):
            return c
    return None


def branch_type(branch):
    first = branch.split("/", 1)[0].lower() if "/" in branch else ""
    for t, prefixes in TYPE_PREFIXES:
        if first in prefixes:
            return t
    return None


def spec_header(root, head, docs):
    """Type/Size declared in the first lines of a spec (or legacy plan) doc of this branch."""
    t = sz = None
    for p in docs:
        text = (common.git(root, "show", "%s:%s" % (head, p)) or "")[:1500]
        t = t or (TYPE_RE.search(text) and TYPE_RE.search(text).group(1).lower())
        t = "chore" if t == "tech" else t  # same as the tech/ branch prefix
        sz = sz or (SIZE_RE.search(text) and SIZE_RE.search(text).group(1).upper())
    return t, sz


def spec_docs(root, head, files):
    """Spec and tasks docs of the branch: `docs/specs/<topic>/spec.md` and `tasks.md` (a changed
    tasks.md brings its spec along when that exists at head), plus the legacy Superpowers
    `docs/superpowers/specs/` and `docs/superpowers/plans/` docs."""
    def in_spec_dir(f, name):
        return f.startswith(SPEC_DIR) and os.path.basename(f) == name

    tasks = [f for f in files if in_spec_dir(f, "tasks.md")]
    specs = [f for f in files if in_spec_dir(f, "spec.md")]
    for t in tasks:
        sibling = os.path.join(os.path.dirname(t), "spec.md")
        if sibling not in specs and common.git(root, "cat-file", "-e", "%s:%s" % (head, sibling)) is not None:
            specs.append(sibling)
    specs += [f for f in files if f.startswith(LEGACY_SPEC_DIR)]
    tasks += [f for f in files if f.startswith(LEGACY_PLAN_DIR)]
    return specs, tasks


def collect(root, branch, base, head):
    status = {}
    for row in (common.git(root, "diff", "--name-status", "-M", base, head) or "").splitlines():
        parts = row.split("\t")
        if len(parts) >= 2:
            status[parts[-1]] = parts[0][0]
    files = list(status)
    stat = common.git(root, "diff", "--shortstat", base, head) or ""
    lines = sum(int(n) for n in re.findall(r"(\d+) (?:insertion|deletion)", stat))
    specs, task_docs = spec_docs(root, head, files)
    tests = [f for f in files if common.is_test_path(f) and status[f] != "D"]
    tests_touched = [f for f in files if common.is_test_path(f) and status[f] in ("M", "D", "R")]
    code = [f for f in files if f.endswith(CODE_EXT) and not common.is_test_path(f)
            and not NOT_CODE_RE.search(f) and status[f] != "D"]
    header_docs = [f for f in specs if f.startswith(SPEC_DIR)] + [f for f in task_docs if f.startswith(LEGACY_PLAN_DIR)]
    declared_type, declared_size = spec_header(root, head, header_docs)
    ttype = declared_type or branch_type(branch) or "unknown"
    if declared_size:
        size, size_src = declared_size, "spec"
    else:
        size_src = "diff"
        size = "S" if len(files) <= 3 and lines <= 40 else "M" if len(files) <= 15 and lines <= 500 else "L"
    return {
        "files": files, "lines": lines, "specs": specs, "task_docs": task_docs, "tests": tests,
        "tests_touched": tests_touched, "code": code,
        "type": ttype, "size": size, "size_src": size_src,
        "review_md": os.path.isfile(os.path.join(root, "REVIEW.md")),
        "claude_md": os.path.isfile(os.path.join(root, "CLAUDE.md")),
    }


def tdd_violation(info):
    """Deterministic test discipline, checked before any agent runs."""
    if info["type"] in ("feat", "enh", "fix") and info["code"] and not info["tests"]:
        return ("%s branch changes code (%s) but adds/changes no tests. TDD: write the test that "
                "proves the behavior (for a fix: the regression test that fails without it), commit, retry."
                % (info["type"], ", ".join(info["code"][:5])))
    if info["type"] == "refactor" and info["tests_touched"]:
        return ("refactor branch modifies/deletes existing tests (%s). A refactor must keep behavior "
                "identical: existing tests stay untouched (new characterization tests may be added). "
                "Revert the test changes, or if behavior really changes, this is enh/feat, not refactor."
                % ", ".join(info["tests_touched"][:5]))
    return None


def agent_prompt(name, root, branch, base, head, info):
    shown = info["files"][:200]
    more = len(info["files"]) - len(shown)
    parts = [
        "Run your %s procedure for this branch. Your cwd is the repo root: run git commands directly "
        "(no `git -C`, no `cd`)." % name,
        "repo root: %s" % root,
        "branch: %s" % branch,
        "base SHA: %s" % base,
        "head SHA: %s" % head,
        "diff command: git diff %s...%s" % (base, head),
        "task type: %s" % info["type"],
        "size: %s (from %s)" % (info["size"], info["size_src"]),
        "REVIEW.md: %s" % ("REVIEW.md" if info["review_md"] else "none"),
        "CLAUDE.md: %s" % ("CLAUDE.md" if info["claude_md"] else "none"),
        "spec docs in this branch: %s" % (", ".join(info["specs"]) or "none"),
        "tasks docs in this branch: %s" % (", ".join(info["task_docs"]) or "none"),
        "changed files (%d, %d lines changed):\n%s%s" % (
            len(info["files"]), info["lines"], "\n".join(shown), "\n…and %d more" % more if more > 0 else ""),
        "Return the result via the structured output tool.",
    ]
    if name == "code-reviewer":
        classes = learn_log.known_classes(learn_log.log_path(root))
        parts.insert(-1, "known mistake classes in this repo (reuse one if it names the same mechanism): %s"
                     % (", ".join(classes) or "none yet"))
    return "\n".join(parts)


def start_agent(claude, name, schema, prompt, root):
    cmd = [claude, "-p", "--agent", name, "--model", MODELS[name], "--effort", EFFORT,
           "--settings", json.dumps({"disableAllHooks": True}),
           "--permission-mode", "dontAsk",
           "--allowedTools", TOOLS[name],
           "--disallowedTools", "Edit Write NotebookEdit",
           "--add-dir", SKILLS_DIR,
           "--no-session-persistence", "--output-format", "json",
           "--json-schema", json.dumps(schema), prompt]
    env = dict(os.environ, AI_SDLC_NESTED="1")
    return subprocess.Popen(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def finish_agent(proc):
    out, err = proc.communicate()
    try:
        data = json.loads(out)
    except Exception:
        return None, "exit %s: %s" % (proc.returncode, (err or out or "")[-400:])
    so = data.get("structured_output")
    if data.get("is_error") or not isinstance(so, dict):
        return None, "no structured result (%s): %s" % (data.get("subtype"), str(data.get("result"))[-400:])
    return so, None


def render_review(r):
    lines = ["### code-reviewer: %s" % r["verdict"], r.get("summary", "")]
    for f in r.get("findings", []):
        lines.append("- **%s** `%s` [%s]: %s%s" % (f["severity"], f["location"], f.get("class", "?"), f["issue"],
                                                   (" → " + f["fix"]) if f.get("fix") else ""))
    return "\n".join(lines)


def render_accept(a):
    lines = ["### acceptance-checker: %s (criteria: %s, design: %s)" % (
        a["status"], a.get("criteria_source", "?"), a.get("design_alignment", "?")),
             a.get("summary", "")]
    for c in a.get("criteria", []):
        lines.append("- [%s] %s: %s" % (c["status"], c["criterion"], c["evidence"]))
    for v in a.get("verification_needed", []) or []:
        lines.append("- verify: %s" % v)
    return "\n".join(lines)


def chain_line(branch, head, info, review, accept):
    def mark(ok):
        return "✓" if ok else "✗"
    parts = []
    spec_route = info["type"] in ("feat", "enh") and info["size"] != "S"
    if spec_route or info["specs"]:
        parts.append(mark(info["specs"]) + "spec")
    if (spec_route and info["size"] in ("L", "XL")) or info["task_docs"]:
        parts.append(mark(info["task_docs"]) + "tasks")
    parts.append(mark(info["tests"]) + "tests")
    if review is None:
        parts.append("?review")
    else:
        sev = [f["severity"] for f in review.get("findings", []) if f["severity"] in ("blocker", "major")]
        parts.append(mark(review["verdict"] == "approve") + "review" + ("(%d)" % len(sev) if sev else ""))
    if skip_acceptance(info):
        parts.append("–acceptance")
    elif accept is None:
        parts.append("?acceptance")
    else:
        parts.append(mark(accept["status"] != "not_ready") + "acceptance")
        if accept.get("design_alignment") in ("matches", "updated", "diverged"):
            parts.append(mark(accept["design_alignment"] != "diverged") + "design-aligned")
    return "ai-sdlc [%s @ %s] %s/%s: %s" % (branch, head[:7], info["type"], info["size"], " ".join(parts))


def skip_acceptance(info):
    return info["type"] == "chore" or (info["size"] == "S" and info["type"] != "feat")


def gated_command(cmd):
    """True when cmd pushes or creates/readies a PR and so needs the review.

    A push that only deletes refs or pushes tags needs none; its flags count only inside
    that push's own segment (up to the next ; & | ) or newline).
    """
    for m in GATED_RE.finditer(cmd):
        if not m.group(2).startswith("git"):
            return True
        rest = cmd[m.end():]
        end = SEGMENT_END_RE.search(rest)
        if not PUSH_NO_REVIEW_RE.search(rest[:end.start()] if end else rest):
            return True
    return False


def check_user_only(cmd, repo=None):
    if USER_ONLY_RE.search(cmd) or STATE_WRITE_RE.search(cmd):
        decide("deny", "ai-sdlc: this turns off or changes an ai-sdlc safety switch "
                       "(review gate, stop checks). Only the user does that, from their "
                       "own terminal or with `!`. Explain to the user why you think it is needed.",
               "user-only safety switch", repo)


def main():
    common.bail_if_nested()
    data = common.read_input()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    check_user_only(cmd, cwd)

    if not gated_command(cmd):
        return
    if os.environ.get("AI_SDLC_REVIEW_GATE") == "0" or \
            os.path.exists(os.path.join(common.STATE_DIR, "review-gate-off")):
        return
    if COMMIT_RE.search(cmd):
        decide("deny", "ai-sdlc review gate: run `git commit` as a separate command first, then push / "
                       "create the PR. The gate reviews the committed HEAD.",
               "commit in the same command as the push/PR", cwd)

    root = common.git_root(cwd or os.getcwd())
    if not root:
        return
    branch = common.git(root, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
    head = common.git(root, "rev-parse", "HEAD")
    ref = base_ref(root)
    if not head or not ref:
        decide("ask", "ai-sdlc review gate: cannot determine the base branch for %s; confirm manually." % root,
               "no base branch", root)
    base = common.git(root, "merge-base", head, ref)
    if not base or base == head:
        return

    state = common.load_chain(root, branch)
    if state.get("skip_head") == head:
        state.pop("skip_head")
        common.save_chain(root, branch, state)
        note("ai-sdlc review gate: skipped once by the user for %s @ %s" % (branch, head[:7]))
    if state.get("passed_head") == head:
        note(state.get("line", "ai-sdlc: review already green for this HEAD"))

    info = collect(root, branch, base, head)
    violation = tdd_violation(info)
    if violation:
        decide("deny", "ai-sdlc gate [%s/%s]: %s" % (info["type"], info["size"], violation),
               "tdd violation (%s/%s)" % (info["type"], info["size"]), root)
    claude = claude_bin()
    if not claude:
        decide("ask", "ai-sdlc review gate: `claude` CLI not found, review did not run. Push anyway?",
               "claude CLI not found", root)

    agents = [("code-reviewer", REVIEW_SCHEMA)]
    if not skip_acceptance(info):
        agents.append(("acceptance-checker", ACCEPT_SCHEMA))
    procs = [(n, start_agent(claude, n, s, agent_prompt(n, root, branch, base, head, info), root))
             for n, s in agents]
    results, errors = {}, []
    for name, proc in procs:
        res, err = finish_agent(proc)
        if err:
            errors.append("%s: %s" % (name, err))
        results[name] = res
    review, accept = results.get("code-reviewer"), results.get("acceptance-checker")

    d, _ = common.chain_paths(root, branch)
    os.makedirs(d, exist_ok=True)
    report_paths = []
    blocks = []
    if review:
        blocks.append(render_review(review))
    if accept:
        blocks.append(render_accept(accept))
    if blocks:
        rp = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "_", branch) + ".report.md")
        with open(rp, "w") as f:
            f.write("# ai-sdlc review: %s @ %s (base %s)\n\n%s\n" % (branch, head[:7], base[:7],
                                                                      "\n\n".join(blocks)))
        report_paths.append(rp)

    learn_hint = ""
    if review:
        try:
            lp = learn_log.log_path(root)
            repeats = learn_log.record(lp, os.path.basename(root), branch, review.get("findings", []),
                                       time.strftime("%Y-%m-%d"))
            learn_hint = learn_log.hint(repeats, lp)
        except Exception:
            pass

    line = chain_line(branch, head, info, review, accept)
    state.update(branch=branch, head=head, base=base, type=info["type"], size=info["size"], line=line,
                 specs=info["specs"], task_docs=info["task_docs"], tests=len(info["tests"]),
                 review=review and {"verdict": review["verdict"], "summary": review.get("summary", "")},
                 acceptance=accept and {"status": accept["status"], "summary": accept.get("summary", ""),
                                        "design_alignment": accept.get("design_alignment")},
                 report=report_paths[0] if report_paths else None, checked_at=int(time.time()))

    if errors:
        common.save_chain(root, branch, state)
        decide("ask", "ai-sdlc review gate could not complete (%s). %s Push anyway?" % ("; ".join(errors), line),
               "review agents failed: %s" % ", ".join(e.split(":", 1)[0] for e in errors), root)

    ok = review["verdict"] == "approve" and (accept is None or accept["status"] != "not_ready")
    if ok:
        state.update(passed_head=head, attempts=0)
        common.save_chain(root, branch, state)
        followups = "\n\n".join(blocks)
        note(line, "ai-sdlc review gate passed. Findings and follow-ups (mention the non-blocking ones "
                   "to the user / in the PR):\n\n" + followups[:MAX_REASON]
             + ("\n\n" + learn_hint if learn_hint else ""))

    state["attempts"] = state.get("attempts", 0) + 1
    if state["attempts"] > MAX_BLOCKS:
        state["attempts"] = 0
        common.save_chain(root, branch, state)
        decide("ask", "ai-sdlc review gate is still red after %d fix rounds. %s Full report: %s. "
                      "Decide yourself whether to push." % (MAX_BLOCKS, line, state.get("report")),
               "still red after %d rounds" % MAX_BLOCKS, root, line)
    common.save_chain(root, branch, state)
    text = "\n\n".join(blocks)
    if len(text) > MAX_REASON:
        text = text[:MAX_REASON] + "\n…(truncated, full report: %s)" % state.get("report")
    if learn_hint:
        text += "\n\n" + learn_hint
    decide("deny",
           "%s\n\nai-sdlc review gate is red (round %d/%d). Fix the blocker/major findings and the "
           "not-done criteria, commit, then retry the same command. Do not weaken tests. If you think "
           "a finding is wrong, explain it to the user instead of working around the gate.\n"
           "Full report: %s\n\n%s" % (line, state["attempts"], MAX_BLOCKS, state.get("report"), text),
           "review red round %d/%d: code-reviewer %s, acceptance %s" % (
               state["attempts"], MAX_BLOCKS, review["verdict"], accept["status"] if accept else "skipped"),
           root, line)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "ask",
            "permissionDecisionReason": "ai-sdlc review gate crashed (%s); confirm manually." % e}}))
        sys.stdout.flush()
        hook_decision_log.log_decision("review_gate", "ask", "gate crashed: %s" % type(e).__name__, tool="Bash")
    sys.exit(0)
