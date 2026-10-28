"""Unit tests for secret_guard.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS_DIR)
import hook_decision_log  # noqa: E402
import secret_guard  # noqa: E402

SCRIPT = os.path.join(HOOKS_DIR, "secret_guard.py")
SYSTEM_PYTHON = "/usr/bin/python3"
HOME = "/fake/home"
PROJECT = "/fake/project"
SETTINGS = HOME + "/.claude/settings.json"
LOCAL_SETTINGS = HOME + "/.claude/settings.local.json"
PRINTING_PROGRAMS = frozenset((
    "cat", "head", "tail", "less", "more", "bat", "grep", "rg", "sed",
    "awk", "jq", "strings", "xxd", "base64",
))


def call(tool, tool_input, cwd=PROJECT):
    return {"cwd": cwd, "tool_name": tool, "tool_input": tool_input}


def file_reason(tool, path, key="file_path", cwd=PROJECT):
    return secret_guard.secret_access_reason(call(tool, {key: path}, cwd), HOME)


def bash_reason(command, cwd=PROJECT):
    return secret_guard.secret_access_reason(call("Bash", {"command": command}, cwd), HOME)


class StateDirWriteTest(unittest.TestCase):
    """~/.claude/state/ai-sdlc holds the user's switches and checks.json trust: file-tool writes ask."""
    STATE = HOME + "/.claude/state/ai-sdlc"

    def test_writing_tools_targeting_the_state_dir_ask(self):
        for tool, path in (("Write", self.STATE + "/trusted-checks.json"), ("Edit", self.STATE + "/chain/x.json"),
                           ("MultiEdit", "~/.claude/state/ai-sdlc/x"), ("Write", "$HOME/.claude/state/ai-sdlc/x"),
                           ("Write", self.STATE + "/../ai-sdlc/x")):
            with self.subTest(tool=tool, path=path):
                self.assertIsNotNone(file_reason(tool, path))
        self.assertIsNotNone(file_reason("NotebookEdit", self.STATE + "/x.ipynb", key="notebook_path"))
        self.assertIsNotNone(file_reason("Write", "state/ai-sdlc/x", cwd=HOME + "/.claude"))

    def test_reading_the_state_dir_does_not_ask(self):
        for tool in ("Read", "Grep", "Glob"):
            with self.subTest(tool=tool):
                self.assertIsNone(file_reason(tool, self.STATE + "/chain/x.json",
                                              key="file_path" if tool == "Read" else "path"))

    def test_writing_next_to_the_state_dir_does_not_ask(self):
        for path in (HOME + "/.claude/state/other.json", HOME + "/.claude/state/ai-sdlc-notes/x",
                     PROJECT + "/.claude/state/ai-sdlc/x"):
            with self.subTest(path=path):
                self.assertIsNone(file_reason("Write", path))


