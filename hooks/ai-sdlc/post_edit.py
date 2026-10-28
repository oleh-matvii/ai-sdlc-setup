#!/usr/bin/env python3
"""PostToolUse (Edit|Write|MultiEdit).

- Records the edited file for the Stop check of this session.
- Auto-formats it with the project's own tooling (rubocop -a / prettier) when available.
Never blocks.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def main():
    common.bail_if_nested()
    data = common.read_input()
    path = common.tool_file_path(data)
    if not path or not os.path.isfile(path):
        return

    sid = data.get("session_id")
    state = common.load_session(sid)
    if path not in state["files"]:
        state["files"].append(path)
        common.save_session(sid, state)

    if os.environ.get("AI_SDLC_FORMAT") == "0":
        return
    groot = common.git_root(path)
    if common.is_ruby(path):
        root = common.find_up(path, "Gemfile", groot)
        cmd = root and common.ruby_cmd(root, "rubocop")
        if cmd:
            common.run(cmd + ["-a", "--format", "quiet", path], root, 60)
    elif path.endswith(common.PRETTIER_EXT):
        root = common.find_up(path, "package.json", groot)
        cmd = root and common.node_bin(root, "prettier")
        if cmd:
            common.run(cmd + ["--write", "--log-level", "silent", path], root, 60)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
