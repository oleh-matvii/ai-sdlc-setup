"""Unit tests for stop_check.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS_DIR)
import stop_check  # noqa: E402

SCRIPT = os.path.join(HOOKS_DIR, "stop_check.py")


class MappedSpecsTest(unittest.TestCase):
    def test_app_and_lib_files_map_to_their_specs(self):
        for rel, spec in (("app/models/user.rb", "spec/models/user_spec.rb"),
                          ("app/controllers/api/v1/users_controller.rb",
                           "spec/controllers/api/v1/users_controller_spec.rb"),
                          ("lib/billing/invoice.rb", "spec/lib/billing/invoice_spec.rb")):
            with self.subTest(rel=rel):
                self.assertEqual(stop_check.mapped_specs("/repo", rel), [spec])

    def test_an_edited_spec_maps_to_itself(self):
        self.assertEqual(stop_check.mapped_specs("/repo", "spec/models/user_spec.rb"), ["spec/models/user_spec.rb"])

    def test_test_helpers_and_minitest_files_map_to_nothing(self):
        for rel in ("spec/support/helpers.rb", "spec/spec_helper.rb", "test/models/user_test.rb"):
            with self.subTest(rel=rel):
                self.assertEqual(stop_check.mapped_specs("/repo", rel), [])

    def test_other_ruby_files_map_to_nothing(self):
        for rel in ("config/routes.rb", "db/migrate/1_x.rb", "Gemfile", "engines/x/app/models/y.rb"):
            with self.subTest(rel=rel):
                self.assertEqual(stop_check.mapped_specs("/repo", rel), [])


class LoadChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, content):
        os.makedirs(os.path.join(self.root, ".claude"), exist_ok=True)
        with open(os.path.join(self.root, ".claude", "checks.json"), "w") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))

    def test_no_file_means_no_project_checks(self):
        self.assertIsNone(stop_check.load_checks(self.root))

    def test_named_commands_keep_their_order_and_get_the_default_timeout(self):
        self.write('{"lint": "ruff check .", "test": "pytest -q"}')
        self.assertEqual(stop_check.load_checks(self.root),
                         [("lint", "ruff check .", stop_check.CHECK_TIMEOUT),
                          ("test", "pytest -q", stop_check.CHECK_TIMEOUT)])

    def test_a_check_can_set_its_own_timeout(self):
        self.write({"test": {"command": "go test ./...", "timeout": 900}})
        self.assertEqual(stop_check.load_checks(self.root), [("test", "go test ./...", 900)])

    def test_unusable_files_raise_with_the_problem(self):
        for content in ("{not json", "[]", '{"lint": ""}', '{"lint": 3}', '{"t": {"timeout": 5}}',
                        '{"t": {"command": "x", "timeout": 0}}', '{"t": {"command": "x", "timeout": "5"}}'):
            with self.subTest(content=content):
                self.write(content)
                with self.assertRaises(ValueError):
                    stop_check.load_checks(self.root)


class ProjectChecksHookTest(unittest.TestCase):
    """Runs stop_check.py as the Stop hook runs it, with HOME in a temp dir (isolated session state)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "repo")
        os.makedirs(os.path.join(self.repo, "pkg", "sub"))
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.edited = [self.touch("pkg/sub/main.py")]

    def tearDown(self):
        self.tmp.cleanup()

    def touch(self, rel):
        path = os.path.join(self.repo, rel)
        open(path, "a").close()
        return path

    def write_checks(self, checks, trusted=True):
        """Writes .claude/checks.json; trusted=True also records its sha256 for this repo, as trust-checks does."""
        os.makedirs(os.path.join(self.repo, ".claude"), exist_ok=True)
        with open(os.path.join(self.repo, ".claude", "checks.json"), "w") as f:
            f.write(checks if isinstance(checks, str) else json.dumps(checks))
        if trusted:
            self.trust(self.repo)

    def checks_sha(self):
        with open(os.path.join(self.repo, ".claude", "checks.json"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def trust_store(self):
        return os.path.join(self.home, ".claude", "state", "ai-sdlc", "trusted-checks.json")

    def trust(self, root, sha=None):
        store = {}
        if os.path.exists(self.trust_store()):
            with open(self.trust_store()) as f:
                store = json.load(f)
        store[root] = sha or self.checks_sha()
        os.makedirs(os.path.dirname(self.trust_store()), exist_ok=True)
        with open(self.trust_store(), "w") as f:
            json.dump(store, f)

    def run_hook(self):
        sessions = os.path.join(self.home, ".claude", "state", "ai-sdlc", "sessions")
        os.makedirs(sessions, exist_ok=True)
        with open(os.path.join(sessions, "s.json"), "w") as f:
            json.dump({"files": self.edited, "attempts": 0}, f)
        env = dict(os.environ, HOME=self.home,
                   CLAUDE_HOOK_DECISION_LOG=os.path.join(self.home, "decisions.jsonl"))
        for k in ("AI_SDLC_NESTED", "AI_SDLC_STOP_CHECKS"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, SCRIPT], input=json.dumps({"session_id": "s", "cwd": self.repo}),
                           capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        return json.loads(p.stdout) if p.stdout.strip() else None

    def test_without_checks_json_nothing_runs_for_other_stacks(self):
        self.assertIsNone(self.run_hook())

    def test_passing_checks_run_from_the_repo_root_and_report_green(self):
        self.write_checks({"lint": "pwd > ran.txt", "test": "true"})
        out = self.run_hook()
        self.assertIn("ai-sdlc ✓", out["systemMessage"])
        self.assertIn("lint", out["systemMessage"])
        self.assertIn("test", out["systemMessage"])
        with open(os.path.join(self.repo, "ran.txt")) as f:
            self.assertEqual(os.path.realpath(f.read().strip()), self.repo)

    def test_checks_run_once_per_repo(self):
        self.edited.append(self.touch("pkg/other.py"))
        self.write_checks({"count": "echo x >> runs.txt"})
        self.run_hook()
        with open(os.path.join(self.repo, "runs.txt")) as f:
            self.assertEqual(f.read().count("x"), 1)

    def test_a_block_is_logged_with_check_names_but_no_output(self):
        self.write_checks({"lint": "true", "test": "echo 'FAILED test_thing'; exit 1"})
        self.run_hook()
        with open(os.path.join(self.home, "decisions.jsonl")) as f:
            entry = json.loads(f.read())
        self.assertEqual((entry["hook"], entry["decision"], entry["repo"]), ("stop_check", "block", "repo"))
        self.assertIn("test", entry["reason"])
        self.assertNotIn("FAILED test_thing", entry["reason"])

    def test_green_runs_are_not_logged(self):
        self.write_checks({"test": "true"})
        self.run_hook()
        self.assertFalse(os.path.exists(os.path.join(self.home, "decisions.jsonl")))

    def test_a_red_check_blocks_with_its_name_and_output(self):
        self.write_checks({"lint": "true", "test": "echo 'FAILED test_thing'; exit 1"})
        out = self.run_hook()
        self.assertEqual(out["decision"], "block")
        self.assertIn("test", out["reason"])
        self.assertIn("FAILED test_thing", out["reason"])

    def test_a_timeout_warns_and_does_not_block(self):
        self.write_checks({"slow": {"command": "sleep 30", "timeout": 1}})
        started = time.time()
        out = self.run_hook()
        self.assertLess(time.time() - started, 20)
        self.assertNotIn("decision", out)
        self.assertIn("⚠", out["systemMessage"])
        self.assertIn("slow", out["systemMessage"])

    def test_an_environment_error_warns_and_does_not_block(self):
        self.write_checks({"test": "echo 'could not connect to server: Connection refused' >&2; exit 1"})
        out = self.run_hook()
        self.assertNotIn("decision", out)
        self.assertIn("⚠", out["systemMessage"])

    def make_ruby_repo(self):
        """A Gemfile and a bin/rubocop binstub that only records that it ran."""
        self.touch("Gemfile")
        os.makedirs(os.path.join(self.repo, "bin"))
        binstub = os.path.join(self.repo, "bin", "rubocop")
        with open(binstub, "w") as f:
            f.write("#!/bin/sh\ntouch rubocop-ran\n")
        os.chmod(binstub, 0o755)
        os.makedirs(os.path.join(self.repo, "app"))
        self.edited = [self.touch("app/x.rb")]
        return os.path.join(self.repo, "rubocop-ran")

    def test_checks_json_replaces_the_built_in_checks(self):
        marker = self.make_ruby_repo()
        self.write_checks({"test": "true"})
        self.run_hook()
        self.assertFalse(os.path.exists(marker))

    def test_without_checks_json_the_built_in_checks_run(self):
        marker = self.make_ruby_repo()
        self.run_hook()
        self.assertTrue(os.path.exists(marker))

    def test_an_unusable_checks_json_warns_and_falls_back_to_the_built_in_checks(self):
        marker = self.make_ruby_repo()
        self.write_checks("{not json")
        out = self.run_hook()
        self.assertNotIn("decision", out)
        self.assertIn("checks.json", out["systemMessage"])
        self.assertTrue(os.path.exists(marker))


    # checks.json trust: a repo's commands run only when the user approved this exact file content.

    def test_untrusted_checks_json_commands_do_not_run(self):
        self.write_checks({"lint": "touch ran.txt"}, trusted=False)
        self.run_hook()
        self.assertFalse(os.path.exists(os.path.join(self.repo, "ran.txt")))

    def test_untrusted_checks_json_warns_with_the_file_and_the_trust_command(self):
        self.write_checks({"lint": "true"}, trusted=False)
        out = self.run_hook()
        self.assertIn("⚠", out["systemMessage"])
        self.assertIn(os.path.join(self.repo, ".claude", "checks.json"), out["systemMessage"])
        self.assertIn("! ~/.claude/hooks/ai-sdlc/trust-checks", out["systemMessage"])

    def test_an_untrusted_failing_check_does_not_block(self):
        self.write_checks({"test": "echo 'FAILED test_thing'; exit 1"}, trusted=False)
        out = self.run_hook()
        self.assertNotIn("decision", out)

    def test_untrusted_checks_json_falls_back_to_the_built_in_checks(self):
        marker = self.make_ruby_repo()
        self.write_checks({"test": "true"}, trusted=False)
        self.run_hook()
        self.assertTrue(os.path.exists(marker))

    def test_a_changed_checks_json_is_untrusted_until_trusted_again(self):
        self.write_checks({"lint": "true"})
        self.write_checks({"lint": "touch ran.txt"}, trusted=False)
        out = self.run_hook()
        self.assertFalse(os.path.exists(os.path.join(self.repo, "ran.txt")))
        self.assertIn("trust-checks", out["systemMessage"])

    def test_trust_recorded_for_another_repo_does_not_apply(self):
        self.write_checks({"lint": "touch ran.txt"}, trusted=False)
        self.trust(os.path.join(self.home, "other-repo"), self.checks_sha())
        self.run_hook()
        self.assertFalse(os.path.exists(os.path.join(self.repo, "ran.txt")))

    def test_a_corrupt_trust_store_counts_as_untrusted(self):
        self.write_checks({"lint": "touch ran.txt"}, trusted=False)
        os.makedirs(os.path.dirname(self.trust_store()), exist_ok=True)
        with open(self.trust_store(), "w") as f:
            f.write("{not json")
        out = self.run_hook()
        self.assertFalse(os.path.exists(os.path.join(self.repo, "ran.txt")))
        self.assertIn("trust-checks", out["systemMessage"])

    def test_trusted_checks_json_runs_chained_shell_commands(self):
        self.write_checks({"lint": "echo a > ran.txt && echo b >> ran.txt"})
        self.run_hook()
        with open(os.path.join(self.repo, "ran.txt")) as f:
            self.assertEqual(f.read().split(), ["a", "b"])

if __name__ == "__main__":
    unittest.main()
