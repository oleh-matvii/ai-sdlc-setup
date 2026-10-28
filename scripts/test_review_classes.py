"""Unit tests for review-classes.py: python3 -m unittest discover -s ~/.claude/scripts -p 'test_*.py'"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review-classes.py")


def load_module():
    spec = importlib.util.spec_from_file_location("review_classes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rc = load_module()


def parsed(*lines, header="# Review log: app\n\n"):
    return rc.parse_log(header + "\n".join(lines) + "\n")


def repo_log(name, *lines):
    return rc.RepoLog(name, parsed(*lines))


class ParseLogTest(unittest.TestCase):
    def test_entry_fields_and_pipes_in_the_summary(self):
        log = parsed("2026-10-09 | nil-unchecked | review | feat/a | app/x.rb:3 | used `a | b` twice")
        [e] = log.entries
        self.assertEqual((e.date, e.cls, e.source, e.branch, e.location, e.summary),
                         ("2026-10-09", "nil-unchecked", "review", "feat/a", "app/x.rb:3", "used `a | b` twice"))
        self.assertEqual(log.malformed, [])

    def test_promoted_lines_carry_target_and_count(self):
        log = parsed("2026-10-11 | nil-unchecked | promoted | - | REVIEW.md | 4 occurrences, 2026-10-01..2026-10-11",
                     "2026-10-12 | other-class | promoted | - | CLAUDE.md | 3 occurrences")
        self.assertEqual([(p.cls, p.target, p.count) for p in log.promotions],
                         [("nil-unchecked", "REVIEW.md", 4), ("other-class", "CLAUDE.md", 3)])
        self.assertEqual(log.entries, [])

    def test_every_source_of_the_format_is_accepted(self):
        log = parsed(*["2026-10-01 | a-b | %s | feat/x | - | s" % src for src in ("review", "user", "post-done", "check")])
        self.assertEqual((len(log.entries), log.malformed), (4, []))

    def test_log_without_a_heading_parses(self):
        self.assertEqual(len(rc.parse_log("2026-10-01 | a-b | user | fix/y | - | s\n").entries), 1)

    def test_malformed_lines_get_line_number_and_problem(self):
        log = parsed("2026-10-09 | dead-code | review | feat/a | a.rb | ok",
                     "2026-13-45 | dead-code | review | feat/a | a.rb | bad date",
                     "2026-10-09 | Dead Code | review | feat/a | a.rb | bad class",
                     "2026-10-09 | dead-code | review | feat/a",
                     "2026-10-09 | dead-code | reviewed | feat/a | a.rb | unknown source",
                     "2026-10-09 | dead-code | promoted | - | REVIEW.md | many",
                     "free text between entries")
        self.assertEqual(len(log.entries), 1)
        self.assertEqual([m.line for m in log.malformed], [4, 5, 6, 7, 8, 9])
        self.assertTrue(all(m.problem for m in log.malformed))

    def test_headings_and_blank_lines_are_not_malformed(self):
        self.assertEqual(parsed("", "## Older", "2026-10-09 | a-b | review | x | - | s", "").malformed, [])


class RepeatsTest(unittest.TestCase):
    def test_class_on_two_branches_of_a_repo_is_a_repeat(self):
        logs = [repo_log("app", "2026-10-01 | a-b | review | feat/x | - | s", "2026-10-02 | a-b | user | fix/y | - | s",
                         "2026-10-03 | c-d | review | feat/x | - | s", "2026-10-04 | c-d | check | feat/x | - | s")]
        self.assertEqual(rc.branch_repeats(logs), {("app", "a-b"): ["feat/x", "fix/y"]})

    def test_class_in_two_repos_is_a_cross_repo_repeat(self):
        logs = [repo_log("one", "2026-10-01 | a-b | review | x | - | s", "2026-10-02 | a-b | review | y | - | s",
                         "2026-10-02 | only-here | review | x | - | s"),
                repo_log("two", "2026-10-03 | a-b | user | z | - | s")]
        self.assertEqual(rc.cross_repo_repeats(logs), {"a-b": {"one": 2, "two": 1}})

    def test_promoted_count_adds_to_the_repo_total(self):
        logs = [repo_log("one", "2026-10-01 | c-d | promoted | - | REVIEW.md | 3 occurrences, 2026-09-01..2026-10-01",
                         "2026-10-05 | c-d | review | x | - | s"),
                repo_log("two", "2026-10-03 | c-d | review | y | - | s")]
        self.assertEqual(rc.cross_repo_repeats(logs)["c-d"]["one"], 4)


class PromotionEffectTest(unittest.TestCase):
    def test_entries_after_the_promotion_mean_the_rule_does_not_hold(self):
        logs = [repo_log("app",
                         "2026-10-01 | c-d | review | a | - | before, not collapsed",
                         "2026-10-02 | c-d | promoted | - | CLAUDE.md | 3 occurrences, 2026-09-01..2026-10-02",
                         "2026-10-05 | c-d | review | b | - | after",
                         "2026-10-07 | other | review | b | - | other class")]
        [effect] = rc.promotion_effects(logs)
        self.assertEqual((effect.cls, effect.target, effect.before, effect.after), ("c-d", "CLAUDE.md", 4, 1))

    def test_a_second_promotion_bounds_the_first(self):
        logs = [repo_log("app",
                         "2026-10-02 | c-d | promoted | - | REVIEW.md | 2 occurrences",
                         "2026-10-05 | c-d | review | b | - | between",
                         "2026-10-06 | c-d | promoted | - | hook | 3 occurrences",
                         "2026-10-07 | c-d | review | c | - | after both")]
        self.assertEqual([(e.target, e.before, e.after) for e in rc.promotion_effects(logs)],
                         [("REVIEW.md", 2, 1), ("hook", 4, 1)])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.learn = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, repo, *lines):
        os.makedirs(os.path.join(self.learn, repo))
        with open(os.path.join(self.learn, repo, "review-log.md"), "w") as f:
            f.write("# Review log: %s\n\n%s\n" % (repo, "\n".join(lines)))

    def run_script(self):
        return subprocess.run([sys.executable, SCRIPT, "--learn-dir", self.learn], capture_output=True, text=True,
                              timeout=30)

    def test_prints_every_section_and_exits_zero_when_clean(self):
        self.write("app", "2026-10-01 | a-b | review | feat/x | - | s", "2026-10-02 | a-b | user | fix/y | - | s",
                   "2026-10-03 | c-d | promoted | - | REVIEW.md | 2 occurrences", "2026-10-04 | c-d | review | z | - | s")
        self.write("web", "2026-10-01 | a-b | review | feat/q | - | s")
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        for text in ("Repeats within a repo", "app: a-b on 2 branches", "Cross-repo repeats", "a-b: 3 in 2 repos",
                     "Promoted classes", "NOT HOLDING", "Malformed lines:\n  none"):
            self.assertIn(text, p.stdout)

    def test_malformed_lines_exit_one_and_never_print_the_line_text(self):
        self.write("app", "2026-10-01 | a-b | review | feat/x | - | s", "garbage CUSTOMER-TEXT line")
        p = self.run_script()
        self.assertEqual(p.returncode, 1)
        self.assertIn("review-log.md:4", p.stdout)
        self.assertNotIn("CUSTOMER-TEXT", p.stdout)

    def test_no_logs_is_reported(self):
        p = self.run_script()
        self.assertEqual(p.returncode, 0)
        self.assertIn("No review logs", p.stdout)


if __name__ == "__main__":
    unittest.main()
