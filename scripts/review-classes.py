#!/usr/bin/env python3
"""Aggregate the ai-sdlc mistake logs (~/.claude/learn/<repo>/review-log.md) into escalation signals.

Line format (global CLAUDE.md, "Learning"):
    YYYY-MM-DD | <class> | <source> | <branch> | <file:line or -> | <gist>
source: review | user | post-done | check, or `promoted` for a collapsed class:
    YYYY-MM-DD | <class> | promoted | - | <REVIEW.md, CLAUDE.md or hook> | N occurrences, <first>..<last>
Prints (1) classes seen on 2+ branches of a repo (rule candidates), (2) classes seen in 2+ repos,
(3) per promotion the occurrences before it vs entries after it (after > 0: the rule does not hold),
(4) malformed lines as path:line: problem (never the line text).
Usage: review-classes.py [--learn-dir DIR]     Exit code: 0 clean, 1 when malformed lines were found.
"""
import argparse
import glob
import os
import re
import sys
from collections import namedtuple
from datetime import datetime

LEARN_DIR = os.path.expanduser("~/.claude/learn")
LOG_NAME = "review-log.md"
SEPARATOR = " | "
FIELDS = 6
CLASS_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,5}$")
SOURCES = ("review", "user", "post-done", "check")
PROMOTED = "promoted"
COUNT_RE = re.compile(r"^(\d+) occurrences?\b")

Entry = namedtuple("Entry", "line date cls source branch location summary")
Promotion = namedtuple("Promotion", "line date cls target count")
Malformed = namedtuple("Malformed", "line problem")
ParsedLog = namedtuple("ParsedLog", "entries promotions malformed")
RepoLog = namedtuple("RepoLog", "repo parsed")
Effect = namedtuple("Effect", "repo cls target before after")


def valid_date(text):
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def parse_line(number, line):
    """An Entry, a Promotion, or the problem string."""
    fields = [f.strip() for f in line.split(SEPARATOR, FIELDS - 1)]
    if len(fields) != FIELDS:
        return "expected 6 fields: date | class | source | branch | location | gist"
    date, cls, source, branch, location, summary = fields
    if not valid_date(date):
        return "invalid date"
    if not CLASS_RE.match(cls):
        return "invalid class name (2-6 lowercase kebab-case words)"
    if source == PROMOTED:
        count = COUNT_RE.match(summary)
        if not count or not location or location == "-":
            return "promoted line needs the target as location and 'N occurrences' as gist"
        return Promotion(number, date, cls, location, int(count.group(1)))
    if source not in SOURCES:
        return "unknown source (review, user, post-done, check, promoted)"
    return Entry(number, date, cls, source, branch, location, summary)


def parse_log(text):
    entries, promotions, malformed = [], [], []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        item = parse_line(number, line)
        if isinstance(item, Entry):
            entries.append(item)
        elif isinstance(item, Promotion):
            promotions.append(item)
        else:
            malformed.append(Malformed(number, item))
    return ParsedLog(entries, promotions, malformed)


def branch_repeats(logs):
    """{(repo, class): sorted branches} for classes seen on 2+ branches of one repo."""
    branches = {}
    for log in logs:
        for e in log.parsed.entries:
            branches.setdefault((log.repo, e.cls), set()).add(e.branch)
    return {key: sorted(b) for key, b in branches.items() if len(b) >= 2}


def cross_repo_repeats(logs):
    """{class: {repo: occurrences}} for classes seen in 2+ repos (promotion counts included)."""
    counts = {}
    for log in logs:
        for e in log.parsed.entries:
            repos = counts.setdefault(e.cls, {})
            repos[log.repo] = repos.get(log.repo, 0) + 1
        for p in log.parsed.promotions:
            repos = counts.setdefault(p.cls, {})
            repos[log.repo] = repos.get(log.repo, 0) + p.count
    return {cls: repos for cls, repos in counts.items() if len(repos) >= 2}


def promotion_effects(logs):
    effects = []
    for log in logs:
        for p in log.parsed.promotions:
            same = sorted(o.line for o in log.parsed.promotions if o.cls == p.cls)
            i = same.index(p.line)
            prev_line = same[i - 1] if i > 0 else 0
            next_line = same[i + 1] if i + 1 < len(same) else sys.maxsize
            lines = [e.line for e in log.parsed.entries if e.cls == p.cls]
            before = p.count + sum(1 for n in lines if prev_line < n < p.line)
            after = sum(1 for n in lines if p.line < n < next_line)
            effects.append(Effect(log.repo, p.cls, p.target, before, after))
    return effects


def render(logs, malformed_by_path):
    out = ["Repeats within a repo (class on 2+ branches -> propose one rule line):"]
    repeats = branch_repeats(logs)
    out += ["  %s: %s on %d branches (%s)" % (repo, cls, len(b), ", ".join(b))
            for (repo, cls), b in sorted(repeats.items())] or ["  none"]
    out += ["", "Cross-repo repeats (class in 2+ repos -> global CLAUDE.md candidate):"]
    cross = cross_repo_repeats(logs)
    out += ["  %s: %d in %d repos (%s)" % (cls, sum(r.values()), len(r),
                                            ", ".join("%s: %d" % kv for kv in sorted(r.items())))
            for cls, r in sorted(cross.items())] or ["  none"]
    out += ["", "Promoted classes (occurrences before the promotion vs entries after):"]
    out += ["  %s -> %s [%s]: before %d, after %d%s" % (
        e.cls, e.target, e.repo, e.before, e.after, "  NOT HOLDING -> hook/lint candidate" if e.after else "")
        for e in sorted(promotion_effects(logs), key=lambda e: (e.repo, e.cls))] or ["  none"]
    out += ["", "Malformed lines:"]
    out += ["  %s:%d: %s" % (path, m.line, m.problem)
            for path, items in sorted(malformed_by_path.items()) for m in items] or ["  none"]
    return "\n".join(out)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--learn-dir", default=LEARN_DIR)
    args = parser.parse_args(argv)
    paths = sorted(glob.glob(os.path.join(args.learn_dir, "*", LOG_NAME)))
    if not paths:
        print("No review logs under %s" % args.learn_dir)
        return 0
    logs, malformed_by_path = [], {}
    for path in paths:
        try:
            with open(path, errors="replace") as f:
                parsed = parse_log(f.read())
        except OSError as e:
            parsed = ParsedLog([], [], [Malformed(0, "cannot read: %s" % e.strerror)])
        logs.append(RepoLog(os.path.basename(os.path.dirname(path)), parsed))
        if parsed.malformed:
            malformed_by_path[path] = parsed.malformed
    print(render(logs, malformed_by_path))
    return 1 if malformed_by_path else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