class SecretFileToolTest(unittest.TestCase):
    def test_read_of_env_file_asks_and_names_it(self):
        reason = file_reason("Read", PROJECT + "/.env")
        self.assertIn(".env", reason)
        self.assertIn("secret", reason)

    def test_reason_names_path_and_matched_pattern(self):
        reason = file_reason("Read", PROJECT + "/server.pem")
        self.assertIn(PROJECT + "/server.pem", reason)
        self.assertIn("*.pem", reason)

    def test_every_file_tool_asks_for_a_secret_file(self):
        for tool, key in (("Read", "file_path"), ("Edit", "file_path"), ("Write", "file_path"),
                          ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path"),
                          ("Grep", "path"), ("Glob", "path")):
            with self.subTest(tool=tool):
                self.assertIsNotNone(file_reason(tool, PROJECT + "/.env", key))

    def test_each_secret_name_family_asks(self):
        for name in (".env", ".env.local", ".env.dist", "server.pem", "tls.key", "id_rsa", "id_rsa.pub",
                     "id_rsa_work", "id_ed25519", "id_ed25519.pub", ".netrc", ".npmrc", ".pgpass",
                     "credentials", "credentials.json", "cert.p12"):
            with self.subTest(name=name):
                self.assertIsNotNone(file_reason("Read", PROJECT + "/" + name))

    def test_files_the_old_guard_protected_still_ask(self):
        for path in ("config/master.key", "config/credentials.yml.enc", "config/credentials/production.key",
                     "~/.ssh/config", "~/.ssh/known_hosts", "~/.aws/credentials"):
            with self.subTest(path=path):
                self.assertIsNotNone(file_reason("Edit", path))

    def test_safe_suffixes_and_ordinary_names_pass(self):
        for name in (".env.example", ".env.sample", ".env.template", "tls.key.example",
                     "README.md", "environment.py", "settings.json", "keyboard.rb", "ssh_helper.rb"):
            with self.subTest(name=name):
                self.assertIsNone(file_reason("Read", PROJECT + "/" + name))

    def test_relative_path_resolves_against_cwd(self):
        self.assertIsNotNone(file_reason("Read", "../other/.env"))

    def test_tilde_expands_to_the_given_home(self):
        self.assertIsNotNone(file_reason("Read", "~/.ssh/id_rsa"))

    def test_grep_without_path_or_on_a_directory_passes(self):
        self.assertIsNone(secret_guard.secret_access_reason(call("Grep", {"pattern": "x"}), HOME))
        self.assertIsNone(file_reason("Grep", PROJECT, "path"))

    def test_other_tools_pass(self):
        self.assertIsNone(secret_guard.secret_access_reason(call("WebFetch", {"url": "x/.env"}), HOME))


class BashCommandTest(unittest.TestCase):
    def test_printing_program_with_a_secret_path_asks(self):
        for command in ("cat .env", "head -n 5 ./config/.env.local", "grep KEY .env",
                        "echo hi | base64 id_rsa", "cat .env; ls", "/usr/bin/cat .env", "CAT .env"):
            with self.subTest(command=command):
                self.assertIsNotNone(bash_reason(command))

    def test_every_printing_program_asks(self):
        self.assertEqual(secret_guard.PRINTING_PROGRAMS, PRINTING_PROGRAMS)
        for program in sorted(PRINTING_PROGRAMS):
            with self.subTest(program=program):
                self.assertIsNotNone(bash_reason(program + " .env"))

    def test_command_without_a_printing_program_passes(self):
        for command in ("source .env && npm start", "python3 edit.py ~/.claude/settings.json",
                        "cp ~/.claude/settings.json /tmp/x"):
            with self.subTest(command=command):
                self.assertIsNone(bash_reason(command))

    def test_printing_an_ordinary_file_passes(self):
        self.assertIsNone(bash_reason("cat README.md"))
        self.assertIsNone(bash_reason("cat %s/.env.example" % PROJECT))

    def test_hash_inside_a_word_does_not_hide_the_rest(self):
        self.assertIsNotNone(bash_reason("echo fix#1; cat .env"))
        self.assertIsNotNone(bash_reason("echo issue#12 && cat ~/.claude/settings.json"))

    def test_apostrophe_in_a_trailing_comment_does_not_hide_the_secret(self):
        for command in ("cat .env; # don't print", "cat .env|grep KEY # don't worry",
                        "KEY=$(cat .env) # don't echo it", "(cd ~/.claude && cat settings.json) # user's"):
            with self.subTest(command=command):
                self.assertIsNotNone(bash_reason(command))

    def test_shell_punctuation_separates_words(self):
        for command in ("echo `cat .env`", "KEY=`cat .env`", "cat<.env", 'echo "$(cat .env)"',
                        "cat .env>out", "true&cat .env", "cat .env|wc"):
            with self.subTest(command=command):
                self.assertIsNotNone(bash_reason(command))

    def test_unbalanced_quotes_still_ask(self):
        for command in ("cat '.env", 'cat ".env', "cat .env '", 'cat .env "'):
            with self.subTest(command=command):
                self.assertIsNotNone(bash_reason(command))

    def test_quotes_and_backslashes_inside_a_word_are_removed(self):
        for command in ('cat "$HOME"/.claude/settings.json', 'cat "${HOME}"/.claude/settings.json',
                        'cat "$HOME/.claude"/settings.json', 'cat ~/.claude/"settings.json"',
                        "cat ~/.claude/'settings.json'", 'cd "$HOME"/.claude && cat settings.json',
                        'cat config/".env.local"', "cat config/'.env'", "cat \\.env", "cat .env\\\n| grep K"):
            with self.subTest(command=command):
                self.assertIsNotNone(bash_reason(command))

    def test_word_emptied_by_quote_removal_is_not_a_path(self):
        self.assertIsNone(bash_reason('cat ""', cwd=PROJECT + "/.env"))

    def test_many_directory_changes_are_answered(self):
        self.assertIsNotNone(bash_reason("cd /tmp && " * 300 + "cat .env"))


