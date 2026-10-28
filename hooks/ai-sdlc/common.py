"""Shared helpers for the ai-sdlc hooks (Python 3.9 compatible)."""
import hashlib
import json
import os
import re
import subprocess
import sys

STATE_DIR = os.path.expanduser("~/.claude/state/ai-sdlc")
SESSIONS_DIR = os.path.join(STATE_DIR, "sessions")
CHAIN_DIR = os.path.join(STATE_DIR, "chain")

RUBY_EXT = (".rb", ".rake", ".ru", ".gemspec")
RUBY_NAMES = ("Gemfile", "Rakefile")
JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue")
PRETTIER_EXT = JS_EXT + (".css", ".scss")

TEST_PATH_RE = re.compile(
    r"(^|/)(spec|specs|test|tests|__tests__|cypress|e2e|playwright)/"
    r"|_spec\.rb$|_test\.rb$|\.(test|spec)\.[cm]?[jt]sx?$"
)


def bail_if_nested():
    """Child `claude -p` sessions started by review_gate must not re-run our hooks."""
    if os.environ.get("AI_SDLC_NESTED"):
        sys.exit(0)


def read_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def tool_file_path(data):
    ti = data.get("tool_input") or {}
    return ti.get("file_path") or ti.get("notebook_path") or ""


def git_root(path):
    d = path if os.path.isdir(path) else os.path.dirname(path)
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    try:
        out = subprocess.run(
            ["git", "-C", d or ".", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def find_up(path, marker, stop_at=None):
    """Nearest ancestor dir of `path` containing `marker`, not above stop_at."""
    d = os.path.dirname(os.path.abspath(path))
    stop_at = os.path.abspath(stop_at) if stop_at else None
    while True:
        if os.path.exists(os.path.join(d, marker)):
            return d
        if d == stop_at or os.path.dirname(d) == d:
            return None
        d = os.path.dirname(d)


def is_ruby(path):
    return path.endswith(RUBY_EXT) or os.path.basename(path) in RUBY_NAMES


def is_test_path(path):
    if re.search(r"(^|/)docs/", path):
        return False
    return bool(TEST_PATH_RE.search(path))


def session_file(session_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(SESSIONS_DIR, safe + ".json")


def load_session(session_id):
    try:
        with open(session_file(session_id)) as f:
            return json.load(f)
    except Exception:
        return {"files": [], "attempts": 0}


def save_session(session_id, state):
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(session_file(session_id), "w") as f:
        json.dump(state, f)


def ruby_cmd(root, tool):
    """bin/<tool> binstub if present, else bundle exec <tool> if it is in the bundle."""
    binstub = os.path.join(root, "bin", tool)
    if os.access(binstub, os.X_OK):
        return [binstub]
    lock = os.path.join(root, "Gemfile.lock")
    try:
        with open(lock) as f:
            if re.search(r"^\s+%s \(" % re.escape(tool), f.read(), re.M):
                return ["bundle", "exec", tool]
    except Exception:
        pass
    return None


def node_bin(root, tool):
    p = os.path.join(root, "node_modules", ".bin", tool)
    return [p] if os.access(p, os.X_OK) else None


def run(cmd, cwd, timeout):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return None, "timeout after %ss: %s" % (timeout, " ".join(cmd))
    except Exception as e:
        return None, "failed to run %s: %s" % (" ".join(cmd), e)


def git(root, *args, timeout=15):
    try:
        p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:
        return None


def chain_paths(root, branch, base_dir=None):
    """(dir, file) of per-repo+branch state: <base_dir or CHAIN_DIR>/<sha1(root)>/<branch>.json."""
    d = os.path.join(base_dir or CHAIN_DIR, hashlib.sha1(root.encode()).hexdigest())
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", branch or "HEAD")
    return d, os.path.join(d, safe + ".json")


def load_chain(root, branch):
    try:
        with open(chain_paths(root, branch)[1]) as f:
            return json.load(f)
    except Exception:
        return {}


def save_chain(root, branch, state):
    d, p = chain_paths(root, branch)
    os.makedirs(d, exist_ok=True)
    with open(p, "w") as f:
        json.dump(state, f, indent=1)
