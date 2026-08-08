"""Harness descriptors — which agent CLI runs the mission, and how.

The benchmark compares **memory systems**, not agents, so the harness must be a
constant across arms and a variable across runs. This module is the single place
the two supported harnesses differ; everything else takes a `Harness` and stays
ignorant of which one it has.

- **`pi`** (pi.dev) against OpenRouter — the default. Cheap enough to run nine
  three-hour missions, and the model is pinned explicitly rather than inherited.
- **`claude_code`** — Claude Code on the user's subscription. Kept because the
  live smoke test proved the whole chain on it, and because it is the fallback if
  pi turns out to be too weak to reach the paper.

Both descriptors carry lessons from box-wheel that are invisible until they cost
a whole run:

- pi's installer is interactive and bails without a TTY, and pi needs Node ≥
  22.19 while boxes ship Node 20. So Node 22 is dropped into `~/.local` rootlessly
  when needed, and pi is installed with `--ignore-scripts` to skip the
  interactive postinstall.
- **`npm install -g --prefix "$HOME/.local"` is load-bearing.** Without it, a box
  that already ships Node ≥ 22 falls through to the *system* npm, whose global
  prefix is root-owned; the install dies with EACCES, leaving no `pi` and a
  silent zero-byte log at launch.
- **pi rewrites its process title to the bare word `pi`** once running, so a
  launch-shaped `pgrep -f "pi -p"` never matches. box-wheel's liveness probe
  declared healthy agents dead and stopped their boxes mid-mission because of
  this. The match must be an ERE over the full cmdline that catches the retitled
  process without matching `pipewire` or `at-spi`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

# Node 22 rootless drop-in + non-interactive pi install. See the module docstring
# for why each clause is here; none of it is incidental.
_PI_INSTALL = (
    'export PATH="$HOME/.local/bin:$PATH"; '
    'MAJ=$(node -p "process.versions.node.split(\'.\')[0]" 2>/dev/null || echo 0); '
    'if [ "${MAJ:-0}" -lt 22 ]; then '
    'A=$(uname -m); case "$A" in aarch64|arm64) N=arm64;; *) N=x64;; esac; '
    'mkdir -p "$HOME/.local"; '
    'curl -fsSL "https://nodejs.org/dist/v22.19.0/node-v22.19.0-linux-$N.tar.xz" '
    '| tar -xJ -C "$HOME/.local" --strip-components=1; fi; '
    'mkdir -p "$HOME/.local/bin"; '
    'npm install -g --prefix "$HOME/.local" --ignore-scripts '
    '@earendil-works/pi-coding-agent'
)

_CLAUDE_INSTALL = (
    'curl -fsSL https://claude.ai/install.sh | bash || '
    'npm install -g @anthropic-ai/claude-code'
)


@dataclass(frozen=True)
class Harness:
    """One agent CLI: how to install it, authenticate it, launch it, and find it."""

    name: str
    auth_env: str
    cli_bin: str
    install_sh: str
    # ERE over the full cmdline for pgrep -f / pkill -f.
    process_match: str
    # Default model slug, or None to use the CLI's own default.
    default_model: Optional[str] = None
    # Whether the harness reads Claude Code's `.claude/skills` directory. Only
    # Claude Code does; for pi the protocol arm runs on its primer and CLI alone.
    reads_claude_skills: bool = False
    # Whether MCP is wired through the pi adapter rather than Claude's --mcp-config.
    uses_pi_mcp_adapter: bool = False


HARNESSES: Dict[str, Harness] = {
    "pi": Harness(
        name="pi",
        auth_env="OPENROUTER_API_KEY",
        cli_bin="pi",
        install_sh=_PI_INSTALL,
        # Matches the retitled bare "pi" and any path-invoked spelling, while a
        # mid-word "pi" (pipewire, at-spi) stays unmatched.
        process_match=r"(^|/)pi( |$)",
        default_model="deepseek/deepseek-v4-pro",
        uses_pi_mcp_adapter=True,
    ),
    "claude_code": Harness(
        name="claude_code",
        auth_env="CLAUDE_CODE_OAUTH_TOKEN",
        cli_bin="claude",
        install_sh=_CLAUDE_INSTALL,
        process_match="claude -p",
        default_model=None,
        reads_claude_skills=True,
    ),
}

DEFAULT_HARNESS = "pi"


def get_harness(name: Optional[str] = None) -> Harness:
    key = name or DEFAULT_HARNESS
    try:
        return HARNESSES[key]
    except KeyError:
        raise ValueError(
            f"unknown harness {key!r}; expected one of {', '.join(HARNESSES)}"
        ) from None


def build_launch_command(harness: Harness, mission_quoted: str, *,
                         model: Optional[str], mcp_config: bool) -> str:
    """The harness-specific `nohup setsid …` command body (pure).

    `pi` takes the prompt as a positional argument after its flags; `claude`
    takes it after `-p`. Both are print/headless modes, and **neither is passed a
    resume flag** — that is what makes a relaunch a genuine cold start.
    """
    chosen = model or harness.default_model
    if harness.name == "pi":
        model_flag = f"--model {chosen} " if chosen else ""
        # `-p` = print (non-interactive), `-a` trusts the run's project files so a
        # TTY-less launch never blocks on an interactive trust prompt.
        return (f"nohup setsid pi -p -a --provider openrouter "
                f"{model_flag}{mission_quoted} ")
    model_flag = f"--model {chosen} " if chosen else ""
    mcp_flag = "--mcp-config .mcp.json " if mcp_config else ""
    return (f"nohup setsid claude -p {mission_quoted} "
            f"--output-format stream-json --verbose "
            f"--dangerously-skip-permissions {model_flag}{mcp_flag}")