class ChangeDirectoryTest(unittest.TestCase):
    def test_cd_and_pushd_change_the_base_directory(self):
        for command in ("cd ~/.claude && cat settings.json", "cd -- ~/.claude && cat settings.json",
                        "cd -P ~/.claude && cat settings.json", "pushd ~/.claude && cat settings.json"):
            with self.subTest(command=command):
                self.assertIsNotNone(bash_reason(command))

    def test_cd_to_an_unrelated_directory_passes(self):
        self.assertIsNone(bash_reason("cd /tmp && cat settings.json"))

    def test_relative_cd_target_resolves_against_cwd(self):
        self.assertIsNotNone(bash_reason("cd .claude && cat settings.json", cwd=HOME))

    def test_home_spellings_as_cd_target(self):
        for home in ("$HOME", "${HOME}", "~"):
            with self.subTest(home=home):
                self.assertIsNotNone(bash_reason("cd %s && cat .claude/settings.json" % home))


class ReadProtectedSettingsTest(unittest.TestCase):
    def test_read_grep_and_glob_of_settings_ask(self):
        for path in (SETTINGS, LOCAL_SETTINGS, "~/.claude/settings.json", "$HOME/.claude/settings.json",
                     "${HOME}/.claude/settings.json", "~/.claude/../.claude/settings.json", "/" + SETTINGS):
            with self.subTest(path=path):
                self.assertIsNotNone(file_reason("Read", path))
                self.assertIsNotNone(file_reason("Grep", path, "path"))
                self.assertIsNotNone(file_reason("Glob", path, "path"))

    def test_reason_names_path_and_kind(self):
        reason = file_reason("Read", SETTINGS)
        self.assertIn(SETTINGS, reason)
        self.assertIn("protected settings file", reason)

    def test_editing_settings_passes(self):
        for tool, key in (("Edit", "file_path"), ("Write", "file_path"), ("MultiEdit", "file_path"),
                          ("NotebookEdit", "notebook_path")):
            for path in (SETTINGS, LOCAL_SETTINGS):
                with self.subTest(tool=tool, path=path):
                    self.assertIsNone(file_reason(tool, path, key))

    def test_relative_settings_path_resolves_against_cwd(self):
        self.assertIsNotNone(file_reason("Read", "settings.json", cwd=HOME + "/.claude"))
        self.assertIsNotNone(bash_reason("cat settings.json", cwd=HOME + "/.claude"))
        self.assertIsNone(file_reason("Read", "settings.json", cwd=HOME + "/other"))

    def test_bash_printing_settings_asks(self):
        self.assertIsNotNone(bash_reason("cat ~/.claude/settings.json"))
        self.assertIsNotNone(bash_reason("jq . " + LOCAL_SETTINGS))
        self.assertIsNotNone(bash_reason('cat "$HOME/.claude/settings.json"'))

    def test_settings_json_elsewhere_is_not_protected(self):
        self.assertIsNone(file_reason("Read", PROJECT + "/.claude/settings.json"))
        self.assertIsNone(bash_reason("cat other/settings.json"))
        self.assertIsNone(file_reason("Read", "$HOME/other/settings.json"))
        self.assertIsNone(file_reason("Read", "$HOME"))

    def test_matching_is_case_insensitive(self):
        self.assertIsNotNone(file_reason("Read", HOME + "/.claude/Settings.json"))
        self.assertIsNotNone(bash_reason("cat %s/.CLAUDE/settings.LOCAL.json" % HOME))
        for name in (".ENV", ".Env.Local", "A.PEM", "Credentials.json", "ID_RSA"):
            with self.subTest(name=name):
                self.assertIsNotNone(file_reason("Read", PROJECT + "/" + name))
        self.assertIsNone(file_reason("Read", PROJECT + "/.env.EXAMPLE"))


