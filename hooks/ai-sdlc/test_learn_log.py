"""Unit tests for learn_log.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learn_log  # noqa: E402


def finding(cls, severity="major", location="app/x.rb:1", issue="boom"):
    return {"class": cls, "severity": severity, "location": location, "issue": issue}


class LearnLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "repo", "review-log.md")

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, branch, findings, today="2026-10-19"):
        return learn_log.record(self.path, "repo", branch, findings, today)

    def test_log_path_is_per_repo_under_learn_dir(self):
        self.assertEqual(learn_log.log_path("/src/my-app"),
                         os.path.join(learn_log.LEARN_DIR, "my-app", "review-log.md"))

    def test_first_occurrence_is_logged_and_not_a_repeat(self):
        self.assertEqual(self.record("feat/a", [finding("missing-authz-scope")]), [])
        entries = learn_log.read_entries(self.path)
        self.assertEqual([(e["class"], e["source"], e["branch"]) for e in entries],
                         [("missing-authz-scope", "review", "feat/a")])

    def test_only_blocker_and_major_are_logged(self):
        self.record("feat/a", [finding("a-b", "minor"), finding("c-d", "question"), finding("e-f", "blocker")])
        self.assertEqual(learn_log.known_classes(self.path), ["e-f"])

    def test_invalid_class_is_skipped(self):
        self.record("feat/a", [finding("Not A Class"), finding(""), finding("x|y")])
        self.assertEqual(learn_log.read_entries(self.path), [])

    def test_same_class_on_same_branch_is_not_logged_twice(self):
        self.record("feat/a", [finding("nil-unchecked")])
        self.assertEqual(self.record("feat/a", [finding("nil-unchecked", location="app/y.rb:2")]), [])
        self.assertEqual(len(learn_log.read_entries(self.path)), 1)

    def test_same_class_on_another_branch_is_a_repeat(self):
        self.record("feat/a", [finding("nil-unchecked")])
        repeats = self.record("fix/b", [finding("nil-unchecked")])
        self.assertEqual(repeats, [{"class": "nil-unchecked", "count": 2, "promoted": False}])

    def test_repeat_after_promotion_is_flagged(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("# Review log: repo\n\n2026-09-01 | nil-unchecked | promoted | - | REVIEW.md | 3 occurrences\n")
        repeats = self.record("fix/b", [finding("nil-unchecked")])
        self.assertEqual(repeats, [{"class": "nil-unchecked", "count": 2, "promoted": True}])

    def test_issue_text_is_single_line_and_truncated(self):
        self.record("feat/a", [finding("long-issue", issue="line1\nline2 | " + "x" * 500)])
        with open(self.path) as f:
            last = f.read().splitlines()[-1]
        self.assertNotIn("\n", last)
        self.assertEqual(last.count("|"), 5)
        self.assertLessEqual(len(last.split(" | ", 5)[5]), learn_log.MAX_SUMMARY)

    def test_entries_written_by_hand_are_read(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("# Review log\n\nsome prose\n2026-10-01 | wrong-test-command | user | feat/x | - | used rake\n")
        self.assertEqual(learn_log.known_classes(self.path), ["wrong-test-command"])

    def test_hint_names_the_next_escalation_step(self):
        hint = learn_log.hint([{"class": "a-b", "count": 2, "promoted": False},
                               {"class": "c-d", "count": 4, "promoted": True}], self.path)
        self.assertIn("a-b", hint)
        self.assertIn("REVIEW.md", hint)
        self.assertIn("hook/lint", hint)
        self.assertEqual(learn_log.hint([], self.path), "")


if __name__ == "__main__":
    unittest.main()
