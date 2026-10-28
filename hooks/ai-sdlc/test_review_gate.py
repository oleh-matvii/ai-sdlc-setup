"""Unit tests for review_gate.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_gate  # noqa: E402


class GatedCommandTest(unittest.TestCase):
    def assert_gated(self, *commands):
        for cmd in commands:
            with self.subTest(cmd=cmd):
                self.assertTrue(review_gate.gated_command(cmd))

    def assert_not_gated(self, *commands):
        for cmd in commands:
            with self.subTest(cmd=cmd):
                self.assertFalse(review_gate.gated_command(cmd))

    def test_plain_push_and_pr_commands_are_gated(self):
        self.assert_gated("git push", "git push origin feat/x", "git push -u origin HEAD", "git\tpush",
                          "FOO=1 git push", "gh pr create --fill", "gh  pr   create", "gh pr ready")

    def test_push_after_separators_is_gated(self):
        self.assert_gated("cd ~/src/app && git push", "git status; git push", "true || git push",
                          "git fetch & git push", "git log | git push")

    def test_push_followed_by_punctuation_is_gated(self):
        self.assert_gated("(git push)", "git push;", "git push; echo done", "git push&& echo ok",
                          "git push|tee out", "git push 2>&1|cat", "git push > /tmp/log 2>&1",
                          "gh pr create;", "(cd app && gh pr create)")

    def test_push_inside_a_quoted_shell_command_is_gated(self):
        self.assert_gated("bash -c 'git push'", 'sh -c "git push origin x"', "zsh -c 'gh pr ready'")

    def test_other_git_and_gh_commands_are_not_gated(self):
        self.assert_not_gated("git status", "git log --grep push", "gh pr view 12", "gh pr list",
                              "echo git-push", "mygit push", "git push-mirror", "git pushd")

    def test_push_that_needs_no_review_is_not_gated(self):
        self.assert_not_gated("git push --delete origin old", "git push -d origin old", "git push --tags",
                              "git push origin --delete old", "git push origin --tags; echo ok")

    def test_no_review_flags_elsewhere_in_the_command_do_not_skip_the_gate(self):
        self.assert_gated("git branch -d old && git push", "ls -d dir; git push",
                          "git push && git push --tags", "git push; git tag --delete v1")


class CommitRegexTest(unittest.TestCase):
    def test_commit_in_a_compound_command_is_found(self):
        for cmd in ("git commit -m x && git push", "git commit -m 'x'; git push", "git commit&&git push",
                    "(git commit -m x) && gh pr create", "git commit"):
            with self.subTest(cmd=cmd):
                self.assertTrue(review_gate.COMMIT_RE.search(cmd))

    def test_other_commands_are_not_commits(self):
        for cmd in ("git commit-tree abc", "git log --grep commit", "git push"):
            with self.subTest(cmd=cmd):
                self.assertFalse(review_gate.COMMIT_RE.search(cmd))


class CheckUserOnlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"CLAUDE_HOOK_DECISION_LOG": os.path.join(self.tmp.name, "decisions.jsonl")}

    def tearDown(self):
        self.tmp.cleanup()

    def decision(self, cmd):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, self.env):
            try:
                review_gate.check_user_only(cmd)
            except SystemExit:
                pass
        return json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] if out.getvalue() else None

    def assert_denied(self, *commands):
        for cmd in commands:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decision(cmd), "deny")

    def assert_allowed(self, *commands):
        for cmd in commands:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.decision(cmd))

    def test_switching_the_safety_switches_off_is_denied(self):
        self.assert_denied("~/.claude/hooks/ai-sdlc/review-gate skip", "review-gate off", "review-gate on",
                           "cd x && review-gate skip", "(review-gate on)", "bash -c 'review-gate off'",
                           "'/Users/me/.claude/hooks/ai-sdlc/review-gate' skip")

    def test_trusting_a_repos_checks_json_is_user_only(self):
        self.assert_denied("~/.claude/hooks/ai-sdlc/trust-checks", "trust-checks /path/to/repo",
                           "cd repo && trust-checks", "bash -c 'trust-checks'",
                           "python3 ~/.claude/hooks/ai-sdlc/trust-checks .",
                           "'/Users/me/.claude/hooks/ai-sdlc/trust-checks' /repo")

    def test_mentioning_trust_checks_without_running_it_is_allowed(self):
        self.assert_allowed("cat ~/.claude/hooks/ai-sdlc/trust-checks", "grep -n trust-checks README.md",
                            "git log -- hooks/ai-sdlc/trust-checks")

    def test_read_only_commands_are_allowed(self):
        self.assert_allowed("~/.claude/hooks/ai-sdlc/review-gate status", "~/.claude/hooks/ai-sdlc/chain-status --md",
                            "git push")

    def test_writes_to_the_state_dir_are_denied(self):
        self.assert_denied("touch ~/.claude/state/ai-sdlc/stop-checks-off",
                           "rm -f ~/.claude/state/ai-sdlc/review-gate-off",
                           "echo x > ~/.claude/state/ai-sdlc/review-gate-off",
                           "echo x >> ~/.claude/state/ai-sdlc/x",
                           "echo x>~/.claude/state/ai-sdlc/x",
                           "sed -i '' s/a/b/ ~/.claude/state/ai-sdlc/chain/x.json",
                           "echo x | tee ~/.claude/state/ai-sdlc/x",
                           "mv /tmp/x ~/.claude/state/ai-sdlc/x",
                           "ln -s /tmp/x ~/.claude/state/ai-sdlc/x")

    def test_copies_into_the_state_dir_are_denied(self):
        self.assert_denied("cp /tmp/x ~/.claude/state/ai-sdlc/trusted-checks.json",
                           "cp -f /tmp/x ~/.claude/state/ai-sdlc/",
                           "cp /tmp/x ~/.claude/state/ai-sdlc/x && echo ok",
                           "cp -t ~/.claude/state/ai-sdlc /tmp/x",
                           "install -m 600 /tmp/x ~/.claude/state/ai-sdlc/trusted-checks.json",
                           "install -t ~/.claude/state/ai-sdlc /tmp/x")

    def test_copies_out_of_the_state_dir_are_allowed(self):
        self.assert_allowed("cp ~/.claude/state/ai-sdlc/chain/x.json /tmp/out",
                            "cp ~/.claude/state/ai-sdlc/x /tmp/out && cat /tmp/out")

    def test_reads_of_the_state_dir_are_allowed(self):
        self.assert_allowed("ls ~/.claude/state/ai-sdlc", "cat ~/.claude/state/ai-sdlc/chain/x.json",
                            "ls ~/.claude/state/ai-sdlc 2>/dev/null", "cat ~/.claude/state/ai-sdlc/x > /tmp/out")

    def test_a_denied_switch_is_logged_without_the_command(self):
        self.decision("~/.claude/hooks/ai-sdlc/review-gate skip --secret-arg")
        with open(self.env["CLAUDE_HOOK_DECISION_LOG"]) as f:
            entry = json.loads(f.read())
        self.assertEqual((entry["hook"], entry["decision"], entry["tool"]), ("review_gate", "deny", "Bash"))
        self.assertNotIn("secret-arg", entry["reason"])


class GateProcessTest(unittest.TestCase):
    """Runs review_gate.py as the hook runs it, with HOME in a temp dir; stops before any agent runs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.home, "app")
        os.makedirs(self.repo)
        self.log = os.path.join(self.home, "decisions.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo, "-c", "user.email=t@example.com", "-c", "user.name=t"] + list(args),
                       check=True, capture_output=True)

    def write(self, rel, text="x\n"):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def run_gate(self, cmd):
        env = dict(os.environ, HOME=self.home, CLAUDE_HOOK_DECISION_LOG=self.log)
        for k in ("AI_SDLC_NESTED", "AI_SDLC_REVIEW_GATE"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_gate.py")],
                           input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.repo}),
                           capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else None

    def logged(self):
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    def test_commit_and_push_in_one_command_is_denied_and_logged(self):
        self.git("init", "-q")
        out = self.run_gate("git commit -m 'wip' && git push")
        self.assertEqual(out["permissionDecision"], "deny")
        [entry] = self.logged()
        self.assertEqual((entry["hook"], entry["decision"], entry["repo"]), ("review_gate", "deny", "app"))
        self.assertNotIn("wip", entry["reason"])

    def test_tdd_violation_is_denied_and_logged_before_any_agent_runs(self):
        self.git("init", "-q", "-b", "main")
        self.write("README.md")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")
        self.git("checkout", "-q", "-b", "feat/x")
        self.write("app/models/x.rb", "class X; end\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "code without tests")
        out = self.run_gate("git push -u origin feat/x")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("app/models/x.rb", out["permissionDecisionReason"])
        [entry] = self.logged()
        self.assertEqual((entry["hook"], entry["decision"], entry["tool"], entry["repo"]),
                         ("review_gate", "deny", "Bash", "app"))
        self.assertIn("tdd", entry["reason"])


class BranchTypeTest(unittest.TestCase):
    def test_prefixes_map_to_types(self):
        for branch, expected in (("feat/x", "feat"), ("feature/x", "feat"), ("enh/x", "enh"),
                                 ("improve/x", "enh"), ("fix/x", "fix"), ("hotfix/x", "fix"), ("FIX/x", "fix"),
                                 ("refactor/x", "refactor"), ("tech/x", "chore"), ("chore/x", "chore"),
                                 ("dependabot/npm/x", "chore"), ("docs/x", "chore")):
            with self.subTest(branch=branch):
                self.assertEqual(review_gate.branch_type(branch), expected)

    def test_unknown_or_missing_prefix_is_none(self):
        for branch in ("main", "HEAD", "feat-x", "user/feat-x", ""):
            with self.subTest(branch=branch):
                self.assertIsNone(review_gate.branch_type(branch))


class SpecRepo(unittest.TestCase):
    """A temp git repo with a main branch; helpers to commit docs on a feature branch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.commit({"README.md": "x\n"}, "init")
        self.base = self.rev("HEAD")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", self.root] + list(args), check=True, capture_output=True,
                              text=True).stdout.strip()

    def rev(self, ref):
        return self.git("rev-parse", ref)

    def commit(self, files, msg="docs"):
        for rel, text in files.items():
            os.makedirs(os.path.join(self.root, os.path.dirname(rel)), exist_ok=True)
            with open(os.path.join(self.root, rel), "w") as f:
                f.write(text)
        self.git("add", ".")
        self.git("commit", "-q", "-m", msg)

    def collect(self, branch="feat/x"):
        return review_gate.collect(self.root, branch, self.base, self.rev("HEAD"))


SPEC = "docs/specs/2026-10-28-order-export/spec.md"
TASKS = "docs/specs/2026-10-28-order-export/tasks.md"


class SpecHeaderTest(SpecRepo):
    def test_bold_markdown_header_of_a_spec_is_read(self):
        self.commit({SPEC: "**Type:** fix\n**Size:** M\n**Status:** Approved\n\n# Spec\n"})
        self.assertEqual(review_gate.spec_header(self.root, "HEAD", [SPEC]), ("fix", "M"))

    def test_tech_type_is_read_as_chore_like_the_tech_branch_prefix(self):
        self.commit({SPEC: "**Type:** tech\n**Size:** L\n\n# Port hooks\n"})
        self.assertEqual(review_gate.spec_header(self.root, "HEAD", [SPEC]), ("chore", "L"))

    def test_plain_header_and_case(self):
        self.commit({SPEC: "type: Refactor\nsize: xl\n"})
        self.assertEqual(review_gate.spec_header(self.root, "HEAD", [SPEC]), ("refactor", "XL"))

    def test_no_header_gives_none(self):
        self.commit({SPEC: "# Spec\n\nThe type of change is small.\n"})
        self.assertEqual(review_gate.spec_header(self.root, "HEAD", [SPEC]), (None, None))


class CollectSpecDocsTest(SpecRepo):
    def test_spec_and_tasks_of_the_branch_are_found_and_the_header_read(self):
        self.git("checkout", "-q", "-b", "feat/x")
        self.commit({SPEC: "**Type:** enh\n**Size:** L\n", TASKS: "- [ ] 1. a (covers: AC1)\n",
                     "docs/specs/2026-10-28-order-export/research.md": "**Type:** fix\n**Size:** S\n"})
        info = self.collect()
        self.assertEqual((info["specs"], info["task_docs"]), ([SPEC], [TASKS]))
        self.assertEqual((info["type"], info["size"], info["size_src"]), ("enh", "L", "spec"))
        self.assertNotIn("plans", info)

    def test_only_tasks_changed_uses_the_spec_next_to_them(self):
        self.commit({SPEC: "**Type:** enh\n**Size:** L\n", TASKS: "- [ ] 1. a\n"}, "approved spec")
        self.base = self.rev("HEAD")
        self.git("checkout", "-q", "-b", "feat/x")
        self.commit({TASKS: "- [x] 1. a\n", "app/x.rb": "1\n", "spec/x_spec.rb": "1\n"}, "task 1")
        info = self.collect()
        self.assertEqual((info["specs"], info["task_docs"]), ([SPEC], [TASKS]))
        self.assertEqual((info["type"], info["size"]), ("enh", "L"))

    def test_legacy_superpowers_spec_and_plan_are_still_accepted(self):
        self.git("checkout", "-q", "-b", "feat/x")
        self.commit({"docs/superpowers/specs/2026-01-01-x-design.md": "# Design\n",
                     "docs/superpowers/plans/2026-01-01-x.md": "**Type:** refactor\n**Size:** M\n"})
        info = self.collect()
        self.assertEqual(info["specs"], ["docs/superpowers/specs/2026-01-01-x-design.md"])
        self.assertEqual(info["task_docs"], ["docs/superpowers/plans/2026-01-01-x.md"])
        self.assertEqual((info["type"], info["size"], info["size_src"]), ("refactor", "M", "spec"))

    def test_no_spec_falls_back_to_branch_and_diff(self):
        self.git("checkout", "-q", "-b", "fix/x")
        self.commit({"app/x.rb": "1\n"})
        info = self.collect("fix/x")
        self.assertEqual((info["specs"], info["task_docs"]), ([], []))
        self.assertEqual((info["type"], info["size"], info["size_src"]), ("fix", "S", "diff"))


class AgentPromptTest(unittest.TestCase):
    def info(self, **kw):
        base = {"files": [SPEC, TASKS, "app/x.rb"], "lines": 10, "type": "feat", "size": "L", "size_src": "spec",
                "review_md": False, "claude_md": False, "specs": [SPEC], "task_docs": [TASKS]}
        base.update(kw)
        return base

    def prompt(self, name, info):
        with mock.patch.object(review_gate.learn_log, "known_classes", return_value=[]):
            return review_gate.agent_prompt(name, "/repo", "feat/x", "b" * 40, "h" * 40, info)

    def test_spec_and_tasks_paths_go_to_both_agents(self):
        for name in ("code-reviewer", "acceptance-checker"):
            with self.subTest(name=name):
                text = self.prompt(name, self.info())
                self.assertIn("spec docs in this branch: " + SPEC, text)
                self.assertIn("tasks docs in this branch: " + TASKS, text)
                self.assertNotIn("plan", text.lower())

    def test_missing_docs_are_named_none(self):
        text = self.prompt("acceptance-checker", self.info(specs=[], task_docs=[]))
        self.assertIn("spec docs in this branch: none", text)
        self.assertIn("tasks docs in this branch: none", text)

    def test_no_lock_state_goes_to_the_agents(self):
        for name in ("code-reviewer", "acceptance-checker"):
            with self.subTest(name=name):
                self.assertNotIn("test lock", self.prompt(name, self.info()).lower())


class ChainLineTest(unittest.TestCase):
    REVIEW = {"verdict": "approve", "findings": []}

    def info(self, ttype="feat", size="M", specs=(), task_docs=(), tests=("spec/x_spec.rb",)):
        return {"type": ttype, "size": size, "specs": list(specs), "task_docs": list(task_docs),
                "tests": list(tests)}

    def line(self, info, accept=None):
        return review_gate.chain_line("feat/x", "abcdef123", info, self.REVIEW, accept)

    def test_feat_m_with_spec_and_aligned_design(self):
        line = self.line(self.info(specs=[SPEC]), {"status": "ready", "design_alignment": "matches"})
        self.assertIn("✓spec", line)
        self.assertIn("✓design-aligned", line)
        self.assertNotIn("plan", line)
        self.assertNotIn("tasks", line)

    def test_feat_l_needs_tasks(self):
        self.assertIn("✗tasks", self.line(self.info(size="L", specs=[SPEC])))
        self.assertIn("✓tasks", self.line(self.info(size="L", specs=[SPEC], task_docs=[TASKS])))

    def test_missing_spec_on_feat_enh_m_is_marked(self):
        for ttype in ("feat", "enh"):
            with self.subTest(ttype=ttype):
                self.assertIn("✗spec", self.line(self.info(ttype=ttype)))

    def test_routes_without_a_spec_do_not_mark_it(self):
        for ttype, size in (("fix", "M"), ("refactor", "L"), ("chore", "M"), ("feat", "S")):
            with self.subTest(ttype=ttype, size=size):
                line = self.line(self.info(ttype=ttype, size=size))
                self.assertNotIn("spec", line.split(": ", 1)[1])
                self.assertNotIn("tasks", line.split(": ", 1)[1])

    def test_diverged_design_is_marked(self):
        line = self.line(self.info(specs=[SPEC]), {"status": "not_ready", "design_alignment": "diverged"})
        self.assertIn("✗design-aligned", line)

    def test_no_spec_alignment_adds_nothing(self):
        line = self.line(self.info(ttype="fix"), {"status": "ready", "design_alignment": "no_spec"})
        self.assertNotIn("aligned", line)


class AcceptanceSchemaTest(unittest.TestCase):
    def test_design_alignment_replaces_plan_alignment(self):
        props = review_gate.ACCEPT_SCHEMA["properties"]
        self.assertEqual(props["design_alignment"]["enum"], ["matches", "updated", "diverged", "no_spec"])
        self.assertIn("design_alignment", review_gate.ACCEPT_SCHEMA["required"])
        self.assertNotIn("plan_alignment", props)

    def test_rendered_report_names_the_design_alignment(self):
        text = review_gate.render_accept({"status": "ready", "criteria_source": "spec", "summary": "s",
                                          "design_alignment": "updated",
                                          "criteria": [{"criterion": "AC1 x", "status": "done", "evidence": "e"}]})
        self.assertIn("design: updated", text)
        self.assertNotIn("plan", text)


class TddViolationTest(unittest.TestCase):
    def info(self, ttype, code=(), tests=(), touched=()):
        return {"type": ttype, "code": list(code), "tests": list(tests), "tests_touched": list(touched)}

    def test_code_without_tests_is_a_violation_for_feat_enh_fix(self):
        for ttype in ("feat", "enh", "fix"):
            with self.subTest(ttype=ttype):
                msg = review_gate.tdd_violation(self.info(ttype, code=["app/models/x.rb"]))
                self.assertIn("app/models/x.rb", msg)

    def test_code_with_tests_passes(self):
        self.assertIsNone(review_gate.tdd_violation(
            self.info("feat", code=["app/x.rb"], tests=["spec/x_spec.rb"])))

    def test_chore_and_unknown_types_need_no_tests(self):
        for ttype in ("chore", "unknown"):
            with self.subTest(ttype=ttype):
                self.assertIsNone(review_gate.tdd_violation(self.info(ttype, code=["app/x.rb"])))

    def test_refactor_touching_existing_tests_is_a_violation(self):
        msg = review_gate.tdd_violation(self.info("refactor", code=["app/x.rb"], tests=["spec/x_spec.rb"],
                                                  touched=["spec/x_spec.rb"]))
        self.assertIn("spec/x_spec.rb", msg)

    def test_refactor_adding_new_tests_passes(self):
        self.assertIsNone(review_gate.tdd_violation(
            self.info("refactor", code=["app/x.rb"], tests=["spec/new_spec.rb"])))


if __name__ == "__main__":
    unittest.main()
