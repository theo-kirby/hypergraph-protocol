"""Turn a bare box into an arm's agent host — one idempotent bash script.

`build_script` is **pure** (no I/O, no network) so the exact bytes sent to a box
can be asserted in tests. `apply` pipes it to `box ssh <id> bash -s` on stdin, so
the credentials inside it never reach the box's process list.

Adapted from box-wheel's `control/provision.py`, with the parts the benchmark
does not need removed (codex, pi, Kaggle) and one part added: the script is
**arm-aware**. The primer it seeds is `_core.md` + this arm's memory section, and
the toolchain it installs is this arm's.

Two invariants worth restating because breaking either is silent and expensive:

- `ANTHROPIC_API_KEY` is **never** written. On a box it outranks
  `CLAUDE_CODE_OAUTH_TOKEN` and reroutes the run from the subscription to API
  billing — the run still works, so nothing tells you until the invoice.
- The `.provisioned` marker records the **arm**, not just a timestamp. A box
  provisioned for one arm must re-provision if another arm lands on it, or it
  runs with the wrong primer and the wrong memory system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from .arms import Arm, compose_primer
from .box_ctl import BoxController
from .config import (BOX_ENV_VARS, FORBIDDEN_ON_BOX, HARNESS_AUTH_VARS,
                     LabConfig)
from .harness import Harness, get_harness

RESEARCH_DIR = "~/research"
PI_AGENT_DIR = "~/.pi/agent"
PRIMER_PATH = f"{RESEARCH_DIR}/RESEARCH_PRIMER.md"
CLAUDE_MD_PATH = f"{RESEARCH_DIR}/CLAUDE.md"
ENV_PATH = f"{RESEARCH_DIR}/.env"
MCP_PATH = f"{RESEARCH_DIR}/.mcp.json"
MARKER_PATH = f"{RESEARCH_DIR}/.provisioned"
BIN_DIR = f"{RESEARCH_DIR}/bin"
PUBLISH_HELPER_PATH = f"{BIN_DIR}/publish-repo"

# Echoed only if every step succeeded (`set -e` aborts earlier otherwise).
OK_SENTINEL = "BOXLAB_PROVISION_OK"

# Heredoc delimiters. Quoted at the point of use so nothing inside a heredoc is
# expanded by the provisioning shell — the primer and the helper contain `$VAR`
# references that must survive verbatim to be expanded when the agent runs them.
_ENV_EOF = "BOXLAB_ENV_EOF"
_MCP_EOF = "BOXLAB_MCP_EOF"
_PRIMER_EOF = "BOXLAB_PRIMER_EOF"
_HELPER_EOF = "BOXLAB_HELPER_EOF"
_GITIGNORE_EOF = "BOXLAB_GITIGNORE_EOF"
_PI_MODELS_EOF = "BOXLAB_PI_MODELS_EOF"
_PI_SETTINGS_EOF = "BOXLAB_PI_SETTINGS_EOF"
_PI_MCP_EOF = "BOXLAB_PI_MCP_EOF"

# Carried from box-wheel almost verbatim: create-or-reuse a public GitHub repo
# and push. The token is used inline on push so it is never persisted into
# .git/config, and `.env` is re-sourced inside the helper because the box's own
# environment may preset a GITHUB_TOKEN that is not the publishing account's.
_PUBLISH_HELPER = r"""#!/usr/bin/env bash
# publish-repo <repo-name> [source-dir]
set -euo pipefail
NAME="${1:?usage: publish-repo <repo-name> [source-dir]}"
DIR="${2:-.}"
if [ -f "$HOME/research/.env" ]; then
  set -a; . "$HOME/research/.env"; set +a
fi
: "${GITHUB_TOKEN:?GITHUB_TOKEN not set}"
: "${GITHUB_OWNER:?GITHUB_OWNER not set}"
cd "$DIR"
git init -q
git config user.name  "${GIT_AUTHOR_NAME:-boxlab-agent}"
git config user.email "${GIT_AUTHOR_EMAIL:-${GITHUB_OWNER}@users.noreply.github.com}"
if [ ! -f .gitignore ]; then
  cat > .gitignore <<'__GITIGNORE_EOF__'
__pycache__/
*.py[cod]
.ipynb_checkpoints/
.DS_Store
.env
.provisioned
.mcp.json
CLAUDE.md
RESEARCH_PRIMER.md
bin/publish-repo
*.zip
__GITIGNORE_EOF__
fi
git rm -r --cached -q . >/dev/null 2>&1 || true
git add -A
git commit -q -m "${COMMIT_MSG:-boxlab run: ${NAME}}" \
  || echo "publish-repo: nothing new to commit"
