#!/usr/bin/env bash
# Symlink the hypergraph-* skills into a Claude skills directory.
#
# Thin wrapper around `hypergraph skills install --link` so there is exactly one
# implementation of "install the skills" (tools/hypergraph.py:cmd_skills).
#
# Usage: ./install.sh                     (installs to ~/.claude/skills)
#        CLAUDE_SKILLS_DIR=/path ./install.sh
#
# This repo itself needs neither: .claude/skills/ holds committed relative symlinks,
# so a clone already has the skills at project scope. Run this only to make them
# available in every session, everywhere.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

exec uv run "$REPO_DIR/tools/hypergraph.py" skills install --link --target "$SKILLS_DIR"
