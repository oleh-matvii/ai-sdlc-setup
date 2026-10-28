"""Per-repo log of mistakes by class (the mechanism of the mistake), for escalation via /retro.

The review gate appends blocker/major code-reviewer findings; the main session appends
`user` / `post-done` / `check` entries by hand in the same format:
    YYYY-MM-DD | <class> | <source> | <branch> | <location> | <summary>
A class seen on a second branch is a repeat -> propose a rule (REVIEW.md / CLAUDE.md);
a repeat after a `promoted` line -> the rule is not holding, propose a hook/lint.
"""
import os
import re

LEARN_DIR = os.path.expanduser("~/.claude/learn")
LOGGED_SEVERITIES = ("blocker", "major")
CLASS_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,5}$")
ENTRY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) \| ([a-z0-9-]+) \| ([a-z-]+) \| ([^|]*?) \|")
PROMOTED = "promoted"
MAX_SUMMARY = 160


def log_path(root):
    return os.path.join(LEARN_DIR, os.path.basename(root.rstrip("/")), "review-log.md")


def read_entries(path):
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        m = ENTRY_RE.match(line)
        if m:
            entries.append({"date": m.group(1), "class": m.group(2), "source": m.group(3),
                            "branch": m.group(4).strip()})
    return entries


def known_classes(path):
    return sorted({e["class"] for e in read_entries(path)})


def one_line(text):
    return re.sub(r"\s+", " ", text.replace("|", "/")).strip()[:MAX_SUMMARY]


def record(path, repo, branch, findings, today):
    """Append new blocker/major findings; return the classes that repeat across branches."""
    entries = read_entries(path)
    new_lines, repeats, seen = [], [], set()
    for f in findings:
        cls = (f.get("class") or "").strip()
        if f.get("severity") not in LOGGED_SEVERITIES or not CLASS_RE.match(cls) or cls in seen:
            continue
        seen.add(cls)
        prior = [e for e in entries if e["class"] == cls]
        if any(e["branch"] == branch and e["source"] != PROMOTED for e in prior):
            continue
        new_lines.append("%s | %s | review | %s | %s | %s" % (
            today, cls, one_line(branch), one_line(f.get("location", "-")), one_line(f.get("issue", ""))))
        if prior:
            repeats.append({"class": cls, "count": len(prior) + 1,
                            "promoted": any(e["source"] == PROMOTED for e in prior)})
    if new_lines:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fresh = not os.path.exists(path)
        with open(path, "a") as out:
            if fresh:
                out.write("# Review log: %s\n\n" % repo)
            out.write("\n".join(new_lines) + "\n")
    return repeats


def hint(repeats, path):
    lines = []
    for r in repeats:
        if r["promoted"]:
            lines.append("- `%s` repeats after a rule: the rule doesn't hold -> propose to the user "
                         "a deterministic control (hook/lint)." % r["class"])
        else:
            lines.append("- `%s` repeats (%d times): propose to the user ONE rule line in the project's REVIEW.md "
                         "(or in the global CLAUDE.md if not repo-specific)." % (r["class"], r["count"]))
    if not lines:
        return ""
    return "ai-sdlc learn (%s):\n%s\nProposal only: write the rule only after the user's \"ok\"." % (
        path, "\n".join(lines))
