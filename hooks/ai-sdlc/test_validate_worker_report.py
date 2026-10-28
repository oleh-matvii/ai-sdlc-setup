"""Unit tests for validate_worker_report.py: python3 -m unittest discover -s ~/.claude/hooks/ai-sdlc -p 'test_*.py'"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS_DIR)
import validate_worker_report as vwr  # noqa: E402

SCRIPT = os.path.join(HOOKS_DIR, "validate_worker_report.py")
REAL_AGENTS_DIR = os.path.expanduser("~/.claude/agents")

IMPLEMENTER = """---
name: feature-implementer
---
Intro.

## Rules
1. **Not an output item.** Rules list.

## Output (always this structure)
1. **Phase and scope:** route, phase, which plan tasks/steps were done.
2. **Changes:** files changed, with one line each.
3. **Tests:** tests added/changed.
4. **Commits.**
5. **Assumptions, risks, blockers:** anything to decide.

## Next heading
1. **Not part of the output**
"""

ARCHITECT = """## Output (always this structure, concise)
1. **Problem and forces:** what varies.
2. **Research:** the problem class.
3. **Options (Option 0 + 1–2):** structure, trade-offs.
4. **Recommendation:** the option.
5. **Resulting structure**, per zoom level touched:
   - system: parts;
   - code: key units.
6. **Testing shape:** seams.
7. **Open questions:** each with your recommendation.

**For a refactor**, replace 3–5 with:
- smells found (`path:line`);
- **safe incremental steps**: each keeps behavior identical.

