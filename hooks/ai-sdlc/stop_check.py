#!/usr/bin/env python3
"""Stop hook: deterministic "verification before completion".

Runs only when files were edited in this session since the last green check:
- Ruby: rubocop on edited files + rspec on edited specs and specs mapped from
  app/**/x.rb -> spec/**/x_spec.rb, lib/x.rb -> spec/lib/x_spec.rb
- JS/TS: eslint on edited files (if the project has eslint installed)
- Any stack: when the edited file's git repo has `.claude/checks.json`, its named commands run
  instead of the built-in checks above, from the repo root, e.g.
      {"lint": "ruff check .", "test": {"command": "pytest -q", "timeout": 600}}
  (a string is a shell command with the default timeout of CHECK_TIMEOUT seconds).
  An unusable checks.json warns and falls back to the built-in checks.

Red -> blocks the stop and feeds the output back to Claude (max 3 times in a row).
Environment problems (DB/Redis down, timeouts) -> warns the user, does not block.
Off switch: AI_SDLC_STOP_CHECKS=0 or touch ~/.claude/state/ai-sdlc/stop-checks-off
"""
import json
import os
import re
import signal
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import hook_decision_log  # noqa: E402

MAX_BLOCKS = 3
MAX_OUTPUT = 4000
ENV_ERROR_RE = re.compile(
    r"ConnectionNotEstablished|PG::ConnectionBad|could not connect to server|"
    r"Connection refused|Mysql2::Error::ConnectionError|Redis::CannotConnectError|"
    r"ActiveRecord::NoDatabaseError|PendingMigrationError"
)
RSPEC_SUMMARY_RE = re.compile(r"(\d+) examples?, (\d+) failures?")
CHECKS_FILE = os.path.join(".claude", "checks.json")
CHECK_TIMEOUT = 300
CHECK_OUTPUT_TAIL = 2000


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def mapped_specs(root, rel):
    if common.is_test_path(rel):
        return [rel] if rel.endswith("_spec.rb") else []
    m = re.match(r"app/(.+)\.rb$", rel) or re.match(r"(lib/.+)\.rb$", rel)
    return ["spec/%s_spec.rb" % m.group(1)] if m else []


def check_ruby(root, files, problems, warnings, passed):
    rels = [os.path.relpath(f, root) for f in files]
    rubocop = common.ruby_cmd(root, "rubocop")
    if rubocop:
        code, out = common.run(rubocop + ["--format", "simple", "--force-exclusion"] + rels, root, 120)
        if code is None:
            warnings.append("rubocop (%s): %s" % (root, out))
        elif code != 0:
            problems.append("rubocop failed in %s:\n%s" % (root, out))
        else:
            passed.append("rubocop (%d files)" % len(rels))

    specs = sorted({s for r in rels if r.endswith(".rb") for s in mapped_specs(root, r)
                    if os.path.isfile(os.path.join(root, s))})
    rspec = common.ruby_cmd(root, "rspec")
    if specs and rspec:
        code, out = common.run(rspec + specs, root, 300)
        summary = RSPEC_SUMMARY_RE.search(out)
        if code == 0:
            passed.append("rspec %s" % (summary.group(0) if summary else "(%d specs)" % len(specs)))
            return
        if code is None or ENV_ERROR_RE.search(out):
            warnings.append("rspec could not run in %s (environment?): %s" % (root, out[-500:]))
        elif summary or "error occurred outside of examples" in out or "errors occurred outside" in out:
            problems.append("rspec failed in %s (%s):\n%s" % (root, " ".join(specs), out))
        else:
            warnings.append("rspec exited %s in %s: %s" % (code, root, out[-500:]))


def check_js(root, files, problems, warnings, passed):
    eslint = common.node_bin(root, "eslint")
    if not eslint:
        return
    rels = [os.path.relpath(f, root) for f in files]
    code, out = common.run(eslint + ["--no-warn-ignored"] + rels, root, 120)
    if code is None:
        warnings.append("eslint (%s): %s" % (root, out))
    elif code == 1:
        problems.append("eslint failed in %s:\n%s" % (root, out))
    elif code == 0:
        passed.append("eslint (%d files)" % len(rels))
    elif code != 0:
        warnings.append("eslint exited %s in %s: %s" % (code, root, out[-500:]))


