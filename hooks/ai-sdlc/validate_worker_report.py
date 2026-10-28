#!/usr/bin/env python3
"""PreToolUse (SubagentHandback) and SubagentStop: a worker's report must follow its agent's `## Output`.

The required sections are the numbered items of the `## Output` section of
~/.claude/agents/<agent_type>.md (the bold name, e.g. `1. **Changes:** ...` -> "Changes").
Items that a "replace A–B with" note makes conditional are optional. Agents without the
file or without `## Output` are not checked.
A report section counts when a report line starts with its name (after `#`, `*`, `_`, digits, `.`, `)`).
- SubagentHandback with missing sections: deny once per agent (re-emit in the structure),
  the second time let it through with a warning.
- SubagentStop carrying the report: block, or warn when the stop hook already blocked once.
Denials and blocks go to the hook decision log (agent type and section names only).
Fails open on its own errors.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HOOK = "validate_worker_report"
HANDBACK_TOOL = "SubagentHandback"
AGENTS_DIR = os.environ.get("AI_SDLC_AGENTS_DIR") or os.path.expanduser("~/.claude/agents")
DENIALS_DIR = os.environ.get("AI_SDLC_WORKER_REPORT_DENIALS") or os.path.join(common.STATE_DIR, "worker-report-denials")

OUTPUT_HEADING_RE = re.compile(r"^##\s+Output\b")
HEADING_RE = re.compile(r"^#{1,6}\s")
ITEM_RE = re.compile(r"^(\d+)\.\s+(.*\S)")
BOLD_NAME_RE = re.compile(r"^\*\*(.+?)\*\*")
PLAIN_NAME_END_RE = re.compile(r" \(| — | - |:")
REPLACE_RE = re.compile(r"replace\s+(\d+)\s*[–-]\s*(\d+)\s+with", re.I)
HEADING_DECORATION = "#*_.) \t0123456789"


def item_name(text):
    m = BOLD_NAME_RE.match(text)
    if m:
        name = m.group(1)
    else:
        end = PLAIN_NAME_END_RE.search(text)
        name = text[:end.start()] if end else text
    return name.split(" (", 1)[0].strip().rstrip(":.").strip()


def required_sections(agent_text):
    """Names of the required report sections declared under `## Output`, in order."""
    items, optional = [], set()
    in_output = list_done = False
    for line in agent_text.splitlines():
        if not in_output:
            in_output = bool(OUTPUT_HEADING_RE.match(line))
            continue
        if HEADING_RE.match(line):
            break
        replace = REPLACE_RE.search(line)
        if replace:
            optional.update(range(int(replace.group(1)), int(replace.group(2)) + 1))
        if list_done:
            continue
        item = ITEM_RE.match(line)
        if item:
            items.append((int(item.group(1)), item_name(item.group(2))))
        elif items and line.strip() and not line[0].isspace():
            list_done = True
    return [name for number, name in items if number not in optional]


def missing_sections(names, report):
    starts = [line.lstrip(HEADING_DECORATION).lower() for line in report.splitlines()]
    return [n for n in names if not any(s.startswith(n.lower()) for s in starts)]


def read_agent_file(agent_type):
    if not isinstance(agent_type, str) or not agent_type or os.path.basename(agent_type) != agent_type:
        return None
    try:
        with open(os.path.join(AGENTS_DIR, agent_type + ".md")) as f:
            return f.read()
    except OSError:
        return None


def report_text(data):
    """The report to check, or None when this event carries none."""
    if data.get("hook_event_name") == "PreToolUse":
        if data.get("tool_name") != HANDBACK_TOOL:
            return None
        return (data.get("tool_input") or {}).get("message") or ""
    return data.get("last_assistant_message") or None


def denial_marker(data):
    key = data.get("agent_id") or "%s-%s" % (data.get("session_id"), data.get("agent_type"))
    return os.path.join(DENIALS_DIR, re.sub(r"[^A-Za-z0-9_.-]", "_", str(key)))


def log(decision, data, missing, tool):
    try:
        import hook_decision_log
        hook_decision_log.log_decision(HOOK, decision, "%s: missing %s" % (data.get("agent_type"), ", ".join(missing)),
                                       tool=tool, repo=data.get("cwd") if isinstance(data.get("cwd"), str) else None)
    except Exception:
        pass


def main():
    common.bail_if_nested()
    data = common.read_input()
    if not isinstance(data, dict):
        return
    report = report_text(data)
    if report is None:
        return
    agent_text = read_agent_file(data.get("agent_type"))
    names = required_sections(agent_text) if agent_text else []
    if not names:
        return
    missing = missing_sections(names, report)
    handback = data.get("hook_event_name") == "PreToolUse"
    marker = denial_marker(data)
    if not missing:
        if handback and os.path.exists(marker):
            os.remove(marker)
        return

    problems = "missing section(s): %s" % ", ".join(missing)
    fix = ("Your report does not follow the `## Output` structure of your agent file (%s). Re-emit the full "
           "report with every numbered section heading, in order, without changing its substance." % problems)
    retry_note = "ai-sdlc: the %s report still misses its declared sections after a retry: %s." % (
        data.get("agent_type"), problems)
    if handback:
        if os.path.exists(marker):
            os.remove(marker)
            print(json.dumps({"systemMessage": retry_note}))
            return
        os.makedirs(DENIALS_DIR, exist_ok=True)
        open(marker, "w").close()
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": fix}}))
        sys.stdout.flush()
        log("deny", data, missing, HANDBACK_TOOL)
    elif data.get("stop_hook_active"):
        print(json.dumps({"systemMessage": retry_note}))
    else:
        print(json.dumps({"decision": "block", "reason": fix}))
        sys.stdout.flush()
        log("block", data, missing, None)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a hook must never fail the worker's turn
        pass
    sys.exit(0)
