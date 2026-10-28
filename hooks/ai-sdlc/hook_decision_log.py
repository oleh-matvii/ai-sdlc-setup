"""Shared decision log for the ai-sdlc hooks: one JSON line per deny/ask/block decision
(plus `context` when retro_trigger asks the main conversation to run retro).

Fields: timestamp (UTC ISO), hook, decision, reason (one short line), tool, repo (basename only).
Callers pass a short reason of their own: never file contents, command output or review text.
Best effort: a failure here must never change or crash the hook's own decision.
Path: ~/.claude/state/hook-decisions.jsonl, override with CLAUDE_HOOK_DECISION_LOG.
Read it with ~/.claude/scripts/hook-stats.py.
"""
import json
import os
import re
from datetime import datetime, timezone

LOG_PATH_ENV = "CLAUDE_HOOK_DECISION_LOG"
DEFAULT_LOG_PATH = os.path.expanduser("~/.claude/state/hook-decisions.jsonl")
MAX_REASON = 200


def resolve_path():
    return os.environ.get(LOG_PATH_ENV) or DEFAULT_LOG_PATH


def log_decision(hook, decision, reason, tool=None, repo=None, log_path=None):
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hook": hook,
            "decision": decision,
            "reason": re.sub(r"\s+", " ", reason).strip()[:MAX_REASON],
            "tool": tool,
            "repo": os.path.basename(repo.rstrip("/")) if repo else None,
        }
        line = json.dumps(entry) + "\n"
        path = log_path or resolve_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # One write in append mode keeps concurrent hooks from interleaving partial lines.
        with open(path, "a") as f:
            f.write(line)
    except Exception:
        # Deliberately broad: whatever goes wrong here must not reach the hook's decision.
        pass
