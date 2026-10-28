#!/usr/bin/env python3
"""Build the routing eval plugin for the global ai-sdlc config (CLAUDE.md, skills, agents).

The eval sandbox runs with a fresh HOME: it sees neither ~/.claude nor installed plugins.
So the wrapper plugin at ~/.claude/evals/routing gets:
- skills/: symlinks to the enabled ~/.claude/skills plus the installed Superpowers skills
  (a global skill wins on a name clash);
- agents -> ~/.claude/agents;
- per case, append_system_prompt = what Superpowers' SessionStart hook injects
  (using-superpowers) + the global CLAUDE.md + a dry-run note.
Cases come from cases.json; results/ is never touched. A case may set `dry_run: false` (no dry-run
note), `max_turns` and `allowed_tools` (a list) for a check that must run past the routing step.
"""
import json
import re
import shutil
import sys
from pathlib import Path

CLAUDE_HOME = Path.home() / ".claude"
GLOBAL_INSTRUCTIONS_PATH = CLAUDE_HOME / "CLAUDE.md"
SETTINGS_PATH = CLAUDE_HOME / "settings.json"
GLOBAL_SKILLS_DIR = CLAUDE_HOME / "skills"
GLOBAL_AGENTS_DIR = CLAUDE_HOME / "agents"
INSTALLED_PLUGINS_PATH = CLAUDE_HOME / "plugins" / "installed_plugins.json"
PLUGIN_DIR = CLAUDE_HOME / "evals" / "routing"
PLUGIN_SKILLS_DIR = PLUGIN_DIR / "skills"
PLUGIN_AGENTS_LINK = PLUGIN_DIR / "agents"
PLUGIN_EVALS_DIR = PLUGIN_DIR / "evals"
CASES_PATH = PLUGIN_DIR / "cases.json"

SUPERPOWERS_ID = "superpowers@claude-plugins-official"
ROUTER_SKILL = "using-superpowers"
SKILL_OVERRIDES_KEY = "skillOverrides"
SKILL_DISABLED = "off"
SKILL_MANIFEST = "SKILL.md"
EVAL_RESULTS_DIR_NAME = "results"
# Lowercase-only names keep case-insensitive filesystems from aliasing "results" or each other.
SAFE_CASE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

PROMPT_PATH = "prompt.md"
CRITERIA_GRADER_PATH = "graders/criteria.md"
MAX_TURNS = 4
READ_ONLY_TOOLS = "[Read, Glob, Grep, Skill]"
ROUTING_DRY_RUN_NOTE = (
    "This session is a routing dry-run: there is no repository to work in and no git branch. "
    "Follow your routing instructions exactly as in a real task (banner, route, first step), "
    "announce the routing decision, then stop. Do not search for files."
)


def load_skill_overrides(settings_path):
    return json.loads(settings_path.read_text()).get(SKILL_OVERRIDES_KEY, {})


def validate_case_names(names):
    invalid = [n for n in names if not SAFE_CASE_NAME.fullmatch(n) or n == EVAL_RESULTS_DIR_NAME]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if invalid or duplicates:
        raise ValueError(f"Bad case names: invalid={invalid} duplicates={duplicates}")


def enabled_skill_dirs(skills_dir, skill_overrides):
    return [
        skill_dir
        for skill_dir in sorted(skills_dir.iterdir())
        if (skill_dir / SKILL_MANIFEST).exists() and skill_overrides.get(skill_dir.name) != SKILL_DISABLED
    ]


def skill_links(global_dirs, superpowers_dirs):
    links = {d.name: d for d in superpowers_dirs}
    links.update({d.name: d for d in global_dirs})
    return links


def superpowers_root(installed_plugins_path):
    installs = json.loads(installed_plugins_path.read_text()).get("plugins", {}).get(SUPERPOWERS_ID)
    if not installs:
        sys.exit(f"{SUPERPOWERS_ID} is not installed; the routing evals depend on it")
    return Path(installs[0]["installPath"])


