"""Unit tests for the trust-checks CLI: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'

trust-checks [<repo root or path inside it>] shows the commands of <repo>/.claude/checks.json and records the
sha256 of its content for that repo root in ~/.claude/state/ai-sdlc/trusted-checks.json ({"<root>": "<sha256>"}).
Runs with HOME in a temp dir.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HOOKS_DIR, "trust-checks")


class TrustChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "repo")
        os.makedirs(os.path.join(self.repo, "pkg"))
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.store = os.path.join(self.home, ".claude", "state", "ai-sdlc", "trusted-checks.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write_checks(self, content):
        os.makedirs(os.path.join(self.repo, ".claude"), exist_ok=True)
        with open(os.path.join(self.repo, ".claude", "checks.json"), "w") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))

    def sha(self):
        with open(os.path.join(self.repo, ".claude", "checks.json"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def run_cli(self, *args, cwd=None):
        self.assertTrue(os.path.isfile(SCRIPT), "missing %s" % SCRIPT)
        return subprocess.run([sys.executable, SCRIPT] + list(args), cwd=cwd or self.home, capture_output=True,
                              text=True, timeout=30, env=dict(os.environ, HOME=self.home))

    def trusted(self):
        if not os.path.exists(self.store):
            return {}
        with open(self.store) as f:
            return json.load(f)

    def test_shows_the_commands_and_records_the_hash_for_the_repo_root(self):
        self.write_checks({"lint": "ruff check .", "test": {"command": "pytest -q && echo done", "timeout": 600}})
        r = self.run_cli(self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("lint", r.stdout)
        self.assertIn("ruff check .", r.stdout)
        self.assertIn("pytest -q && echo done", r.stdout)
        self.assertEqual(self.trusted(), {self.repo: self.sha()})

    def test_defaults_to_the_git_root_of_the_current_dir(self):
        self.write_checks({"lint": "true"})
        r = self.run_cli(cwd=os.path.join(self.repo, "pkg"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trusted(), {self.repo: self.sha()})

    def test_retrusting_a_changed_file_replaces_its_hash_and_keeps_other_repos(self):
        os.makedirs(os.path.dirname(self.store))
        with open(self.store, "w") as f:
            json.dump({"/elsewhere": "abc", self.repo: "old"}, f)
        self.write_checks({"lint": "true"})
        self.run_cli(self.repo)
        self.assertEqual(self.trusted(), {"/elsewhere": "abc", self.repo: self.sha()})

    def test_without_checks_json_it_fails_and_records_nothing(self):
        r = self.run_cli(self.repo)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("checks.json", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.store))

    def test_an_unusable_checks_json_is_not_trusted(self):
        self.write_checks("{not json")
        r = self.run_cli(self.repo)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.store))

    def test_outside_a_git_repo_it_fails(self):
        r = self.run_cli(self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.store))


if __name__ == "__main__":
    unittest.main()
