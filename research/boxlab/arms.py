"""The three arms — and the one thing that is allowed to differ between them.

Every arm gets the **same** `_core.md` (research discipline, publishing, the
definition of done) and the **same** mission. Exactly one section differs: the
memory system, from `primers/memory/<arm>.md`.

That constraint is the experiment. The original box-wheel primer mixed research
discipline and Flywheel mechanics in one 283-line document; handing that to one
arm and nothing to another would measure *good primer versus no primer*, and the
protocol arms would win for a reason that has nothing to do with protocols. The
split makes the memory system the only variable, and `tests/test_primers.py`
holds the three sections to a matched length so prompt bulk cannot leak in as a
confound either.

Arm `git` is a **genuine** control, not a strawman: it teaches commit-as-record,
a running `NOTES.md` / `DECISIONS.md` / `DEAD-ENDS.md`, branch-per-alternative,
and log interrogation. If a protocol cannot beat competent git hygiene, that is
the finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

PRIMERS_DIR = Path(__file__).resolve().parents[1] / "primers"
CORE_PRIMER = PRIMERS_DIR / "_core.md"
MEMORY_DIR = PRIMERS_DIR / "memory"


@dataclass(frozen=True)
class Arm:
    """One experimental condition: a memory system and what it needs on the box."""

    name: str
    label: str
    # Extra bash run during provisioning, after the shared toolchain. Empty for
    # the control — its memory system is git, which every box already has.
    install_sh: str = ""
    # Bash appended only when the harness reads Claude Code's `.claude/skills`.
    claude_skills_sh: str = ""
    # Whether the box needs the Flywheel MCP config wired into `.mcp.json`.
    needs_flywheel_mcp: bool = False

    @property
    def memory_primer_path(self) -> Path:
        return MEMORY_DIR / f"{self.name}.md"

    def memory_primer(self) -> str:
        return self.memory_primer_path.read_text(encoding="utf-8")

    def install_for(self, harness) -> str:
        """This arm's provisioning bash for a given harness.

        The skills bundle is Claude Code-specific — `.claude/skills` is a Claude
        Code convention that pi does not read. Installing it under pi would be
        inert weight and, worse, would imply the protocol arm had a workflow
        layer it does not actually have. Under pi the protocol arm runs on its
        primer and the `hypergraph` CLI alone, and the write-up must say so.
        """
        parts = [self.install_sh]
        if self.claude_skills_sh and getattr(harness, "reads_claude_skills", False):
            parts.append(self.claude_skills_sh)
        return "".join(p for p in parts if p)


# `uv tool install` is deliberately the install path for the hypergraph arm: it
# is the *published* adoption route (PyPI, no clone, no fork), so the arm tests
# what a real adopter gets rather than a dev checkout. `skills install --user`
# puts the five skills where a headless session will find them.
_HYPERGRAPH_INSTALL = """if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv tool install hypergraph-protocol
hypergraph --help >/dev/null || echo "warn: hypergraph CLI not runnable"
"""

_HYPERGRAPH_SKILLS = """hypergraph skills install --user \
  || echo "warn: hypergraph skills install non-zero"
"""

# The flywheel CLI is a secondary read interface — the agent works through the
# HTTP MCP — so a non-zero install is a warning, not a failure.
_FLYWHEEL_INSTALL = """if ! command -v flywheel >/dev/null 2>&1; then
  curl -fsSL https://flywheel.paradigma.inc/install | sh -s -- --mode mcp --yes \
    || echo "warn: flywheel CLI install non-zero (HTTP MCP still configured)"
fi
"""

ARMS: Dict[str, Arm] = {
    "git": Arm(
        name="git",
        label="A — git only (control)",
    ),
    "flywheel": Arm(
        name="flywheel",
        label="B — Flywheel",
        install_sh=_FLYWHEEL_INSTALL,
        needs_flywheel_mcp=True,
    ),
    "hypergraph": Arm(
        name="hypergraph",
        label="C — Hypergraph protocol",
        install_sh=_HYPERGRAPH_INSTALL,
        claude_skills_sh=_HYPERGRAPH_SKILLS,
    ),
}

ARM_ORDER = ("git", "flywheel", "hypergraph")


def get_arm(name: str) -> Arm:
    try:
        return ARMS[name]
    except KeyError:
        raise ValueError(
            f"unknown arm {name!r}; expected one of {', '.join(ARM_ORDER)}"
        ) from None


def compose_primer(arm: Arm, *, core: Optional[str] = None) -> str:
    """The box's `CLAUDE.md`: the shared core plus this arm's memory section.

    Pure string composition (box-wheel's convention) so the exact bytes an arm
    receives can be asserted in a test and rendered for review without spending
    a box.
    """
    core_text = core if core is not None else CORE_PRIMER.read_text(encoding="utf-8")
    return core_text.rstrip("\n") + "\n\n" + arm.memory_primer().strip("\n") + "\n"
