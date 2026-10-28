"""Unit tests for hook-stats.py: python3 -m unittest discover -s ~/.claude/scripts -p 'test_*.py'"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hook-stats.py")
NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


def load_module():
    spec = importlib.util.spec_from_file_location("hook_stats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook_stats = load_module()


def line(hook, decision, reason, ts=NOW, repo="app", tool="Bash"):
    return json.dumps({"timestamp": ts.isoformat(), "hook": hook, "decision": decision, "reason": reason,
                       "tool": tool, "repo": repo})


class ParseTest(unittest.TestCase):
    def test_valid_lines_parse_and_malformed_ones_are_counted(self):
        entries, malformed = hook_stats.parse_entries([line("a", "deny", "r"), "not json{", "[1]",
                                                       '{"hook": "a"}', ""])
        self.assertEqual([(e.hook, e.decision, e.reason, e.repo) for e in entries], [("a", "deny", "r", "app")])
        self.assertEqual(malformed, 3)

    def test_unparseable_timestamp_is_malformed(self):
        bad = json.dumps({"timestamp": "yesterday", "hook": "a", "decision": "deny", "reason": "r"})
        self.assertEqual(hook_stats.parse_entries([bad]), ([], 1))

    def test_naive_timestamp_is_read_as_utc(self):
        naive = json.dumps({"timestamp": "2026-10-27T10:00:00", "hook": "a", "decision": "ask", "reason": "r"})
        [entry], _ = hook_stats.parse_entries([naive])
        self.assertEqual(entry.timestamp.utcoffset(), timedelta(0))


class AggregateTest(unittest.TestCase):
    def entries(self, *lines):
        return hook_stats.parse_entries(list(lines))[0]

    def test_counts_per_hook_and_decision_with_top_three_reasons(self):
        stats = hook_stats.aggregate(self.entries(
            *[line("h", "deny", "common")] * 3, *[line("h", "deny", "second")] * 3,
            line("h", "ask", "third"), line("h", "ask", "third"), line("h", "ask", "fourth"),
            line("other", "block", "x")))
        self.assertEqual(dict(stats["h"].decisions), {"deny": 6, "ask": 3})
        self.assertEqual(stats["h"].reasons.most_common(3), [("common", 3), ("second", 3), ("third", 2)])
        self.assertEqual(dict(stats["other"].decisions), {"block": 1})

    def test_repos_are_counted_per_hook(self):
        stats = hook_stats.aggregate(self.entries(line("h", "deny", "r", repo="a"), line("h", "deny", "r", repo="a"),
                                                  line("h", "deny", "r", repo=None)))
        self.assertEqual(dict(stats["h"].repos), {"a": 2, "-": 1})

    def test_since_filter_drops_older_entries(self):
        entries = self.entries(line("h", "deny", "r", NOW - timedelta(days=10)), line("h", "deny", "r", NOW))
        self.assertEqual([e.timestamp for e in hook_stats.filter_since(entries, 5, NOW)], [NOW])
        self.assertEqual(len(hook_stats.filter_since(entries, None, NOW)), 2)

    def test_hook_filter_keeps_one_hook(self):
        entries = self.entries(line("a", "deny", "r"), line("b", "ask", "r"))
        self.assertEqual([e.hook for e in hook_stats.filter_hook(entries, "b")], ["b"])


class FormatTest(unittest.TestCase):
    def test_report_lists_hooks_decisions_reasons_repos_and_malformed_footer(self):
        entries, malformed = hook_stats.parse_entries([line("h", "deny", "why"), line("h", "ask", "ok"), "junk"])
        report = hook_stats.format_report(hook_stats.aggregate(entries), malformed)
        self.assertIn("h (2 decisions)", report)
        self.assertIn("deny: 1", report)
        self.assertIn("1  why", report)
        self.assertIn("app: 2", report)
        self.assertIn("Skipped 1 malformed line", report)

    def test_empty_report_says_so(self):
        self.assertIn("No decisions", hook_stats.format_report({}, 0))


class ScriptTest(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, text=True, timeout=30)

    def test_runs_on_a_log_file_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.jsonl")
            with open(log, "w") as f:
                f.write(line("h", "deny", "why") + "\nbroken\n")
            p = self.run_script("--log", log)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("deny: 1", p.stdout)
        self.assertIn("malformed", p.stdout)

    def test_default_log_comes_from_the_hooks_env_variable(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.jsonl")
            with open(log, "w") as f:
                f.write(line("from-env", "ask", "r") + "\n")
            p = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, timeout=30,
                               env=dict(os.environ, CLAUDE_HOOK_DECISION_LOG=log))
        self.assertIn("from-env", p.stdout)

    def test_missing_log_exits_zero_with_a_message(self):
        p = self.run_script("--log", "/nonexistent/log.jsonl")
        self.assertEqual(p.returncode, 0)
        self.assertIn("No log", p.stdout)


if __name__ == "__main__":
    unittest.main()
