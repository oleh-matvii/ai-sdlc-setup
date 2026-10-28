#!/usr/bin/env python3
"""Summarise the ai-sdlc hook decision log: per hook, decision counts, top reasons and repos.

Reads the JSONL written by ~/.claude/hooks/ai-sdlc/hook_decision_log.py (deny/ask/block decisions).
Usage: hook-stats.py [--log PATH] [--since-days N] [--hook NAME]
Malformed lines are skipped and counted in a footer. Always exits 0.
"""
import argparse
import json
import os
from collections import Counter, namedtuple
from datetime import datetime, timedelta, timezone

DEFAULT_LOG = os.environ.get("CLAUDE_HOOK_DECISION_LOG") or os.path.expanduser("~/.claude/state/hook-decisions.jsonl")
TOP_REASONS = 3
REQUIRED_KEYS = ("timestamp", "hook", "decision", "reason")

Entry = namedtuple("Entry", "timestamp hook decision reason repo")


class HookStats:
    def __init__(self):
        self.decisions = Counter()
        self.reasons = Counter()
        self.repos = Counter()


def parse_entry(text):
    try:
        record = json.loads(text)
        if not isinstance(record, dict) or any(k not in record for k in REQUIRED_KEYS):
            return None
        ts = datetime.fromisoformat(record["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return Entry(ts, str(record["hook"]), str(record["decision"]), str(record["reason"]),
                     record.get("repo") or "-")
    except (ValueError, TypeError):
        return None


def parse_entries(lines):
    entries, malformed = [], 0
    for text in lines:
        if not text.strip():
            continue
        entry = parse_entry(text)
        if entry is None:
            malformed += 1
        else:
            entries.append(entry)
    return entries, malformed


def filter_since(entries, since_days, now):
    if since_days is None:
        return entries
    cutoff = now - timedelta(days=since_days)
    return [e for e in entries if e.timestamp >= cutoff]


def filter_hook(entries, hook):
    return [e for e in entries if e.hook == hook] if hook else entries


def aggregate(entries):
    stats = {}
    for e in entries:
        s = stats.setdefault(e.hook, HookStats())
        s.decisions[e.decision] += 1
        s.reasons[e.reason] += 1
        s.repos[e.repo] += 1
    return stats


def format_report(stats, malformed):
    lines = []
    for hook in sorted(stats):
        s = stats[hook]
        lines.append("%s (%d decisions)" % (hook, sum(s.decisions.values())))
        for decision, count in sorted(s.decisions.items()):
            lines.append("  %s: %d" % (decision, count))
        lines.append("  top reasons:")
        lines += ["    %d  %s" % (count, reason) for reason, count in s.reasons.most_common(TOP_REASONS)]
        lines.append("  repos: " + ", ".join("%s: %d" % (repo, n) for repo, n in s.repos.most_common()))
        lines.append("")
    if not stats:
        lines.append("No decisions in range.")
    if malformed:
        lines.append("Skipped %d malformed line(s)." % malformed)
    return "\n".join(lines).rstrip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--since-days", type=float, default=None)
    parser.add_argument("--hook", default=None)
    args = parser.parse_args()
    try:
        with open(args.log, errors="replace") as f:
            text = f.read()
    except OSError:
        print("No log found at %s" % args.log)
        return 0
    entries, malformed = parse_entries(text.splitlines())
    entries = filter_hook(filter_since(entries, args.since_days, datetime.now(timezone.utc)), args.hook)
    print(format_report(aggregate(entries), malformed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
