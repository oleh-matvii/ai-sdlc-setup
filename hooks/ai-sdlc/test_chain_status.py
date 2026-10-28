"""Tests for chain-status: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCRIPT = os.path.join(HERE, "chain-status")


class ChainStatusMarkdownTest(unittest.TestCase):
    """Runs chain-status --md with HOME in a temp dir and a saved gate state for the branch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "app")
        os.makedirs(self.repo)
        git = ["git", "-C", self.repo, "-c", "user.email=t@example.com", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q", "-b", "feat/x"], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], check=True, capture_output=True)
        self.head = subprocess.run(git + ["rev-parse", "HEAD"], check=True, capture_output=True,
                                   text=True).stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def save_state(self, state):
        code = ("import common, json, sys; common.save_chain(sys.argv[1], 'feat/x', json.loads(sys.argv[2]))")
        env = dict(os.environ, HOME=self.home)
        subprocess.run([sys.executable, "-c", code, self.repo, json.dumps(state)], cwd=HERE, env=env, check=True)

    def table(self, state):
        self.save_state(dict(state, head=self.head))
        p = subprocess.run([sys.executable, SCRIPT, "--md", self.repo], capture_output=True, text=True,
                           env=dict(os.environ, HOME=self.home), timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        cells = [[c.strip() for c in line.strip().strip("|").split("|")] for line in p.stdout.splitlines()
                 if line.startswith("| ")]
        return {k: v for k, v in cells}

    def test_spec_tasks_and_design_alignment_rows(self):
        rows = self.table({"type": "feat", "size": "L", "specs": ["docs/specs/a/spec.md"],
                           "task_docs": ["docs/specs/a/tasks.md"],
                           "acceptance": {"status": "ready", "design_alignment": "updated"}})
        self.assertEqual(rows["Spec"], "`docs/specs/a/spec.md`")
        self.assertEqual(rows["Tasks"], "`docs/specs/a/tasks.md`")
        self.assertEqual(rows["Design alignment"], "✅ spec updated")
        self.assertFalse([k for k in rows if "Plan" in k])

    def test_no_spec_alignment(self):
        rows = self.table({"type": "fix", "size": "S",
                           "acceptance": {"status": "ready", "design_alignment": "no_spec"}})
        self.assertEqual(rows["Design alignment"], "— no spec")
        self.assertEqual(rows["Tasks"], "—")

    def test_state_saved_by_the_old_gate_still_renders(self):
        rows = self.table({"type": "feat", "size": "M", "plans": ["docs/superpowers/plans/x.md"],
                           "acceptance": {"status": "ready", "plan_alignment": "diverged"}})
        self.assertEqual(rows["Tasks"], "`docs/superpowers/plans/x.md`")
        self.assertEqual(rows["Design alignment"], "❌ diverged")
        rows = self.table({"type": "fix", "size": "S", "acceptance": {"status": "ready", "plan_alignment": "no_plan"}})
        self.assertEqual(rows["Design alignment"], "— no spec")


if __name__ == "__main__":
    unittest.main()