def load_checks(root):
    """[(name, command, timeout)] from <root>/.claude/checks.json; None without the file.

    Raises ValueError naming the problem when the file is unusable.
    """
    path = os.path.join(root, CHECKS_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError("not readable JSON (%s)" % e)
    if not isinstance(data, dict):
        raise ValueError("must be a JSON object of named commands")
    checks = []
    for name, spec in data.items():
        cmd, timeout = (spec, CHECK_TIMEOUT) if isinstance(spec, str) else \
            ((spec.get("command"), spec.get("timeout", CHECK_TIMEOUT)) if isinstance(spec, dict) else (None, None))
        if not isinstance(cmd, str) or not cmd.strip():
            raise ValueError('"%s" needs a non-empty command string' % name)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError('"%s" timeout must be a positive number of seconds' % name)
        checks.append((name, cmd, timeout))
    return checks


def run_shell(cmd, cwd, timeout):
    """(exit code or None on timeout/failure, output). Kills the whole process group on timeout."""
    try:
        p = subprocess.Popen(cmd, shell=True, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    except Exception as e:
        return None, "failed to run %s: %s" % (cmd, e)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        out, _ = p.communicate()
        return None, "timeout after %ss: %s\n%s" % (timeout, cmd, (out or "")[-500:])


def check_project(root, checks, problems, warnings, passed):
    for name, cmd, timeout in checks:
        code, out = run_shell(cmd, root, timeout)
        tail = out[-CHECK_OUTPUT_TAIL:]
        if code == 0:
            passed.append(name)
        elif code is None or ENV_ERROR_RE.search(out):
            warnings.append("%s could not run in %s (environment?): %s" % (name, root, tail[-500:]))
        else:
            problems.append("%s failed in %s (`%s`, exit %s):\n%s" % (name, root, cmd, code, tail))


def main():
    common.bail_if_nested()
    data = common.read_input()
    sid = data.get("session_id")
    state = common.load_session(sid)
    files = [f for f in state.get("files", []) if os.path.isfile(f)]
    if not files:
        return
    if os.environ.get("AI_SDLC_STOP_CHECKS") == "0" or \
            os.path.exists(os.path.join(common.STATE_DIR, "stop-checks-off")):
        return

    problems, warnings, passed = [], [], []
    ruby, js, project = {}, {}, {}
    for f in files:
        groot = common.git_root(f)
        if groot and groot not in project:
            try:
                project[groot] = load_checks(groot)
            except ValueError as e:
                project[groot] = None
                warnings.append("%s in %s is unusable, used the built-in checks: %s" % (CHECKS_FILE, groot, e))
        if groot and project[groot] is not None:
            continue
        if common.is_ruby(f):
            root = common.find_up(f, "Gemfile", groot)
            if root:
                ruby.setdefault(root, []).append(f)
        elif f.endswith(common.JS_EXT):
            root = common.find_up(f, "package.json", groot)
            if root:
                js.setdefault(root, []).append(f)

    for root, checks in project.items():
        if checks:
            check_project(root, checks, problems, warnings, passed)
    for root, fs in ruby.items():
        check_ruby(root, fs, problems, warnings, passed)
    for root, fs in js.items():
        check_js(root, fs, problems, warnings, passed)

    if problems:
        state["attempts"] = state.get("attempts", 0) + 1
        if state["attempts"] > MAX_BLOCKS:
            state.update(files=[], attempts=0)
            common.save_session(sid, state)
            emit({"systemMessage": "ai-sdlc: checks are still red after %d fix attempts — stopping. "
                                   "Review manually." % MAX_BLOCKS})
        common.save_session(sid, state)
        text = "\n\n".join(problems)
        if len(text) > MAX_OUTPUT:
            text = text[:MAX_OUTPUT] + "\n…(truncated)"
        hook_decision_log.log_decision(
            "stop_check", "block", "red: %s (attempt %d/%d)" % (
                ", ".join(p.split(" failed in ", 1)[0] for p in problems), state["attempts"], MAX_BLOCKS),
            repo=data.get("cwd") if isinstance(data.get("cwd"), str) else None)
        emit({"decision": "block",
              "reason": "ai-sdlc verification failed for files edited in this session "
                        "(attempt %d/%d). Fix the cause, do not weaken tests or disable cops:\n\n%s"
                        % (state["attempts"], MAX_BLOCKS, text)})

    state.update(files=[], attempts=0)
    common.save_session(sid, state)
    msg = []
    if passed:
        msg.append("ai-sdlc ✓ " + " · ".join(passed))
    if warnings:
        msg.append("ai-sdlc ⚠ checks skipped/incomplete — " + " | ".join(w[:300] for w in warnings))
    if msg:
        emit({"systemMessage": "\n".join(msg)})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"systemMessage": "ai-sdlc stop_check error: %s" % e}))
    sys.exit(0)
