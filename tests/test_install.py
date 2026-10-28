"""install.sh: symlinks the repo into $HOME/.claude and merges settings.json. Always runs with a temp HOME."""
import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(REPO, "install.sh")
REPO_SETTINGS = os.path.join(REPO, "settings.json")


def repo_hook_commands():
    with open(REPO_SETTINGS) as f:
        hooks = json.load(f)["hooks"]
    return {(event, h["command"]) for event, groups in hooks.items() for g in groups for h in g["hooks"]}


def hook_commands(settings):
    return [(event, h["command"]) for event, groups in settings.get("hooks", {}).items()
            for g in groups for h in g["hooks"]]


def snapshot(root):
    """Every path under root with its link target or file content."""
    out = {}
    for d, dirs, files in os.walk(root):
        for name in dirs + files:
            p = os.path.join(d, name)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                out[rel] = ("link", os.readlink(p))
            elif os.path.isfile(p):
                with open(p, "rb") as f:
                    out[rel] = ("file", f.read())
            else:
                out[rel] = ("dir", None)
    return out


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.claude = os.path.join(self.home, ".claude")

    def tearDown(self):
        shutil.rmtree(self.home)

    def run_install(self, *args):
        env = dict(os.environ, HOME=self.home)
        return subprocess.run(["bash", INSTALL] + list(args), env=env, capture_output=True, text=True, timeout=60)

    def assert_linked(self, rel, repo_rel):
        p = os.path.join(self.claude, rel)
        self.assertTrue(os.path.islink(p), "%s is not a symlink" % rel)
        self.assertEqual(os.path.realpath(p), os.path.realpath(os.path.join(REPO, repo_rel)))

    def write(self, rel, content):
        p = os.path.join(self.claude, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)

    def settings(self):
        with open(os.path.join(self.claude, "settings.json")) as f:
            return json.load(f)

    def backups(self):
        return glob.glob(os.path.join(self.claude, "backups", "ai-sdlc-setup-*"))

    def test_fresh_install_links_every_part(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_linked("CLAUDE.md", "CLAUDE.md")
        for p in glob.glob(os.path.join(REPO, "agents", "*.md")):
            self.assert_linked(os.path.join("agents", os.path.basename(p)), os.path.join("agents", os.path.basename(p)))
        for p in glob.glob(os.path.join(REPO, "skills", "*", "")):
            name = os.path.basename(os.path.dirname(p))
            self.assert_linked(os.path.join("skills", name), os.path.join("skills", name))
        self.assert_linked("hooks/ai-sdlc", "hooks/ai-sdlc")
        for p in glob.glob(os.path.join(REPO, "scripts", "*")):
            if os.path.isfile(p):
                name = os.path.basename(p)
                self.assert_linked(os.path.join("scripts", name), os.path.join("scripts", name))
        self.assert_linked("evals/routing/cases.json", "evals/routing/cases.json")
        self.assert_linked("evals/routing/.claude-plugin", "evals/routing/.claude-plugin")

    def test_fresh_install_creates_settings_as_a_regular_file(self):
        self.run_install()
        p = os.path.join(self.claude, "settings.json")
        self.assertFalse(os.path.islink(p))
        with open(REPO_SETTINGS) as f:
            self.assertEqual(self.settings(), json.load(f))

    def test_rerun_is_idempotent(self):
        self.run_install()
        before = snapshot(self.claude)
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(snapshot(self.claude), before)
        self.assertEqual(self.backups(), [])

    def test_existing_file_is_backed_up_before_linking(self):
        self.write("CLAUDE.md", "my own rules\n")
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_linked("CLAUDE.md", "CLAUDE.md")
        [backup] = self.backups()
        with open(os.path.join(backup, "CLAUDE.md")) as f:
            self.assertEqual(f.read(), "my own rules\n")

    def test_existing_dir_and_wrong_symlink_are_backed_up(self):
        self.write("hooks/ai-sdlc/old.py", "x = 1\n")
        os.makedirs(os.path.join(self.claude, "skills"), exist_ok=True)
        os.symlink("/nonexistent/elsewhere", os.path.join(self.claude, "skills", "retro"))
        self.run_install()
        self.assert_linked("hooks/ai-sdlc", "hooks/ai-sdlc")
        self.assert_linked("skills/retro", "skills/retro")
        [backup] = self.backups()
        self.assertTrue(os.path.isfile(os.path.join(backup, "hooks", "ai-sdlc", "old.py")))
        self.assertEqual(os.readlink(os.path.join(backup, "skills", "retro")), "/nonexistent/elsewhere")

    def test_settings_merge_keeps_unrelated_keys_and_hooks_without_duplicates(self):
        stop_cmd = "python3 $HOME/.claude/hooks/ai-sdlc/stop_check.py"
        self.write("settings.json", json.dumps({
            "theme": "light",
            "permissions": {"allow": ["Bash(ls:*)"]},
            "enabledPlugins": {"superpowers@claude-plugins-official": False},
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "my-guard.sh"}]}],
                "Stop": [{"hooks": [{"type": "command", "command": stop_cmd, "timeout": 600}]}],
            },
        }))
        self.run_install()
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.settings()
        self.assertEqual(s["theme"], "light")
        self.assertEqual(s["permissions"], {"allow": ["Bash(ls:*)"]})
        self.assertFalse(s["enabledPlugins"]["superpowers@claude-plugins-official"], "user's choice overwritten")
        self.assertTrue(s["enabledPlugins"]["layered-rails@layered-rails-skills"])
        self.assertIn("layered-rails-skills", s["extraKnownMarketplaces"])
        commands = hook_commands(s)
        self.assertIn(("PreToolUse", "my-guard.sh"), commands)
        self.assertEqual(len(commands), len(set(commands)), "duplicated hook entries: %s" % commands)
        self.assertTrue(repo_hook_commands() <= set(commands))

    def test_settings_merge_backs_up_the_original(self):
        self.write("settings.json", '{"theme": "light"}\n')
        self.run_install()
        [backup] = self.backups()
        with open(os.path.join(backup, "settings.json")) as f:
            self.assertEqual(f.read(), '{"theme": "light"}\n')

    def test_invalid_settings_json_is_left_untouched_and_fails(self):
        self.write("settings.json", "{not json")
        r = self.run_install()
        self.assertNotEqual(r.returncode, 0)
        with open(os.path.join(self.claude, "settings.json")) as f:
            self.assertEqual(f.read(), "{not json")

    def test_dry_run_changes_nothing(self):
        self.write("CLAUDE.md", "my own rules\n")
        self.write("settings.json", '{"theme": "light"}\n')
        before = snapshot(self.claude)
        r = self.run_install("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(snapshot(self.claude), before)
        self.assertIn("CLAUDE.md", r.stdout)
        self.assertIn("settings.json", r.stdout)

    def test_help_prints_usage(self):
        r = self.run_install("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--dry-run", r.stdout)
        self.assertFalse(os.path.exists(self.claude))

    def test_unknown_option_fails_without_changes(self):
        r = self.run_install("--bogus")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.claude))


if __name__ == "__main__":
    unittest.main()