Never copy customer personal data into the output.
"""

GOOD_REPORT = """1. **Phase and scope:** tech/L, whole plan.
2. **Changes:**
- a.py: thing
3. **Tests**
Ran 10 tests, OK
## 4. Commits
none (not a git repo)
**5. Assumptions, risks, blockers:** none
"""


def without(name, report=GOOD_REPORT):
    return "\n".join(line for line in report.splitlines() if name not in line)


class RequiredSectionsTest(unittest.TestCase):
    def test_bold_item_names_from_the_output_section_only(self):
        self.assertEqual(vwr.required_sections(IMPLEMENTER),
                         ["Phase and scope", "Changes", "Tests", "Commits", "Assumptions, risks, blockers"])

    def test_sub_bullets_do_not_end_the_list_and_replaceable_items_are_optional(self):
        self.assertEqual(vwr.required_sections(ARCHITECT),
                         ["Problem and forces", "Research", "Testing shape", "Open questions"])

    def test_plain_and_parenthesised_names(self):
        text = "## Output\n1. Context — current shape\n2. **Key findings** (each with its source URL)\n3. Risks - x\n"
        self.assertEqual(vwr.required_sections(text), ["Context", "Key findings", "Risks"])

    def test_no_output_section_means_nothing_to_enforce(self):
        self.assertEqual(vwr.required_sections("# Agent\n\n## Steps\n1. **Do it**\n"), [])

    def test_every_real_agent_with_an_output_section_parses(self):
        files = sorted(glob.glob(os.path.join(REAL_AGENTS_DIR, "*.md")))
        if not files:
            self.skipTest("no agents installed")
        for path in files:
            with open(path) as f:
                text = f.read()
            with self.subTest(agent=os.path.basename(path)):
                names = vwr.required_sections(text)
                if "\n## Output" in text:
                    self.assertGreaterEqual(len(names), 4)
                    self.assertTrue(all(n and len(n) < 60 and "*" not in n for n in names), names)
                else:
                    self.assertEqual(names, [])


class MissingSectionsTest(unittest.TestCase):
    names = ["Phase and scope", "Changes", "Tests", "Commits", "Assumptions, risks, blockers"]

    def test_complete_report_in_any_heading_style_has_none_missing(self):
        self.assertEqual(vwr.missing_sections(self.names, GOOD_REPORT), [])

    def test_missing_section_is_named(self):
        self.assertEqual(vwr.missing_sections(self.names, without("Commits")), ["Commits"])

    def test_name_must_start_the_line(self):
        report = without("Commits") + "\nNo Commits were made."
        self.assertEqual(vwr.missing_sections(self.names, report), ["Commits"])

    def test_matching_ignores_case(self):
        self.assertEqual(vwr.missing_sections(self.names, GOOD_REPORT.replace("Commits", "COMMITS")), [])


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.agents = os.path.join(root, "agents")
        os.makedirs(self.agents)
        with open(os.path.join(self.agents, "feature-implementer.md"), "w") as f:
            f.write(IMPLEMENTER)
        with open(os.path.join(self.agents, "plain.md"), "w") as f:
            f.write("# No output section\n")
        self.log = os.path.join(root, "decisions.jsonl")
        self.env = dict(os.environ, AI_SDLC_AGENTS_DIR=self.agents, CLAUDE_HOOK_DECISION_LOG=self.log,
                        AI_SDLC_WORKER_REPORT_DENIALS=os.path.join(root, "denials"))
        self.env.pop("AI_SDLC_NESTED", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, payload):
        p = subprocess.run([sys.executable, SCRIPT], input=payload if isinstance(payload, str) else json.dumps(payload),
                           capture_output=True, text=True, timeout=20, env=self.env)
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        return json.loads(p.stdout) if p.stdout.strip() else None

    def logged(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    @staticmethod
    def handback(report, agent_type="feature-implementer", agent_id="a1", tool="SubagentHandback"):
        return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"message": report},
                "agent_type": agent_type, "agent_id": agent_id, "session_id": "s", "cwd": "/src/my-app"}

    @staticmethod
    def subagent_stop(report, retry=False):
        return {"hook_event_name": "SubagentStop", "agent_type": "feature-implementer", "agent_id": "a1",
                "last_assistant_message": report, "stop_hook_active": retry, "session_id": "s", "cwd": "/src/x"}

    def test_valid_handback_passes_silently_and_is_not_logged(self):
        self.assertIsNone(self.run_hook(self.handback(GOOD_REPORT)))
        self.assertEqual(self.logged(), [])

    def test_invalid_handback_is_denied_naming_the_missing_sections(self):
        out = self.run_hook(self.handback(without("Commits")))["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn("Commits", out["permissionDecisionReason"])

    def test_second_invalid_handback_of_the_same_agent_goes_through_with_a_warning(self):
        bad = self.handback(without("Commits"))
        self.run_hook(bad)
        out = self.run_hook(bad)
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("Commits", out["systemMessage"])

    def test_a_valid_handback_resets_the_retry(self):
        self.run_hook(self.handback(without("Commits")))
        self.run_hook(self.handback(GOOD_REPORT))
        out = self.run_hook(self.handback(without("Commits")))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_another_agent_is_denied_on_its_own_first_try(self):
        self.run_hook(self.handback(without("Commits"), agent_id="a"))
        out = self.run_hook(self.handback(without("Commits"), agent_id="b"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_agents_without_an_output_section_or_file_pass(self):
        for agent in ("plain", "superpowers:code-reviewer", "missing", "../agents/feature-implementer"):
            with self.subTest(agent=agent):
                self.assertIsNone(self.run_hook(self.handback("anything", agent_type=agent)))

    def test_other_tools_and_empty_stops_are_ignored(self):
        self.assertIsNone(self.run_hook(self.handback("x", tool="Bash")))
        self.assertIsNone(self.run_hook({"hook_event_name": "SubagentStop", "agent_type": "feature-implementer"}))

    def test_subagent_stop_with_a_bad_report_blocks_then_warns_on_retry(self):
        self.assertEqual(self.run_hook(self.subagent_stop(without("Commits")))["decision"], "block")
        out = self.run_hook(self.subagent_stop(without("Commits"), retry=True))
        self.assertNotIn("decision", out)
        self.assertIn("Commits", out["systemMessage"])

    def test_deny_and_block_are_logged_without_report_text(self):
        self.run_hook(self.handback(without("Commits") + "\nSECRET-REPORT-TEXT"))
        self.run_hook(self.subagent_stop(without("Commits")))
        entries = self.logged()
        self.assertEqual([(e["hook"], e["decision"], e["tool"]) for e in entries],
                         [("validate_worker_report", "deny", "SubagentHandback"),
                          ("validate_worker_report", "block", None)])
        self.assertEqual(entries[0]["repo"], "my-app")
        self.assertIn("feature-implementer", entries[0]["reason"])
        self.assertIn("Commits", entries[0]["reason"])
        self.assertNotIn("SECRET-REPORT-TEXT", json.dumps(entries))

    def test_garbage_input_passes_silently(self):
        for text in ("not json{", "", "[1]", "{}"):
            with self.subTest(text=text):
                self.assertIsNone(self.run_hook(text))


if __name__ == "__main__":
    unittest.main()
