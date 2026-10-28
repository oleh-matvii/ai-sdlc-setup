#!/bin/zsh
# Routing regression suite for the global ai-sdlc config (CLAUDE.md, skills, agents).
# Run after any change under ~/.claude. Extra args pass through, e.g. --runs 3 or --case 'fix-*'.
# The sandbox denies reads outside its workspace; the grant lets symlinked skills
# (~/.claude/skills, the Superpowers cache) open their own supporting files.
python3 "$HOME/.claude/scripts/build-routing-evals.py" || exit 1
exec claude plugin eval "$HOME/.claude/evals/routing" \
  --ablation none --judge-model sonnet --runs 1 -j 4 \
  --allow-tools "Read(/$HOME/.claude/**)" \
  --max-cost-usd 5 --no-publish --trust-plugin "$@"