def build_system_prompt_addition(router_skill_text, global_instructions, dry_run=True):
    # Same wrapper as superpowers/hooks/session-start, so the router reads as in a real session.
    session_context = (
        "<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n**Below is the full content of your "
        "'superpowers:using-superpowers' skill - your introduction to using skills. For all other "
        f"skills, use the 'Skill' tool:**\n\n{router_skill_text}\n</EXTREMELY_IMPORTANT>"
    )
    text = f"{session_context}\n\n{global_instructions}"
    return f"{text}\n\n{ROUTING_DRY_RUN_NOTE}" if dry_run else text


def yaml_quoted(text):
    # A JSON string is a valid YAML double-quoted scalar. The eval loader cuts the front matter
    # at the first `---` even inside a value, so every `-` is escaped (`-` in YAML too).
    return json.dumps(text).replace("-", "\\u002d")


def render_prompt(user_prompt, system_prompt_addition, max_turns=MAX_TURNS, allowed_tools=READ_ONLY_TOOLS):
    return (
        "---\n"
        f"max_turns: {max_turns}\n"
        f"allowed_tools: {allowed_tools}\n"
        f"append_system_prompt: {yaml_quoted(system_prompt_addition)}\n"
        "---\n\n"
        f"{user_prompt}\n"
    )


def render_criteria_grader(criteria):
    return f"---\ntype: llm\nfocus: trace\n---\n\n{criteria}\n"


def case_files(case, router_skill_text, global_instructions):
    system_prompt_addition = build_system_prompt_addition(router_skill_text, global_instructions,
                                                          dry_run=case.get("dry_run", True))
    tools = case.get("allowed_tools")
    return {
        PROMPT_PATH: render_prompt(case["prompt"], system_prompt_addition, case.get("max_turns", MAX_TURNS),
                                   "[%s]" % ", ".join(tools) if tools else READ_ONLY_TOOLS),
        CRITERIA_GRADER_PATH: render_criteria_grader(case["criteria"]),
    }


def stale_case_dirs(evals_dir, kept_case_names):
    kept = {*kept_case_names, EVAL_RESULTS_DIR_NAME}
    return [e for e in evals_dir.iterdir() if e.is_dir() and not e.is_symlink() and e.name not in kept]


def recreate_dir(directory):
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def write_case(case_dir, files_by_relative_path):
    recreate_dir(case_dir)
    for relative_path, content in files_by_relative_path.items():
        path = case_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def main():
    cases = json.loads(CASES_PATH.read_text())
    names = [case["name"] for case in cases]
    validate_case_names(names)

    sp_skills_dir = superpowers_root(INSTALLED_PLUGINS_PATH) / "skills"
    links = skill_links(enabled_skill_dirs(GLOBAL_SKILLS_DIR, load_skill_overrides(SETTINGS_PATH)),
                        enabled_skill_dirs(sp_skills_dir, {}))
    router_skill_text = (sp_skills_dir / ROUTER_SKILL / SKILL_MANIFEST).read_text()
    global_instructions = GLOBAL_INSTRUCTIONS_PATH.read_text()

    recreate_dir(PLUGIN_SKILLS_DIR)
    for name, target in sorted(links.items()):
        (PLUGIN_SKILLS_DIR / name).symlink_to(target)
    if not PLUGIN_AGENTS_LINK.is_symlink():
        PLUGIN_AGENTS_LINK.symlink_to(GLOBAL_AGENTS_DIR)

    PLUGIN_EVALS_DIR.mkdir(parents=True, exist_ok=True)
    for stale in stale_case_dirs(PLUGIN_EVALS_DIR, names):
        shutil.rmtree(stale)
    for case in cases:
        write_case(PLUGIN_EVALS_DIR / case["name"], case_files(case, router_skill_text, global_instructions))
    print(f"Linked {len(links)} skills; built {len(cases)} routing cases")


if __name__ == "__main__":
    main()
