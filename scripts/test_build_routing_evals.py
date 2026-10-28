"""Unit tests for build-routing-evals.py: python3 -m unittest ~/.claude/scripts/test_build_routing_evals.py"""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

BUILDER_PATH = Path(__file__).with_name("build-routing-evals.py")
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n\n(.*)$", re.S)


def load_builder():
    spec = importlib.util.spec_from_file_location("build_routing_evals", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def make_skill(parent, name):
    (parent / name).mkdir(parents=True)
    (parent / name / builder.SKILL_MANIFEST).write_text("---\nname: %s\n---\n" % name)
    return parent / name


class ValidateCaseNamesTest(unittest.TestCase):
    def test_accepts_kebab_case_names(self):
        builder.validate_case_names(["fix-stack-trace", "question-no-banner", "case2"])

    def test_rejects_names_that_could_alias_dirs_or_results(self):
        for bad in ["", " ", "results", "Results", "ok\n", "a/b", ".hidden", "-leading", "Foo"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                builder.validate_case_names([bad])

    def test_rejects_duplicates(self):
        with self.assertRaises(ValueError):
            builder.validate_case_names(["same", "same"])


class StaleCaseDirsTest(unittest.TestCase):
    def test_keeps_listed_cases_and_results(self):
        with tempfile.TemporaryDirectory() as temp:
            evals_dir = Path(temp)
            for name in ["kept", "results", "removed"]:
                (evals_dir / name).mkdir()
            stale = builder.stale_case_dirs(evals_dir, ["kept"])
            self.assertEqual([p.name for p in stale], ["removed"])


class RenderPromptTest(unittest.TestCase):
    def test_system_prompt_round_trips_and_user_prompt_follows(self):
        for text in ["    leading indent\nnaïve café", "a: b\n---\n\ttab \"q\" \\ end  ", "▶ ai-sdlc · fix/S"]:
            with self.subTest(text=text):
                m = FRONT_MATTER.match(builder.render_prompt("user asks", text))
                line = [l for l in m.group(1).splitlines() if l.startswith("append_system_prompt:")][0]
                self.assertEqual(json.loads(line.split(":", 1)[1]), text)
                self.assertEqual(m.group(2), "user asks\n")

    def test_no_dash_fence_inside_front_matter(self):
        # The eval loader cuts the front matter at the first `---`, even inside a quoted value.
        rendered = builder.render_prompt("p", "---\nname: x\n---\nbody --- more")
        front = FRONT_MATTER.match(rendered).group(1)
        self.assertNotIn("---", front)
        line = [l for l in front.splitlines() if l.startswith("append_system_prompt:")][0]
        self.assertEqual(json.loads(line.split(":", 1)[1]), "---\nname: x\n---\nbody --- more")

    def test_front_matter_has_read_only_tools_and_turn_limit(self):
        front = FRONT_MATTER.match(builder.render_prompt("p", "s")).group(1)
        self.assertIn("max_turns: %d" % builder.MAX_TURNS, front)
        self.assertIn("allowed_tools: %s" % builder.READ_ONLY_TOOLS, front)


class CaseFilesTest(unittest.TestCase):
    def front(self, files):
        return FRONT_MATTER.match(files[builder.PROMPT_PATH])

    def test_a_plain_case_is_a_read_only_dry_run(self):
        files = builder.case_files({"name": "c", "prompt": "do x", "criteria": "Pass if y"}, "ROUTER", "RULES")
        front, body = self.front(files).groups()
        self.assertIn("max_turns: %d" % builder.MAX_TURNS, front)
        self.assertIn("allowed_tools: %s" % builder.READ_ONLY_TOOLS, front)
        self.assertIn(json.dumps(builder.ROUTING_DRY_RUN_NOTE)[1:-1].replace("-", "\\u002d"), front)
        self.assertEqual(body, "do x\n")
        self.assertTrue(files[builder.CRITERIA_GRADER_PATH].endswith("Pass if y\n"))

    def test_a_live_case_overrides_turns_tools_and_drops_the_dry_run_note(self):
        case = {"name": "c", "prompt": "review", "criteria": "Pass if race", "dry_run": False, "max_turns": 10,
                "allowed_tools": ["Read", "Glob", "Grep", "Skill", "Agent"]}
        front = self.front(builder.case_files(case, "ROUTER", "RULES")).group(1)
        self.assertIn("max_turns: 10", front)
        self.assertIn("allowed_tools: [Read, Glob, Grep, Skill, Agent]", front)
        self.assertNotIn("dry", front)
        self.assertIn("RULES", front)


class SkillLinksTest(unittest.TestCase):
    def test_skips_disabled_and_manifestless_global_skills(self):
        with tempfile.TemporaryDirectory() as temp:
            skills = Path(temp)
            make_skill(skills, "enabled")
            make_skill(skills, "disabled")
            (skills / "no-manifest").mkdir()
            enabled = builder.enabled_skill_dirs(skills, {"disabled": builder.SKILL_DISABLED})
            self.assertEqual([p.name for p in enabled], ["enabled"])

    def test_global_skill_wins_over_superpowers_skill_with_same_name(self):
        with tempfile.TemporaryDirectory() as temp:
            mine, sp = Path(temp, "mine"), Path(temp, "sp")
            own = make_skill(mine, "brainstorming")
            make_skill(sp, "brainstorming")
            tdd = make_skill(sp, "test-driven-development")
            links = builder.skill_links([own], builder.enabled_skill_dirs(sp, {}))
            self.assertEqual(links, {"brainstorming": own, "test-driven-development": tdd})


class SuperpowersTest(unittest.TestCase):
    def test_install_path_from_installed_plugins(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp, "installed_plugins.json")
            manifest.write_text(json.dumps({"plugins": {builder.SUPERPOWERS_ID: [{"installPath": temp}]}}))
            self.assertEqual(builder.superpowers_root(manifest), Path(temp))

    def test_missing_superpowers_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp, "installed_plugins.json")
            manifest.write_text(json.dumps({"plugins": {}}))
            with self.assertRaises(SystemExit):
                builder.superpowers_root(manifest)

    def test_live_system_prompt_has_no_dry_run_note(self):
        text = builder.build_system_prompt_addition("ROUTER BODY", "GLOBAL RULES", dry_run=False)
        self.assertTrue(text.endswith("GLOBAL RULES"))
        self.assertNotIn(builder.ROUTING_DRY_RUN_NOTE, text)

    def test_system_prompt_mirrors_session_start_injection_then_claude_md(self):
        text = builder.build_system_prompt_addition("ROUTER BODY", "GLOBAL RULES")
        self.assertIn("You have superpowers.", text)
        self.assertLess(text.index("ROUTER BODY"), text.index("GLOBAL RULES"))
        self.assertTrue(text.endswith(builder.ROUTING_DRY_RUN_NOTE))


if __name__ == "__main__":
    unittest.main()