code=$(curl -sS -o /tmp/publish_repo.json -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" -H "Accept: application/vnd.github+json" \
  https://api.github.com/user/repos \
  -d "{\"name\":\"${NAME}\",\"private\":${REPO_PRIVATE:-false},\"auto_init\":false}")
case "$code" in
  201) echo "publish-repo: created ${GITHUB_OWNER}/${NAME}" ;;
  422) echo "publish-repo: ${GITHUB_OWNER}/${NAME} exists, reusing" ;;
  *)   echo "publish-repo: create failed (HTTP $code): $(cat /tmp/publish_repo.json)"; exit 1 ;;
esac
git branch -M main
git push "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_OWNER}/${NAME}.git" HEAD:main
echo "publish-repo: pushed https://github.com/${GITHUB_OWNER}/${NAME}"
""".replace("__GITIGNORE_EOF__", _GITIGNORE_EOF)


@dataclass
class ProvisionResult:
    ok: bool
    log: str
    box_id: str


def mcp_config_json(config: LabConfig) -> str:
    """`.mcp.json` wiring the Flywheel HTTP MCP server (bearer auth)."""
    return json.dumps({
        "mcpServers": {
            "flywheel": {
                "type": "http",
                "url": config.flywheel_mcp_url,
                "headers": {
                    "Authorization": f"Bearer {config.flywheel_api_key or ''}"
                },
            }
        }
    }, indent=2)


def env_file_body(config: LabConfig, arm: Arm, harness: Harness) -> str:
    """The box's `~/research/.env`, chmod 600.

    Only what this (arm, harness) pair needs is written. Two omissions are
    deliberate: one harness's token is never readable as another's, and the
    control arm never holds a Flywheel key — an arm that cannot reach a service
    it was never told about is one less way for the comparison to blur.
    """
    lines = []
    for name in BOX_ENV_VARS:
        if name in HARNESS_AUTH_VARS and name != harness.auth_env:
            continue
        if name == "FLYWHEEL_API_KEY" and not arm.needs_flywheel_mcp:
            continue
        lines.append(f"{name}={config.get(name) or ''}")
    for name in FORBIDDEN_ON_BOX:
        assert not any(line.startswith(name + "=") for line in lines), (
            f"{name} must never be written to a box")
    return "\n".join(lines) + "\n"


def pi_config_block(config: LabConfig, arm: Harness, harness: Harness) -> str:
    """pi's three config files: OpenRouter provider, defaults, and MCP.

    The OpenRouter key stays a literal `$OPENROUTER_API_KEY` reference that pi
    interpolates at runtime from the box's `.env`, so it is never duplicated into
    a second file. `defaultProjectTrust: always` is load-bearing on a detached
    launch: without it a TTY-less run blocks forever on an interactive trust
    prompt and writes a zero-byte log.
    """
    model = harness.default_model
    models_json = json.dumps({
        "providers": {
            "openrouter": {
                "baseUrl": "https://openrouter.ai/api/v1",
                "api": "openai-completions",
                "apiKey": "$OPENROUTER_API_KEY",
                "models": ([{"id": model, "name": model}] if model else []),
            }
        }
    }, indent=2)
    settings_json = json.dumps({
        "defaultProvider": "openrouter",
        **({"defaultModel": model} if model else {}),
        "defaultProjectTrust": "always",
    }, indent=2)
    return f"""
# pi config: OpenRouter provider + defaults
mkdir -p {PI_AGENT_DIR}
cat > {PI_AGENT_DIR}/models.json <<'{_PI_MODELS_EOF}'
{models_json}
{_PI_MODELS_EOF}
cat > {PI_AGENT_DIR}/settings.json <<'{_PI_SETTINGS_EOF}'
{settings_json}
{_PI_SETTINGS_EOF}
"""


def pi_mcp_block(config: LabConfig) -> str:
    """pi's Flywheel MCP wiring, read through the pi-mcp-adapter."""
    mcp_json = json.dumps({
        "mcpServers": {
            "flywheel": {
                "url": config.flywheel_mcp_url,
                "headers": {
                    "Authorization": f"Bearer {config.flywheel_api_key or ''}"
                },
                "auth": "bearer",
                "lifecycle": "lazy",
            }
        }
    }, indent=2)
    return f"""
# Flywheel MCP for pi (via the pi-mcp-adapter)
pi install npm:pi-mcp-adapter || echo "warn: pi-mcp-adapter install non-zero"
cat > {PI_AGENT_DIR}/mcp.json <<'{_PI_MCP_EOF}'
{mcp_json}
{_PI_MCP_EOF}
"""


