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
from boxlab.harness import HARNESSES, get_harness  # noqa: E402

ARM_NAMES = ("git", "flywheel", "hypergraph")
HARNESS_NAMES = ("pi", "claude_code")


@pytest.fixture
def config():
    """A config with fixed fake secrets — never reads the real .env."""
    return LabConfig(values={
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth-tok-AAA",
        "OPENROUTER_API_KEY": "or-key-DDD",
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
    the intervention and the measure would silently become meaningless. It must
    hold for every harness, not just the one the smoke test happened to use.
    """
    for hname in HARNESS_NAMES:
        for name in ARM_NAMES:
            script = runner.build_launch_script(
                "run1", "do the thing", arms_mod.get_arm(name),
                get_harness(hname))
            assert "--resume" not in script
            assert "--continue" not in script


# ---- provisioning bytes -------------------------------------------------------

def test_api_key_is_never_written_to_a_box(config):
    """ANTHROPIC_API_KEY would outrank the OAuth token and bill the API."""
    config.values["ANTHROPIC_API_KEY"] = "sk-ant-SHOULD-NEVER-APPEAR"
    for name in ARM_NAMES:
        for hname in HARNESS_NAMES:
            script = provision.build_script(
                config, arms_mod.get_arm(name), get_harness(hname))
            assert "ANTHROPIC_API_KEY" not in script
            assert "sk-ant-SHOULD-NEVER-APPEAR" not in script


def test_control_arm_gets_no_flywheel_credential_or_mcp(config):
    script = provision.build_script(config, arms_mod.get_arm("git"),
                                    get_harness("pi"))
    assert "FLYWHEEL_API_KEY" not in script
    assert "fw-key-CCC" not in script
    # `.mcp.json` appears as a .gitignore entry in the publish helper for every
    # arm; what the control must not get is an actual MCP server declaration.
    assert "mcpServers" not in script
    assert "mcp-server" not in script


def test_flywheel_arm_gets_the_mcp_config(config):
    """Both harnesses wire Flywheel MCP, by different mechanisms."""
    pi_script = provision.build_script(config, arms_mod.get_arm("flywheel"),
                                       get_harness("pi"))
    assert "pi-mcp-adapter" in pi_script
    assert "fw-key-CCC" in pi_script
    assert "mcp-server" in pi_script

    cc_script = provision.build_script(config, arms_mod.get_arm("flywheel"),
                                       get_harness("claude_code"))
    assert "mcpServers" in cc_script
    assert "fw-key-CCC" in cc_script


def test_hypergraph_arm_installs_the_published_package(config):
    """The arm must test the real adoption route (PyPI), not a dev checkout."""
    for hname in HARNESS_NAMES:
        script = provision.build_script(
            config, arms_mod.get_arm("hypergraph"), get_harness(hname))
        assert "uv tool install hypergraph-protocol" in script
        assert "FLYWHEEL_API_KEY" not in script
        # `.claude/skills` is a Claude Code convention pi does not read, so the
        # skills bundle must be installed for one harness and omitted for the
        # other — installing it under pi would imply a workflow layer arm C
        # does not actually have there.
        assert ("hypergraph skills install" in script) == (hname == "claude_code")


def test_marker_records_the_arm_not_just_a_timestamp(config):
    """A box reused across arms must re-provision, or it runs the wrong primer."""
    for name in ARM_NAMES:
        for hname in HARNESS_NAMES:
            script = provision.build_script(
                config, arms_mod.get_arm(name), get_harness(hname))
            assert f'echo "{name} {hname} $(date' in script


def test_provisioning_ends_with_the_ok_sentinel(config):
    for hname in HARNESS_NAMES:
        for name in ARM_NAMES:
            script = provision.build_script(
                config, arms_mod.get_arm(name), get_harness(hname))
            assert script.rstrip().endswith(f'echo "{provision.OK_SENTINEL}"')
            assert script.startswith("set -e")


def test_env_file_is_chmod_600(config):
    for name in ARM_NAMES:
        script = provision.build_script(config, arms_mod.get_arm(name),
                                        get_harness("pi"))
        assert f"chmod 600 {provision.ENV_PATH}" in script


# ---- launch bytes -------------------------------------------------------------

def test_launch_script_detaches_properly():
    """nohup setsid keeps it alive; < /dev/null lets the ssh call return."""
    for hname in HARNESS_NAMES:
        h = get_harness(hname)
        script = runner.build_launch_script(
            "r1", "mission", arms_mod.get_arm("git"), h)
        assert f"nohup setsid {h.cli_bin} -p" in script
        assert "< /dev/null" in script


def test_pi_launch_pins_the_model_and_provider():
    """The model must be explicit — an inherited default is not reproducible."""
    script = runner.build_launch_script(
        "r1", "m", arms_mod.get_arm("git"), get_harness("pi"))
    assert "--provider openrouter" in script
    assert "--model deepseek/deepseek-v4-pro" in script
    assert "-a " in script  # trust project files: a TTY-less run must not block


def test_pi_process_match_survives_the_retitle():
    """pi retitles itself to bare `pi`; a launch-shaped pattern kills healthy runs."""
    match = get_harness("pi").process_match
    import re
    assert re.search(match, "pi")
    assert re.search(match, "/home/user/.local/bin/pi -p -a")
    assert not re.search(match, "/usr/bin/pipewire")
    assert not re.search(match, "/usr/lib/at-spi-bus-launcher")


def test_mcp_config_flag_only_for_the_flywheel_arm():
    """Claude Code takes --mcp-config; pi reads its adapter config from disk."""
    for name in ARM_NAMES:
        script = runner.build_launch_script(
            "r1", "m", arms_mod.get_arm(name), get_harness("claude_code"))
        assert ("--mcp-config" in script) == (name == "flywheel")


def test_one_harness_token_is_never_readable_as_anothers(config):
    """A box gets exactly one harness auth variable — its own."""
    for hname in HARNESS_NAMES:
        h = get_harness(hname)
        script = provision.build_script(config, arms_mod.get_arm("git"), h)
        assert f"{h.auth_env}=" in script
        for other in HARNESS_NAMES:
            if other != hname:
                assert f"{get_harness(other).auth_env}=" not in script


def test_mission_is_shell_quoted():
    """A mission carries prose; unquoted it would be reinterpreted by bash."""
    script = runner.build_launch_script(
        "r1", "implement word2vec; don't $EXPAND `this`", arms_mod.get_arm("git"),
        get_harness("pi"))
    assert "$EXPAND" in script
    assert "`this`" in script  # inside single quotes — inert
    assert script.count("nohup setsid") == 1


def test_config_never_exposes_secrets_in_describe(config):
    text = config.describe()
    assert "oauth-tok-AAA" not in text
    assert "gh-tok-BBB" not in text
    assert "fw-key-CCC" not in text
    assert "test-owner" in text  # the owner is not a secret, and showing it helps


# ---- harvest ------------------------------------------------------------------

def test_harvest_collects_session_transcripts_not_just_the_workspace():
    """pi's run log holds only the final answer; the sessions hold the measures.

    Measures 2 and 3 are computed from the harness session JSONL. A harvest that
    took only ~/research would leave every run unmeasurable, and nothing would
    report it until analysis time.
    """
    import inspect
    from boxlab import experiment
    src = inspect.getsource(experiment._harvest)
    assert ".pi/agent/sessions" in src
    assert ".claude/projects" in src


def test_harvest_excludes_live_credentials():
    """.env and the MCP bearer must be dropped at the source, not filtered later."""
    import inspect
    from boxlab import experiment
    src = inspect.getsource(experiment._harvest)
    assert "--exclude=research/.env" in src
    assert "--exclude='.pi/agent/mcp.json'" in src


def test_spend_guard_treats_an_unreadable_status_as_exceeded():
    """Launching blind is how a budget cap becomes decorative."""
    from boxlab.spend import SpendGuard
    guard = SpendGuard.__new__(SpendGuard)
    guard.api_key, guard.budget_usd, guard.start_usage = "k", 10.0, 0.0
    guard.spent = lambda: None
    assert guard.exceeded() is True
    guard.spent = lambda: 9.99
    assert guard.exceeded() is False
    guard.spent = lambda: 10.0
    assert guard.exceeded() is True


# ---- analysis ------------------------------------------------------------------

def test_reasoning_tokens_are_priced_as_output():
    """pi reports cost 0 for a custom provider; a reasoning model is not free.

    `usage.reasoning` is not included in `usage.output`, so pricing only `output`
    understates a reasoning model's cost — silently, and in the direction that
    makes the run look cheaper than it was.
    """
    from boxlab.analyze import PRICING, SessionMetrics, Turn
    s = SessionMetrics(harness="pi", model="deepseek/deepseek-v4-pro")
    s.turns = [Turn(timestamp=0.0, input_tokens=1000, output_tokens=100,
                    reasoning_tokens=900)]
    price = PRICING["deepseek/deepseek-v4-pro"]
    expected = 1000 * price["input"] + 1000 * price["output"]
    assert abs(s.cost_usd() - expected) < 1e-12
    assert s.cost_usd() is not None and s.cost_usd() > 0


def test_unknown_model_reports_no_cost_rather_than_zero():
    """A missing price must read as unknown, never as free."""
    from boxlab.analyze import SessionMetrics, Turn
    s = SessionMetrics(harness="pi", model="some/unlisted-model")
    s.turns = [Turn(timestamp=0.0, input_tokens=10, output_tokens=10)]
    assert s.cost_usd() is None


def test_orientation_is_distinguished_from_work():
    """Reading/listing is orientation; writing or a real command is work."""
    from boxlab.analyze import SessionMetrics, Turn
    s = SessionMetrics(harness="pi", model="deepseek/deepseek-v4-pro")
    s.started_at = 100.0
    s.turns = [
        Turn(timestamp=110.0, tools=["read"]),
        Turn(timestamp=120.0, tools=["bash"], bash_commands=["ls -la ~/research"]),
        Turn(timestamp=130.0, tools=["bash"], bash_commands=["git log --oneline"]),
        Turn(timestamp=140.0, tools=["write"]),
    ]
    assert s.first_productive(strict=True) == 40.0   # the write
    assert s.first_productive(strict=False) == 10.0  # the first read


def test_read_only_bash_matcher_is_anchored():
    """`lsof` is not `ls`, and `catalogue` is not `cat`."""
    from boxlab.analyze import READ_ONLY_BASH
    assert READ_ONLY_BASH.match("ls -la")
    assert READ_ONLY_BASH.match("git log --oneline")
    assert not READ_ONLY_BASH.match("lsof -i")
    assert not READ_ONLY_BASH.match("catalogue.py")
    assert not READ_ONLY_BASH.match("python3 train.py")
    assert not READ_ONLY_BASH.match("git commit -m x")


def test_spend_guard_measures_account_usage_not_key_usage():
    """The key's own `usage` field does not track real spend.

    Measured live: a 27-minute run moved the key field by $0.02 and the account
    total by $0.82. A guard on the key field would report 2% of budget used while
    spending forty times that, and would never trip.
    """
    import inspect
    from boxlab import spend as spend_mod
    src = inspect.getsource(spend_mod.SpendGuard)
    assert "account_usage" in src
    assert "key_status(api_key).usage" not in src


# ---- driver recovery ----------------------------------------------------------

def test_driver_log_parse_recovers_boxes_and_launch_times(tmp_path):
    """A dead driver's log must be enough to rebuild the whole schedule.

    The driver holds the schedule in memory, so if it dies the agents keep
    working (they are detached) but nothing cuts, harvests, or stops them. This
    happened: a caller-side timeout killed the first nine-box driver ten minutes
    into a two-hour run.
    """
    from boxlab.attach import parse_driver_log
    log = tmp_path / "driver.log"
    log.write_text(
        "[22:58:20] git-s2: box bx_epyadecb\n"
        "[22:58:23] git-s2: provisioning arm=git harness=pi\n"
        "[22:59:31] git-s2: phase 1 launched (detached; ssh did not return)\n"
        "[22:59:47] flywheel-s2: box bx_t7bhu5d4\n"
        "[23:00:03] flywheel-s2: phase 1 launched (detached)\n"
        "[23:00:15] hypergraph-s3: box bx_9kwgwta6\n",  # never launched
        encoding="utf-8")
    specs = parse_driver_log(log, day_epoch=0.0)
    by_id = {s.run_id: s for s in specs}
    # A box with no launch line is not an in-flight run and must not be resumed.
    assert set(by_id) == {"git-s2", "flywheel-s2"}
    assert by_id["git-s2"].box_id == "bx_epyadecb"
    assert by_id["git-s2"].arm == "git" and by_id["git-s2"].seed == 2
    # Timing comes from the launch line, not the box line.
    assert by_id["git-s2"].phase1_launched_at == 22 * 3600 + 59 * 60 + 31


def test_a_late_cold_start_cut_is_skipped_not_forced(tmp_path):
    """Firing the cut late would look like a measurement and not be one."""
    import inspect
    from boxlab import attach
    src = inspect.getsource(attach.finish_runs)
    assert "skip = now > cut_at" in src
