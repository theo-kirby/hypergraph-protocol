#!/usr/bin/env bash
# Symlink the hypergraph-* skills into the Claude skills directory.
# Usage: ./install.sh            (installs to ~/.claude/skills)
#        CLAUDE_SKILLS_DIR=/path ./install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$SKILLS_DIR"

for src in "$REPO_DIR"/skills/hypergraph-*/; do
  name="$(basename "$src")"
  target="$SKILLS_DIR/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "skip: $target exists and is not a symlink — remove it manually" >&2
    continue
  fi
  ln -sfn "${src%/}" "$target"
  echo "linked: $target -> ${src%/}"
done