def build_script(config: LabConfig, arm: Arm,
                 harness: Optional[Harness] = None) -> str:
    """The idempotent provisioning bash for one (arm, harness) (pure)."""
    harness = harness or get_harness()
    primer = compose_primer(arm)

    mcp_block = ""
    if arm.needs_flywheel_mcp:
        if harness.uses_pi_mcp_adapter:
            mcp_block = pi_mcp_block(config)
        else:
            mcp_block = f"""
# Flywheel MCP server config (Claude Code reads it via --mcp-config)
cat > {MCP_PATH} <<'{_MCP_EOF}'
{mcp_config_json(config)}
{_MCP_EOF}
"""

    harness_config_block = ""
    if harness.name == "pi":
        harness_config_block = pi_config_block(config, arm, harness)

    arm_block = ""
    install = arm.install_for(harness)
    if install:
        arm_block = f"\n# arm toolchain: {arm.label}\n{install}"

    return f"""set -e
mkdir -p {RESEARCH_DIR}/runs {RESEARCH_DIR}/artifacts {BIN_DIR}
cd {RESEARCH_DIR}

# 1. harness CLI: {harness.name} (install only if missing)
if ! command -v {harness.cli_bin} >/dev/null 2>&1; then
  {harness.install_sh}
fi
export PATH="$HOME/.local/bin:$HOME/.flywheel/bin:$PATH"

# 2. credentials — chmod 600; the heredoc keeps keys out of the process list
cat > {ENV_PATH} <<'{_ENV_EOF}'
{env_file_body(config, arm, harness)}{_ENV_EOF}
chmod 600 {ENV_PATH}
{harness_config_block}{arm_block}
{mcp_block}
# 3. primer -> RESEARCH_PRIMER.md + CLAUDE.md (agents auto-load CLAUDE.md from
#    the working directory). Shared core + this arm's memory section.
cat > {PRIMER_PATH} <<'{_PRIMER_EOF}'
{primer}{_PRIMER_EOF}
cp {PRIMER_PATH} {CLAUDE_MD_PATH}

# 4. publish-repo helper. Quoted heredoc so $GITHUB_TOKEN expands when the agent
#    RUNS it, not now.
cat > {PUBLISH_HELPER_PATH} <<'{_HELPER_EOF}'
{_PUBLISH_HELPER}{_HELPER_EOF}
chmod +x {PUBLISH_HELPER_PATH}

# 5. verify (best-effort) + drop the arm+harness-stamped marker
{harness.cli_bin} --version || echo "warn: {harness.cli_bin} --version non-zero"
git --version || echo "warn: git not found (publish-repo will fail)"
python3 --version || echo "warn: python3 not found"
echo "{arm.name} {harness.name} $(date -u +%Y-%m-%dT%H:%M:%SZ)" > {MARKER_PATH}
echo "{OK_SENTINEL}"
"""


def provisioned_as(box_id: str, box: Optional[BoxController] = None
                   ) -> Optional[tuple]:
    """The `(arm, harness)` a box was provisioned for, or None.

    The marker's first two tokens are the arm and the harness. Both matter: a box
    reused under a different arm runs the wrong primer, and one reused under a
    different harness has the wrong CLI and the wrong auth variable. Scanning
    lines rather than reading the whole output matters — ssh banners interleave.
    """
    ctl = box or BoxController()
    try:
        _, out = ctl.ssh_exec(
            box_id, f"cat {MARKER_PATH} 2>/dev/null || true\n", timeout=45.0)
    except Exception:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in {"git", "flywheel", "hypergraph"}:
            return (parts[0], parts[1])
    return None


def apply(box_id: str, config: LabConfig, arm: Arm,
          harness: Optional[Harness] = None, *,
          box: Optional[BoxController] = None,
          force: bool = False) -> ProvisionResult:
    """Run the provisioning script. Skipped only on an exact arm+harness match."""
    harness = harness or get_harness()
    ctl = box or BoxController()
    if not force and provisioned_as(box_id, ctl) == (arm.name, harness.name):
        return ProvisionResult(ok=True, log="already provisioned for this arm",
                               box_id=box_id)
    rc, out = ctl.ssh_exec(box_id, build_script(config, arm, harness),
                           timeout=1200.0)
    return ProvisionResult(ok=(rc == 0 and OK_SENTINEL in out), log=out,
                           box_id=box_id)
