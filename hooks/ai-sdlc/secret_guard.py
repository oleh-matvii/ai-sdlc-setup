#!/usr/bin/env python3
"""PreToolUse (Read|Grep|Glob|Edit|Write|MultiEdit|NotebookEdit|Bash): ask before touching a protected file.

Two protection levels (always "ask", never "deny"; works in auto mode too):
- secret files (.env*, keys, credentials, ~/.ssh/...): any file tool, and shell printing, asks.
- read-protected files (~/.claude/settings*.json): only reading, searching and shell printing ask.
`.example` / `.sample` / `.template` copies pass. Bash is checked only when it runs a
content-printing program (cat, grep, jq, ...) on a protected path.
Asks are logged to the hook decision log (file basename only). Fails open on its own errors.
"""
import fnmatch
import json
import os
import posixpath
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SECRET_NAMES = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "id_rsa*", "id_ed25519*",
    ".netrc", ".npmrc", ".pgpass", "credentials", "credentials.*",
)
SECRET_DIRS = (".ssh",)
SAFE_SUFFIXES = (".example", ".sample", ".template")
READ_PROTECTED = (".claude/settings.json", ".claude/settings.local.json")
HOME_SPELLINGS = ("~", "$HOME", "${HOME}")
PRINTING_PROGRAMS = frozenset((
    "cat", "head", "tail", "less", "more", "bat", "grep", "rg", "sed",
    "awk", "jq", "strings", "xxd", "base64",
))
CD_PROGRAMS = ("cd", "pushd")
PATH_KEYS = {
    "Read": "file_path", "Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path", "Grep": "path", "Glob": "path",
}
READING_TOOLS = ("Read", "Grep", "Glob")
# A plain split instead of a shell lexer: it never fails on odd quoting or comments, and a
# quoted path with spaces falling apart only errs toward asking.
WORD_SEPARATORS = re.compile(r"[\s;|&()<>`]+")
UNQUOTE = str.maketrans("", "", "'\"\\")


def expand_home(raw, home):
    for spelling in HOME_SPELLINGS:
        if raw == spelling or raw.startswith(spelling + "/"):
            return home + raw[len(spelling):]
    return raw


def resolve(raw, cwd, home):
    p = posixpath.normpath(posixpath.join(cwd, expand_home(raw, home)))
    # normpath keeps exactly two leading slashes, which would dodge exact-path matching
    return "/" + p.lstrip("/") if p.startswith("/") else p


def secret_match(path):
    """The pattern a secret path matches, or None."""
    name = posixpath.basename(path).lower()
    if name.endswith(SAFE_SUFFIXES):
        return None
    for pattern in SECRET_NAMES:
        if fnmatch.fnmatchcase(name, pattern):
            return pattern
    parts = path.lower().split("/")[:-1]
    for d in SECRET_DIRS:
        if d in parts:
            return d + "/"
    return None


def read_protected(path, home):
    return any(path.lower() == posixpath.join(home, rel).lower() for rel in READ_PROTECTED)


def secret_kind(path):
    pattern = secret_match(path)
    return "secret file (matches %s)" % pattern if pattern else None


def read_kind(path, home):
    return "protected settings file" if read_protected(path, home) else secret_kind(path)


def working_dir(data):
    cwd = data.get("cwd")
    return cwd if isinstance(cwd, str) else ""


def file_tool_match(data, home):
    tool = data["tool_name"]
    raw = data["tool_input"].get(PATH_KEYS[tool])
    if not raw:
        return None
    path = resolve(raw, working_dir(data), home)
    kind = read_kind(path, home) if tool in READING_TOOLS else secret_kind(path)
    return (path, kind) if kind else None


def words(command):
    # Quotes and backslashes are deleted anywhere in a word, as a shell does.
    return [w for w in (p.translate(UNQUOTE) for p in WORD_SEPARATORS.split(command)) if w]


def bash_match(data, home):
    tokens = words(data["tool_input"]["command"])
    if not any(posixpath.basename(t).lower() in PRINTING_PROGRAMS for t in tokens):
        return None
    cwd = working_dir(data)
    bases = [cwd]
    for i, t in enumerate(tokens):
        if t in CD_PROGRAMS:
            target = next((x for x in tokens[i + 1:] if not x.startswith("-")), None)
            if target:
                d = resolve(target, cwd, home)
                if d not in bases:
                    bases.append(d)
    for t in tokens:
        for base in bases:
            path = resolve(t, base, home)
            kind = read_kind(path, home)
            if kind:
                return path, kind
    return None


def protected_match(data, home):
    """(resolved path, kind) when the tool call touches a protected file, else None."""
    tool = data["tool_name"]
    if tool == "Bash":
        return bash_match(data, home)
    if tool in PATH_KEYS:
        return file_tool_match(data, home)
    return None


def secret_access_reason(data, home):
    m = protected_match(data, home)
    return "%s is a %s" % m if m else None


def main():
    try:
        data = json.load(sys.stdin)
        home = os.path.expanduser("~")
        m = protected_match(data, home)
        if not m:
            return
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "ai-sdlc secret guard: %s is a %s — confirm manually." % m,
        }}))
        sys.stdout.flush()
    except Exception:  # the hook must never block a tool call
        return
    try:
        # Imported late so a broken log module cannot affect the decision already printed.
        import hook_decision_log
        hook_decision_log.log_decision("secret_guard", "ask", "%s: %s" % (posixpath.basename(m[0]), m[1]),
                                       tool=data.get("tool_name"), repo=working_dir(data) or None)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
