#!/usr/bin/env python3
"""PostToolUse (Bash): start the `retro` skill automatically after a PR is created.

Fires only in the main conversation (not inside a subagent), when the command is a `gh pr create`
(the same command shapes review_gate.py gates) and its stdout has the new PR's URL on a line of its
own. Tells the main conversation, via additionalContext, to run the retro skill: propose only,
apply nothing without the user's ok.
Once per repo+branch (outside a git repo: once per PR): fired PRs are remembered under
~/.claude/state/ai-sdlc/retro/. Never blocks; on any error it stays silent.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import hook_decision_log  # noqa: E402
from review_gate import CMD_END, CMD_START  # noqa: E402

RETRO_DIR = os.path.join(common.STATE_DIR, "retro")
PR_CREATE_RE = re.compile(CMD_START + r"gh\s+pr\s+create" + CMD_END)
PR_URL_RE = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)\b")
# `gh pr create` prints only the new PR's URL on stdout (progress goes to stderr): a URL on its own line.
CREATED_URL_RE = re.compile(r"^\s*(%s)\s*$" % PR_URL_RE.pattern, re.M)
CONTEXT = ("PR %s created — run the `retro` skill now (automatic run): propose only, apply nothing "
           "without the user's ok; if nothing is worth proposing, say so in one line.")


def is_pr_create(cmd):
    return bool(PR_CREATE_RE.search(cmd or ""))


def pr_url(response):
    """URL of the PR a successful `gh pr create` printed on stdout, else None."""
    if isinstance(response, dict):
        if response.get("interrupted"):
            return None
        text = response.get("stdout")
    else:
        text = response
    m = CREATED_URL_RE.search(text) if isinstance(text, str) else None
    return m.group(1) if m else None


def state_key(cwd, url):
    """(root, branch, in_git) the trigger is remembered under: the git repo and branch, else the PR itself."""
    root = common.git_root(cwd) if cwd else None
    if root:
        return root, common.git(root, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD", True
    owner, repo, number = PR_URL_RE.search(url).groups()
    return "github.com/%s/%s" % (owner, repo), "pull-%s" % number, False


def main():
    common.bail_if_nested()
    data = common.read_input()
    if not isinstance(data, dict) or data.get("agent_id"):
        return  # inside a subagent: retro belongs to the main conversation
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict) or not is_pr_create(tool_input.get("command")):
        return
    url = pr_url(data.get("tool_response"))
    if not url:
        return
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root, branch, in_git = state_key(cwd, url)
    d, path = common.chain_paths(root, branch, base_dir=RETRO_DIR)
    if os.path.exists(path):
        return
    os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"pr": url, "branch": branch, "fired_at": int(time.time())}, f)
    hook_decision_log.log_decision("retro_trigger", "context", "retro triggered after PR create",
                                   tool="Bash", repo=root if in_git else None)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": CONTEXT % url}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
