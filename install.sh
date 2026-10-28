#!/usr/bin/env bash
# Install the ai-sdlc setup into $HOME/.claude as symlinks to this repo, and merge settings.json.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh [--dry-run] [--help]

Symlinks this repo into $HOME/.claude:
  CLAUDE.md, agents/*.md, skills/<name>/, hooks/ai-sdlc/, scripts/*,
  evals/routing/cases.json, evals/routing/.claude-plugin
An existing target that is not already the right symlink is moved to
$HOME/.claude/backups/ai-sdlc-setup-<timestamp>/ first. Re-running is safe.

settings.json is never overwritten: the repo's hooks are added to
$HOME/.claude/settings.json when their command is not there yet, and
enabledPlugins / extraKnownMarketplaces keys are added when missing
(the original is backed up first). It is created when absent.

  --dry-run   print the actions without changing anything
  --help      show this help
EOF
}

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install.sh: unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CLAUDE_DIR="$HOME/.claude"
BACKUP_DIR="$CLAUDE_DIR/backups/ai-sdlc-setup-$(date +%Y%m%d-%H%M%S)"
if [ -e "$BACKUP_DIR" ]; then BACKUP_DIR="$BACKUP_DIR-$$"; fi
PREFIX=""
if [ "$DRY_RUN" = 1 ]; then PREFIX="[dry-run] "; fi

run() {
  if [ "$DRY_RUN" = 0 ]; then "$@"; fi
}

backup() {
  local target="$1" rel dest
  rel="${target#"$CLAUDE_DIR"/}"
  dest="$BACKUP_DIR/$rel"
  echo "${PREFIX}backup  ~/.claude/$rel -> $dest"
  run mkdir -p "$(dirname "$dest")"
  run mv "$target" "$dest"
}

link() {
  local src="$REPO_DIR/$1" dst="$CLAUDE_DIR/$2"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "${PREFIX}ok      ~/.claude/$2"
    return
  fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then backup "$dst"; fi
  echo "${PREFIX}link    ~/.claude/$2 -> $src"
  run mkdir -p "$(dirname "$dst")"
  run ln -s "$src" "$dst"
}

link CLAUDE.md CLAUDE.md
for f in "$REPO_DIR"/agents/*.md; do link "agents/${f##*/}" "agents/${f##*/}"; done
for d in "$REPO_DIR"/skills/*/; do d="${d%/}"; link "skills/${d##*/}" "skills/${d##*/}"; done
link hooks/ai-sdlc hooks/ai-sdlc
for f in "$REPO_DIR"/scripts/*; do
  if [ -f "$f" ]; then link "scripts/${f##*/}" "scripts/${f##*/}"; fi
done
link evals/routing/cases.json evals/routing/cases.json
link evals/routing/.claude-plugin evals/routing/.claude-plugin

python3 - "$REPO_DIR/settings.json" "$CLAUDE_DIR/settings.json" "$BACKUP_DIR" "$DRY_RUN" <<'PY'
import json
import os
import shutil
import sys

repo_path, target, backup_dir, dry_run = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"
prefix = "[dry-run] " if dry_run else ""
with open(repo_path) as f:
    repo = json.load(f)

if not os.path.exists(target):
    print("%screate  ~/.claude/settings.json" % prefix)
    if not dry_run:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            json.dump(repo, f, indent=2)
            f.write("\n")
    sys.exit(0)

try:
    with open(target) as f:
        current = json.load(f)
except ValueError as e:
    sys.exit("install.sh: ~/.claude/settings.json is not valid JSON (%s); fix it and re-run" % e)

changes = []
hooks = current.setdefault("hooks", {})
for event, groups in repo.get("hooks", {}).items():
    existing = hooks.setdefault(event, [])
    present = {h.get("command") for g in existing for h in g.get("hooks", [])}
    for group in groups:
        missing = [h for h in group["hooks"] if h["command"] not in present]
        if missing:
            new_group = {k: v for k, v in group.items() if k != "hooks"}
            new_group["hooks"] = missing
            existing.append(new_group)
            present.update(h["command"] for h in missing)
            changes += ["hook %s: %s" % (event, h["command"]) for h in missing]
    if not existing:
        del hooks[event]
if not hooks:
    del current["hooks"]
for key in ("enabledPlugins", "extraKnownMarketplaces"):
    for name, value in repo.get(key, {}).items():
        section = current.setdefault(key, {})
        if name not in section:
            section[name] = value
            changes.append("%s: %s" % (key, name))

if not changes:
    print("%sok      ~/.claude/settings.json (nothing to merge)" % prefix)
    sys.exit(0)
for c in changes:
    print("%smerge   ~/.claude/settings.json + %s" % (prefix, c))
if not dry_run:
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(target, os.path.join(backup_dir, "settings.json"))
    print("backup  ~/.claude/settings.json -> %s" % os.path.join(backup_dir, "settings.json"))
    with open(target, "w") as f:
        json.dump(current, f, indent=2)
        f.write("\n")
PY
