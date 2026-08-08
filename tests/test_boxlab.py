"""Tests for the benchmark lab's pure builders.

Two things are guarded here, and they fail in different ways if left unguarded.

**The experiment's validity.** The three arms must differ *only* in their memory
section, at a matched length, and a relaunch must be a genuine cold start. Each of
those is a silent confound if it drifts — the run still completes, the charts
still render, and the conclusion is wrong.

**The provisioning bytes.** A provisioning bug costs a whole run to discover, so
the scripts are asserted as strings (box-wheel's convention) rather than
discovered live on a box.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

from boxlab import arms as arms_mod  # noqa: E402
from boxlab import provision, runner  # noqa: E402
from boxlab.config import LabConfig  # noqa: E402

ARM_NAMES = ("git", "flywheel", "hypergraph")


@pytest.fixture
def config():
    """A config with fixed fake secrets — never reads the real .env."""
    return LabConfig(values={
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth-tok-AAA",
        "GITHUB_TOKEN": "gh-tok-BBB",
        "GITHUB_OWNER": "test-owner",
        "FLYWHEEL_API_KEY": "fw-key-CCC",
    })


# ---- the experiment's validity ------------------------------------------------

def test_memory_sections_are_length_matched():
    """Prompt bulk must not leak in as a confound (see arms.py)."""
    counts = {
        name: len(arms_mod.get_arm(name).memory_primer().split())
        for name in ARM_NAMES
    }
    spread = max(counts.values()) / min(counts.values())
    assert spread <= 1.15, f"memory sections are not length-matched: {counts}"


def test_every_arm_gets_the_identical_core():
    core = arms_mod.CORE_PRIMER.read_text(encoding="utf-8").strip()
    for name in ARM_NAMES:
        composed = arms_mod.compose_primer(arms_mod.get_arm(name))
        assert core in composed, f"arm {name} did not receive the shared core"


def test_arms_do_not_leak_each_others_memory_systems():
    """The control must never hear about Flywheel or Hypergraph, and so on."""
    markers = {
        "git": "Your memory system: git and files",
        "flywheel": "Your memory system: Flywheel",
        "hypergraph": "Your memory system: the Hypergraph protocol",
    }
    for name in ARM_NAMES:
        composed = arms_mod.compose_primer(arms_mod.get_arm(name))
        assert markers[name] in composed
        for other, marker in markers.items():
            if other != name:
                assert marker not in composed, f"{name} leaked {other}"


def test_relaunch_is_a_genuine_cold_start():
    """No --resume/--continue: a relaunched session keeps no conversation history.

    This is the entire mechanism behind the cold-start-resilience measure. If a
    flag ever restores session state, the arms would carry their context across
    the intervention and the measure would silently become meaningless.
    """
    for name in ARM_NAMES:
        script = runner.build_launch_script(
            "run1", "do the thing", arms_mod.get_arm(name))
        assert "--resume" not in script
        assert "--continue" not in script


# ---- provisioning bytes -------------------------------------------------------

def test_api_key_is_never_written_to_a_box(config):
    """ANTHROPIC_API_KEY would outrank the OAuth token and bill the API."""
    config.values["ANTHROPIC_API_KEY"] = "sk-ant-SHOULD-NEVER-APPEAR"
    for name in ARM_NAMES:
        script = provision.build_script(config, arms_mod.get_arm(name))
        assert "ANTHROPIC_API_KEY" not in script
        assert "sk-ant-SHOULD-NEVER-APPEAR" not in script


def test_control_arm_gets_no_flywheel_credential_or_mcp(config):
    script = provision.build_script(config, arms_mod.get_arm("git"))
    assert "FLYWHEEL_API_KEY" not in script
    assert "fw-key-CCC" not in script
    # `.mcp.json` appears as a .gitignore entry in the publish helper for every
    # arm; what the control must not get is an actual MCP server declaration.
    assert "mcpServers" not in script
    assert "mcp-server" not in script


def test_flywheel_arm_gets_the_mcp_config(config):
    script = provision.build_script(config, arms_mod.get_arm("flywheel"))
    assert ".mcp.json" in script
    assert "fw-key-CCC" in script
    assert "mcp-server" in script


def test_hypergraph_arm_installs_the_published_package(config):
    """The arm must test the real adoption route (PyPI), not a dev checkout."""
    script = provision.build_script(config, arms_mod.get_arm("hypergraph"))
    assert "uv tool install hypergraph-protocol" in script
    assert "hypergraph skills install" in script
    assert "FLYWHEEL_API_KEY" not in script


def test_marker_records_the_arm_not_just_a_timestamp(config):
    """A box reused across arms must re-provision, or it runs the wrong primer."""
    for name in ARM_NAMES:
        script = provision.build_script(config, arms_mod.get_arm(name))
        assert f'echo "{name} $(date' in script


def test_provisioning_ends_with_the_ok_sentinel(config):
    for name in ARM_NAMES:
        script = provision.build_script(config, arms_mod.get_arm(name))
        assert script.rstrip().endswith(f'echo "{provision.OK_SENTINEL}"')
        assert script.startswith("set -e")


def test_env_file_is_chmod_600(config):
    for name in ARM_NAMES:
        script = provision.build_script(config, arms_mod.get_arm(name))
        assert f"chmod 600 {provision.ENV_PATH}" in script


# ---- launch bytes -------------------------------------------------------------

def test_launch_script_detaches_properly():
    """nohup setsid keeps it alive; < /dev/null lets the ssh call return."""
    script = runner.build_launch_script("r1", "mission", arms_mod.get_arm("git"))
    assert "nohup setsid claude -p" in script
    assert "< /dev/null" in script
    assert "--output-format stream-json" in script
    assert "--dangerously-skip-permissions" in script


def test_mcp_config_flag_only_for_the_flywheel_arm():
    for name in ARM_NAMES:
        script = runner.build_launch_script("r1", "m", arms_mod.get_arm(name))
        assert ("--mcp-config" in script) == (name == "flywheel")


def test_mission_is_shell_quoted():
    """A mission carries prose; unquoted it would be reinterpreted by bash."""
    script = runner.build_launch_script(
        "r1", "implement word2vec; don't $EXPAND `this`", arms_mod.get_arm("git"))
    assert "$EXPAND" in script
    assert "`this`" in script  # inside single quotes — inert
    assert script.count("nohup setsid") == 1


def test_config_never_exposes_secrets_in_describe(config):
    text = config.describe()
    assert "oauth-tok-AAA" not in text
    assert "gh-tok-BBB" not in text
    assert "fw-key-CCC" not in text
    assert "test-owner" in text  # the owner is not a secret, and showing it helps
