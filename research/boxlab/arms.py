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

import re
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
    # Bash that leaves this arm's memory system **initialised and empty**, run
    # after the toolchain. `{run_id}` is substituted with the run's id.
    #
    # This exists because the arms were not comparable without it. Arm B was
    # handed a Flywheel account that already existed: the agent's first act could
    # be to write a node. Arm C was handed nothing — no `.hypergraph/`, no
    # config, no roots — so hypergraph-s1 spent its **entire second phase**
    # standing the protocol up by hand (`mkdir -p .hypergraph/graph/record …`,
    # a hand-written config.yml, skills found by grepping site-packages) and
    # never got back to training. It scored lowest in its arm.
    #
    # That measured "does the tool ship an init path", not "does the protocol
    # help". Both arms now start from the same place: a memory system that
    # exists, with nothing in it.
    seed_sh: str = ""

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


# The version every hypergraph-arm box installs. Read from pyproject rather than
# repeated, so a release cannot leave the benchmark measuring a version that no
# longer exists. `uv tool install pkg==X` pins it; the assertion below catches the
# case where a cached tool install silently kept an older one.
def _pinned_version() -> str:
    text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(
        encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', text, re.M)
    if not match:
        raise RuntimeError("cannot read `version` from pyproject.toml")
    return match.group(1)


HYPERGRAPH_VERSION = _pinned_version()

# `uv tool install` is deliberately the install path for the hypergraph arm: it
# is the *published* adoption route (PyPI, no clone, no fork), so the arm tests
# what a real adopter gets rather than a dev checkout.
_HYPERGRAPH_INSTALL = f"""if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv tool install --force 'hypergraph-protocol=={HYPERGRAPH_VERSION}'
got=$(hypergraph --version 2>&1 | tr -d '\\r')
case "$got" in
  *"{HYPERGRAPH_VERSION}"*) echo "hypergraph pinned: $got" ;;
  *) echo "FATAL: expected hypergraph-protocol {HYPERGRAPH_VERSION}, got '$got'"; exit 1 ;;
esac
"""

# `skills install --user` puts the five skills where a headless session finds
# them. Claude Code only — `.claude/skills` is a convention pi does not read.
_HYPERGRAPH_SKILLS = """hypergraph skills install --user \
  || echo "warn: hypergraph skills install non-zero"
"""

# Arm C's memory system, initialised and empty — the counterpart to arm B's empty
# Flywheel account.
#
# The asymmetry this removes is not cosmetic. A Flywheel account with zero nodes
# still *accepts* `commit_new_node`: arm B's first act can be to record work. A
# `.hypergraph/` directory with no config and no roots accepts nothing, so arm C's
# first act had to be building the memory system — and on the nine-run benchmark
# that consumed hypergraph-s1's entire second phase, hand-rolling `mkdir -p`, a
# hand-written config, and skills found by grepping site-packages. It never
# returned to training and scored lowest in its arm.
#
# Roots and a valid config, and nothing more. A seeded state *skeleton* would
# overshoot: arm B is not handed one, and building it is part of the work under
# test. `--reconcile` on the state root is honest — establishing state is exactly
# what a reconcile pass does (SPEC I3).
_HYPERGRAPH_SEED = """cd ~/research
export PATH="$HOME/.local/bin:$PATH"
if [ ! -f .hypergraph/config.yml ]; then
  mkdir -p .hypergraph/graph/record .hypergraph/graph/state .hypergraph/cache
  cat > /tmp/boxlab-record-root.md <<'BOXLAB_ROOT_EOF'
## What
Record root for this project. Every unit of work recorded here traces back to
this node.

## Why
The protocol needs one causal anchor per graph.

## Method
Created by the box provisioning step, before the research session started.

## Result
An empty record graph, ready for its first unit of work.

## Repo
No commit yet.
BOXLAB_ROOT_EOF
  cat > /tmp/boxlab-state-root.md <<'BOXLAB_ROOT_EOF'
## Intent
State root for this project. Every state node descends from here. The state graph
tracks what is true now: open work, working components, negative knowledge, and
the frontier of what to do next.
BOXLAB_ROOT_EOF
  REC=$(hypergraph new record --root --title "Record root" \
    --body /tmp/boxlab-record-root.md | awk 'NR==1{print $1}')
  ST=$(hypergraph new state --root --reconcile --title "State root" \
    --body /tmp/boxlab-state-root.md | awk 'NR==1{print $1}')
  if [ -z "$REC" ] || [ -z "$ST" ]; then
    echo "FATAL: hypergraph root creation produced no slug (rec='$REC' state='$ST')"
    exit 1
  fi
  cat > .hypergraph/config.yml <<BOXLAB_CONF_EOF
project: BOXLAB_RUN_ID
backend: local
graph_dir: .hypergraph/graph
cache_dir: .hypergraph/cache
state_md: STATE.md
record_root:
  slug: $REC
state_root:
  slug: $ST
BOXLAB_CONF_EOF
  rm -f /tmp/boxlab-record-root.md /tmp/boxlab-state-root.md
fi
hypergraph export
hypergraph check --record .hypergraph/cache/record.json \
  --state .hypergraph/cache/state.json --config .hypergraph/config.yml \
  || { echo "FATAL: seeded hypergraph graph does not pass check"; exit 1; }
hypergraph render --state .hypergraph/cache/state.json \
  --config .hypergraph/config.yml -o STATE.md
"""

# Arm B's toolchain. The `--mode mcp --yes` form used on the nine-run benchmark
# **exited non-zero on all three boxes**: "Non-interactive setup requires one of
# --install-skill or --skip-skill". Arm B therefore ran with the HTTP MCP and no
# CLI at all, and spent its opening turns probing whether the tool was
# `flywheel_get_contract` or `flywheel_flywheel_get_contract`, `section` or
# `section_id`, `limit` or `page_size` — every call duplicated.
#
# `--skip-skill` rather than `--install-skill` under pi, for the same reason arm C
# omits its skills bundle there: the skill is a host-agent convention pi does not
# read. Installing one for B and not C would hand arm B a workflow layer arm C
# does not have, which is a confound in the protocol's favour. Under Claude Code
# both arms get their skill (see `claude_skills_sh`).
#
# A failed install is now fatal, not a warning. "Configured but unusable" is the
# state that produced the P1/P2 findings, and it printed BOXLAB_PROVISION_OK.
_FLYWHEEL_INSTALL = """if ! command -v flywheel >/dev/null 2>&1; then
  curl -fsSL https://flywheel.paradigma.inc/install | sh -s -- \
    --mode mcp --yes --skip-skill
fi
export PATH="$HOME/.local/bin:$HOME/.flywheel/bin:$PATH"
flywheel --version \
  || { echo "FATAL: flywheel CLI not runnable after install"; exit 1; }
"""

_FLYWHEEL_SKILLS = """flywheel setup --mode mcp --yes --claude --install-skill --force \
  || echo "warn: flywheel skill install non-zero"
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
        claude_skills_sh=_FLYWHEEL_SKILLS,
        needs_flywheel_mcp=True,
    ),
    "hypergraph": Arm(
        name="hypergraph",
        label="C — Hypergraph protocol",
        install_sh=_HYPERGRAPH_INSTALL,
        claude_skills_sh=_HYPERGRAPH_SKILLS,
        seed_sh=_HYPERGRAPH_SEED,
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
