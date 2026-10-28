"""Unit tests for hook_decision_log.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook_decision_log  # noqa: E402

FIELDS = {"timestamp", "hook", "decision", "reason", "tool", "repo"}


class HookDecisionLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "state", "hook-decisions.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def entries(self):
        with open(self.path) as f:
            return [json.loads(line) for line in f.read().splitlines()]

    def log(self, *args, **kwargs):
        kwargs.setdefault("log_path", self.path)
        return hook_decision_log.log_decision(*args, **kwargs)

    def test_default_path_is_under_claude_state(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(hook_decision_log.LOG_PATH_ENV, None)
            self.assertEqual(hook_decision_log.resolve_path(),
                             os.path.expanduser("~/.claude/state/hook-decisions.jsonl"))

    def test_env_variable_overrides_the_path(self):
        with mock.patch.dict(os.environ, {hook_decision_log.LOG_PATH_ENV: self.path}):
            hook_decision_log.log_decision("guard", "deny", "test lock", tool="Edit", repo="/src/app")
        self.assertEqual(len(self.entries()), 1)

    def test_appends_one_json_line_per_decision_with_the_agreed_fields(self):
        self.log("guard", "deny", "test lock", tool="Edit", repo="/src/my-app")
        self.log("secret_guard", "ask", "secret file", tool="Read", repo="/src/other/")
        first, second = self.entries()
        self.assertEqual(set(first), FIELDS)
        self.assertEqual({k: first[k] for k in FIELDS - {"timestamp"}},
                         {"hook": "guard", "decision": "deny", "reason": "test lock",
                          "tool": "Edit", "repo": "my-app"})
        self.assertEqual((second["hook"], second["repo"]), ("secret_guard", "other"))

    def test_repo_is_stored_as_basename_only(self):
        self.log("h", "ask", "r", repo="/Users/someone/work/secret-project")
        self.assertEqual(self.entries()[0]["repo"], "secret-project")

    def test_missing_tool_and_repo_are_null(self):
        self.log("h", "block", "r")
        e = self.entries()[0]
        self.assertEqual((e["tool"], e["repo"]), (None, None))

    def test_timestamp_is_utc_iso(self):
        self.log("h", "ask", "r")
        ts = datetime.fromisoformat(self.entries()[0]["timestamp"])
        self.assertEqual(ts.utcoffset().total_seconds(), 0)

    def test_reason_is_one_short_line(self):
        self.log("h", "block", "line1\nline2\n" + "x" * 1000)
        reason = self.entries()[0]["reason"]
        self.assertNotIn("\n", reason)
        self.assertLessEqual(len(reason), hook_decision_log.MAX_REASON)
        self.assertTrue(reason.startswith("line1 line2 x"))

    def test_unwritable_path_does_not_raise(self):
        blocker = os.path.join(self.tmp.name, "blocker")
        with open(blocker, "w") as f:
            f.write("a file, so it cannot be a directory")
        self.assertIsNone(self.log("h", "ask", "r", log_path=os.path.join(blocker, "log.jsonl")))

    def test_unserialisable_input_does_not_raise(self):
        self.assertIsNone(self.log("h", "ask", object()))
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