class MissingCwdTest(unittest.TestCase):
    def test_relative_secret_path_asks_without_cwd(self):
        self.assertIsNotNone(secret_guard.secret_access_reason(
            {"tool_name": "Read", "tool_input": {"file_path": ".env"}}, HOME))

    def test_non_string_cwd_is_treated_as_missing(self):
        self.assertIsNotNone(file_reason("Read", "/x/.env", cwd=None))


class HookProcessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "decisions.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, stdin_text, python=sys.executable, log=None):
        env = dict(os.environ, **{hook_decision_log.LOG_PATH_ENV: log or self.log})
        return subprocess.run([python, SCRIPT], input=stdin_text, capture_output=True, text=True,
                              timeout=10, env=env)

    def assert_asks_about_env(self, payload, python=sys.executable, log=None):
        p = self.run_hook(json.dumps(payload), python, log)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "ask"))
        self.assertIn(".env", out["permissionDecisionReason"])

    def test_read_of_env_prints_ask(self):
        self.assert_asks_about_env(call("Read", {"file_path": PROJECT + "/.env"}))

    def test_cat_of_env_prints_ask(self):
        self.assert_asks_about_env(call("Bash", {"command": "cat .env"}))

    @unittest.skipUnless(os.path.exists(SYSTEM_PYTHON), "system python3 not installed")
    def test_runs_under_system_python(self):
        self.assert_asks_about_env(call("Read", {"file_path": PROJECT + "/.env"}), SYSTEM_PYTHON)

    def test_harmless_call_prints_nothing(self):
        p = self.run_hook(json.dumps(call("Read", {"file_path": PROJECT + "/README.md"})))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_malformed_input_prints_nothing(self):
        for text in ("not json", "", "{}", '{"tool_name": "Bash"}', "[1]",
                     json.dumps({"tool_name": "Read", "cwd": PROJECT}),
                     json.dumps({"tool_name": "Bash", "tool_input": {"command": None}})):
            with self.subTest(text=text):
                p = self.run_hook(text)
                self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_ask_is_logged_with_basename_tool_and_repo_only(self):
        self.run_hook(json.dumps(call("Read", {"file_path": PROJECT + "/config/.env"})))
        with open(self.log) as f:
            entry = json.loads(f.read())
        self.assertEqual((entry["hook"], entry["decision"], entry["tool"], entry["repo"]),
                         ("secret_guard", "ask", "Read", "project"))
        self.assertIn(".env", entry["reason"])
        self.assertNotIn(PROJECT, entry["reason"])

    def test_allowed_call_is_not_logged(self):
        self.run_hook(json.dumps(call("Read", {"file_path": PROJECT + "/README.md"})))
        self.assertFalse(os.path.exists(self.log))

    def test_unwritable_log_does_not_change_the_decision(self):
        blocker = os.path.join(self.tmp.name, "blocker")
        with open(blocker, "w") as f:
            f.write("a file")
        self.assert_asks_about_env(call("Read", {"file_path": PROJECT + "/.env"}),
                                   log=os.path.join(blocker, "log.jsonl"))


if __name__ == "__main__":
    unittest.main()
