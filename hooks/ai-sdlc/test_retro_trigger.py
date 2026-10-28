"""Unit tests for retro_trigger.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retro_trigger  # noqa: E402

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retro_trigger.py")
PR_URL = "https://github.com/acme/app/pull/42"


class PrCreateCommandTest(unittest.TestCase):
    def test_gh_pr_create_shapes_review_gate_recognises_are_pr_creates(self):
        for cmd in ("gh pr create --fill", "gh  pr   create", "cd app && gh pr create --title x",
                    "(cd app && gh pr create)", "bash -c 'gh pr create --fill'", "gh pr create;",
                    "git status; gh pr create --draft"):
            with self.subTest(cmd=cmd):
                self.assertTrue(retro_trigger.is_pr_create(cmd))

    def test_other_commands_are_not_pr_creates(self):
        for cmd in ("gh pr view 42", "gh pr ready", "git push -u origin HEAD", "gh pr list",
                    "gh pr createx", "mygh pr create", ""):
            with self.subTest(cmd=cmd):
                self.assertFalse(retro_trigger.is_pr_create(cmd))


class PrUrlTest(unittest.TestCase):
    def test_finds_the_pr_url_in_bash_stdout(self):
        self.assertEqual(retro_trigger.pr_url({"stdout": "Creating pull request\n%s\n" % PR_URL, "stderr": ""}),
                         PR_URL)

    def test_accepts_a_plain_string_response(self):
        self.assertEqual(retro_trigger.pr_url("Creating pull request\n%s\n" % PR_URL), PR_URL)

    def test_a_url_inside_other_output_is_not_a_created_pr(self):
        for stdout in ("> see %s for details\n" % PR_URL, "merged in %s" % PR_URL):
            with self.subTest(stdout=stdout):
                self.assertIsNone(retro_trigger.pr_url({"stdout": stdout}))

    def test_no_url_interrupted_or_new_pr_link_is_none(self):
        for resp in ({"stdout": "", "stderr": "aborted: you must first push the current branch"},
                     {"stdout": PR_URL, "interrupted": True},
                     {"stdout": "https://github.com/acme/app/pull/new/feat/x"},
                     {"stdout": "", "stderr": PR_URL},
                     None, 42, []):
            with self.subTest(resp=resp):
                self.assertIsNone(retro_trigger.pr_url(resp))


class RetroTriggerProcessTest(unittest.TestCase):
    """Runs retro_trigger.py as the hook runs it, with HOME in a temp dir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "app")
        os.makedirs(self.repo)
        self.log = os.path.join(self.home, "decisions.jsonl")
        self.retro_dir = os.path.join(self.home, ".claude", "state", "ai-sdlc", "retro")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo, "-c", "user.email=t@example.com", "-c", "user.name=t"] + list(args),
                       check=True, capture_output=True)

    def init_repo(self, branch="fix/proj-1-total"):
        self.git("init", "-q", "-b", "main")
        self.git("commit", "-q", "--allow-empty", "-m", "init")
        self.git("checkout", "-q", "-b", branch)

    def payload(self, cmd="gh pr create --fill", stdout=PR_URL + "\n", **extra):
        data = {"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": self.repo,
                "tool_input": {"command": cmd, "description": "Create PR"},
                "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False, "isImage": False}}
        data.update(extra)
        return json.dumps(data)

    def run_hook(self, stdin, env_extra=None):
        env = dict(os.environ, HOME=self.home, CLAUDE_HOOK_DECISION_LOG=self.log)
        env.pop("AI_SDLC_NESTED", None)
        env.update(env_extra or {})
        p = subprocess.run([sys.executable, HOOK], input=stdin, capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        return json.loads(p.stdout) if p.stdout.strip() else None

    def logged(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    def test_successful_pr_create_asks_the_main_conversation_to_run_retro(self):
        self.init_repo()
        out = self.run_hook(self.payload())
        spec = out["hookSpecificOutput"]
        self.assertEqual(spec["hookEventName"], "PostToolUse")
        ctx = spec["additionalContext"]
        self.assertIn(PR_URL, ctx)
        self.assertIn("`retro` skill", ctx)
        self.assertIn("ok", ctx)
        self.assertNotIn("decision", out)

    def test_firing_is_remembered_per_repo_and_branch(self):
        self.init_repo()
        self.run_hook(self.payload())
        self.assertTrue(os.path.isdir(self.retro_dir))
        [state_file] = [os.path.join(d, f) for d, _, fs in os.walk(self.retro_dir) for f in fs]
        self.assertEqual(os.path.basename(state_file), "fix_proj-1-total.json")
        with open(state_file) as f:
            self.assertEqual(json.load(f)["pr"], PR_URL)

    def test_retry_or_second_pr_on_the_same_branch_is_silent(self):
        self.init_repo()
        self.assertIsNotNone(self.run_hook(self.payload()))
        self.assertIsNone(self.run_hook(self.payload()))
        self.assertIsNone(self.run_hook(self.payload(stdout="https://github.com/acme/app/pull/43\n")))

    def test_a_pr_from_another_branch_fires_again(self):
        self.init_repo()
        self.run_hook(self.payload())
        self.git("checkout", "-q", "-b", "fix/proj-2-other")
        out = self.run_hook(self.payload(stdout="https://github.com/acme/app/pull/43\n"))
        self.assertIn("https://github.com/acme/app/pull/43", out["hookSpecificOutput"]["additionalContext"])

    def test_outside_a_git_repo_it_fires_once_per_pr(self):
        self.assertIsNotNone(self.run_hook(self.payload()))
        self.assertIsNone(self.run_hook(self.payload()))

    def test_failed_pr_create_without_a_url_is_silent(self):
        self.init_repo()
        self.assertIsNone(self.run_hook(self.payload(stdout="")))
        self.assertIsNone(self.run_hook(self.payload(
            tool_response={"stdout": "", "stderr": "a pull request for branch already exists:\n%s\n" % PR_URL,
                           "interrupted": False, "isImage": False})))
        self.assertFalse(os.path.exists(self.retro_dir))

    def test_other_commands_are_silent_even_with_a_pr_url_in_the_output(self):
        self.init_repo()
        for cmd, stdout in (("gh pr view 42 --json url -q .url", PR_URL),
                            ("git push -u origin HEAD", "https://github.com/acme/app/pull/new/fix/proj-1-total"),
                            ("echo gh pr create", "gh pr create")):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.run_hook(self.payload(cmd=cmd, stdout=stdout)))
        self.assertFalse(os.path.exists(self.retro_dir))

    def test_malformed_input_is_silent(self):
        for stdin in ("", "not json", "[]", json.dumps({"tool_input": "gh pr create"}),
                      json.dumps({"tool_input": {"command": "gh pr create"}}),
                      json.dumps({"tool_input": {"command": "gh pr create"}, "tool_response": {"stdout": 7}})):
            with self.subTest(stdin=stdin):
                self.assertIsNone(self.run_hook(stdin))

    def test_inside_a_subagent_it_is_silent_and_remembers_nothing(self):
        self.init_repo()
        self.assertIsNone(self.run_hook(self.payload(agent_id="a1", agent_type="feature-implementer")))
        self.assertFalse(os.path.exists(self.retro_dir))
        self.assertIsNotNone(self.run_hook(self.payload()))

    def test_nested_review_sessions_are_silent(self):
        self.init_repo()
        self.assertIsNone(self.run_hook(self.payload(), {"AI_SDLC_NESTED": "1"}))

    def test_unwritable_state_fails_open(self):
        self.init_repo()
        os.makedirs(os.path.dirname(self.retro_dir))
        open(self.retro_dir, "w").close()
        self.assertIsNone(self.run_hook(self.payload()))

    def test_firing_is_logged_without_the_command_or_url(self):
        self.init_repo()
        self.run_hook(self.payload(cmd="gh pr create --title 'secret-title'"))
        self.run_hook(self.payload(cmd="gh pr create --title 'secret-title'"))
        [entry] = self.logged()
        self.assertEqual((entry["hook"], entry["decision"], entry["tool"], entry["repo"]),
                         ("retro_trigger", "context", "Bash", "app"))
        self.assertNotIn("secret-title", entry["reason"])
        self.assertNotIn("github.com", entry["reason"])


if __name__ == "__main__":
    unittest.main()
