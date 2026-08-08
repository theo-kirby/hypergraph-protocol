"""Credential resolution for the benchmark lab — env-gated, with stated provenance.

Nothing here touches the network. It answers one question: *which secrets do we
have, and where did each come from?* Provenance is tracked per variable and
surfaced by `describe()` because the alternative — a value silently arriving from
a file the operator forgot about — is how a run ends up billed to the wrong
account or authenticated as the wrong GitHub user.

Resolution order, first hit wins:

1. the process environment,
2. this repo's `.env`,
3. the fallback env file (`$BOXLAB_ENV_FILE`, default `~/box-wheel/.env`).

Step 3 exists because box-wheel already holds this exact account set, and copying
long-lived tokens between dotfiles multiplies the places a leak can come from.
It is opt-out: set `BOXLAB_ENV_FILE=` (empty) to resolve from this repo alone.

**`ANTHROPIC_API_KEY` is deliberately absent from every list below.** On a box it
outranks `CLAUDE_CODE_OAUTH_TOKEN` and silently reroutes the run from the
subscription to API billing — a box-wheel lesson, and an expensive one to
rediscover. `forbidden_on_box()` names it so provisioning can refuse to write it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_ENV = REPO_ROOT / ".env"
DEFAULT_FALLBACK_ENV = Path.home() / "box-wheel" / ".env"

# Written into the box's ~/research/.env. Order is the file's order.
BOX_ENV_VARS = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_OWNER",
    "FLYWHEEL_API_KEY",
)

# Never write these onto a box, whatever the local environment holds.
FORBIDDEN_ON_BOX = ("ANTHROPIC_API_KEY",)

# What each arm actually needs. Arm C needs no service credential at all — the
# Hypergraph backend for the run is `local`, so its memory system is files in the
# agent's own git repo. That asymmetry is a finding, not an oversight: it is the
# cheapest of the three to stand up.
ARM_REQUIREMENTS: Dict[str, tuple] = {
    "git": ("CLAUDE_CODE_OAUTH_TOKEN", "GITHUB_TOKEN", "GITHUB_OWNER"),
    "flywheel": ("CLAUDE_CODE_OAUTH_TOKEN", "GITHUB_TOKEN", "GITHUB_OWNER",
                 "FLYWHEEL_API_KEY"),
    "hypergraph": ("CLAUDE_CODE_OAUTH_TOKEN", "GITHUB_TOKEN", "GITHUB_OWNER"),
}

DEFAULT_FLYWHEEL_API_URL = "https://flywheel.paradigma.inc"


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a dotenv file into a dict. Tolerant: skips comments and junk lines.

    Deliberately minimal — no `export` handling, no interpolation, no quoting
    rules beyond stripping one matched pair. A dotenv parser that tries to be
    clever is a parser that silently mangles a token.
    """
    out: Dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def fallback_env_path() -> Optional[Path]:
    """The box-wheel dotenv to fall back to, or None when opted out.

    `BOXLAB_ENV_FILE` set to the empty string means "this repo only" — an
    explicit opt-out, distinct from the variable being unset (use the default).
    """
    raw = os.environ.get("BOXLAB_ENV_FILE")
    if raw is None:
        return DEFAULT_FALLBACK_ENV
    raw = raw.strip()
    return Path(raw).expanduser() if raw else None


def mask(value: Optional[str]) -> str:
    """Render a secret for logs: length and last 4 only, never the secret."""
    if not value:
        return "(unset)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"…{value[-4:]} ({len(value)} chars)"


@dataclass
class LabConfig:
    """Resolved credentials plus a per-variable record of where each came from."""

    values: Dict[str, str] = field(default_factory=dict)
    sources: Dict[str, str] = field(default_factory=dict)
    flywheel_api_url: str = DEFAULT_FLYWHEEL_API_URL

    @classmethod
    def load(cls) -> "LabConfig":
        repo = parse_env_file(REPO_ENV)
        fb_path = fallback_env_path()
        fallback = parse_env_file(fb_path) if fb_path else {}

        values: Dict[str, str] = {}
        sources: Dict[str, str] = {}
        names = set(BOX_ENV_VARS) | {"BOX_API_KEY", "FLYWHEEL_API_URL"}
        for name in names:
            for value, origin in (
                (os.environ.get(name), "process env"),
                (repo.get(name), str(REPO_ENV)),
                (fallback.get(name), str(fb_path) if fb_path else ""),
            ):
                if value:
                    values[name] = value
                    sources[name] = origin
                    break
        return cls(
            values=values,
            sources=sources,
            flywheel_api_url=values.get("FLYWHEEL_API_URL",
                                        DEFAULT_FLYWHEEL_API_URL),
        )

    # ---- accessors --------------------------------------------------------

    def get(self, name: str) -> Optional[str]:
        return self.values.get(name)

    @property
    def claude_oauth_token(self) -> Optional[str]:
        return self.values.get("CLAUDE_CODE_OAUTH_TOKEN")

    @property
    def github_token(self) -> Optional[str]:
        return self.values.get("GITHUB_TOKEN")

    @property
    def github_owner(self) -> Optional[str]:
        return self.values.get("GITHUB_OWNER")

    @property
    def flywheel_api_key(self) -> Optional[str]:
        return self.values.get("FLYWHEEL_API_KEY")

    @property
    def flywheel_mcp_url(self) -> str:
        return self.flywheel_api_url.rstrip("/") + "/mcp-server"

    # ---- gates ------------------------------------------------------------

    def missing_for(self, arm: str) -> list:
        """Credential names the given arm needs and does not have."""
        try:
            required = ARM_REQUIREMENTS[arm]
        except KeyError:
            raise ValueError(
                f"unknown arm {arm!r}; expected one of "
                f"{', '.join(sorted(ARM_REQUIREMENTS))}") from None
        return [name for name in required if not self.values.get(name)]

    def require(self, arm: str) -> None:
        """Raise with actionable instructions if the arm cannot run."""
        missing = self.missing_for(arm)
        if not missing:
            return
        fb = fallback_env_path()
        where = f"{REPO_ENV}" + (f", or {fb}" if fb else "")
        raise RuntimeError(
            f"arm {arm!r} needs {', '.join(missing)} — not found in the process "
            f"environment, {where}.\n"
            "Add them to one of those files (KEY=value, one per line), or set "
            "BOXLAB_ENV_FILE to a dotenv that has them."
        )

    def describe(self) -> str:
        """A masked, provenance-annotated dump — safe to print or paste."""
        lines = ["boxlab credentials:"]
        for name in (*BOX_ENV_VARS, "BOX_API_KEY"):
            value = self.values.get(name)
            origin = self.sources.get(name, "—")
            # GITHUB_OWNER is an account name, not a secret; showing it is the
            # point (publishing to the wrong owner is a real failure mode).
            shown = value if name == "GITHUB_OWNER" and value else mask(value)
            lines.append(f"  {name:<26} {shown:<22} [{origin}]")
        lines.append(f"  flywheel api url           {self.flywheel_api_url}")
        for name in FORBIDDEN_ON_BOX:
            if os.environ.get(name):
                lines.append(
                    f"  NOTE: {name} is set locally and will NOT be sent to any "
                    "box (it would outrank the OAuth token and bill the API).")
        for arm in sorted(ARM_REQUIREMENTS):
            missing = self.missing_for(arm)
            status = "ready" if not missing else f"missing {', '.join(missing)}"
            lines.append(f"  arm {arm:<12} {status}")
        return "\n".join(lines)


def forbidden_on_box() -> tuple:
    """Names provisioning must never write into a box's environment."""
    return FORBIDDEN_ON_BOX
