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


def test_hypergraph_arm_installs_the_published_package_at_a_pinned_version(config):
    """The arm must test the real adoption route (PyPI), not a dev checkout.

    Pinned, and asserted on the box: `uv tool install` reuses a cached tool, so
    an unpinned install can silently leave a box running last month's version
    while the write-up names this one.
    """
    import re
    declared = re.search(r'^version = "([^"]+)"',
                         (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    assert arms_mod.HYPERGRAPH_VERSION == declared
    for hname in HARNESS_NAMES:
        script = provision.build_script(
            config, arms_mod.get_arm("hypergraph"), get_harness(hname))
        assert f"uv tool install --force 'hypergraph-protocol=={declared}'" in script
        assert "hypergraph --version" in script
        assert "FATAL: expected hypergraph-protocol" in script
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


# ---- redaction ----------------------------------------------------------------

def test_redaction_removes_every_known_secret_value():
    """Exact values first — the layer that cannot miss what it was told about."""
    from boxlab.redact import redact, secret_values
    values = {
        "OPENROUTER_API_KEY": "sk-or-v1-" + "a" * 40,
        "GITHUB_TOKEN": "ghp_" + "B" * 36,
        "FLYWHEEL_API_KEY": "fw_live_" + "9" * 32,
        "GITHUB_OWNER": "boxwheel",
    }
    secrets = secret_values(values)
    # An account name is not a credential: redacting it would mangle every URL
    # in every transcript and protect nothing.
    assert "GITHUB_OWNER" not in secrets
    out = redact("\n".join(f"{k}={v}" for k, v in values.items()), secrets)
    for name, value in values.items():
        if name == "GITHUB_OWNER":
            assert "boxwheel" in out
        else:
            assert value not in out
            assert f"<REDACTED:{name}>" in out


def test_redaction_catches_secret_shapes_it_was_never_told_about():
    """The layer that matters after a rotation: a key nobody registered.

    `secret_values` only knows the keys this process holds. A token an agent
    minted itself, or one rotated last week and still sitting in an old
    transcript, is caught by shape or not at all.
    """
    from boxlab.redact import redact, scan_text
    text = ("token=ghp_" + "C" * 36 + "\n"
            "export OPENROUTER_API_KEY=sk-or-v1-" + "d" * 44 + "\n"
            "Authorization: Bearer " + "e" * 40 + "\n"
            "github_pat_" + "F" * 30 + "\n")
    assert scan_text(text), "the scanner must see these before redaction"
    out = redact(text, {})  # no known values at all
    assert not scan_text(out), out


def test_redaction_leaves_ordinary_prose_alone():
    """A redactor that mangles transcripts protects nothing anyone will read."""
    from boxlab.redact import redact, secret_values
    prose = ("The tokenization step ran in 4s. GITHUB_OWNER=boxwheel pushed to "
             "https://github.com/boxwheel/word2vec. Password rotation is a "
             "separate task.\n")
    assert redact(prose, secret_values({"GITHUB_OWNER": "boxwheel"})) == prose


def test_short_values_are_never_treated_as_secrets():
    """Replacing a 3-character 'secret' corrupts every file it appears in."""
    from boxlab.redact import secret_values
    assert secret_values({"GITHUB_TOKEN": "abc"}) == {}


def test_redact_archive_rewrites_members_and_reports_the_count(tmp_path):
    """Nothing unredacted may reach disk, so the rewrite happens in memory."""
    import io
    import tarfile
    from boxlab.redact import redact_archive

    key = "sk-or-v1-" + "z" * 40
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, body in (("session.jsonl", f'{{"cmd":"cat .env","out":"{key}"}}'),
                           ("vectors.txt", "the 0.1 0.2 0.3")):
            data = body.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

    cleaned, changed = redact_archive(buf.getvalue(),
                                      {"OPENROUTER_API_KEY": key})
    assert changed == 1
    with tarfile.open(fileobj=io.BytesIO(cleaned)) as tf:
        members = {m.name: tf.extractfile(m).read().decode() for m in tf}
    assert key not in members["session.jsonl"]
    assert "<REDACTED:OPENROUTER_API_KEY>" in members["session.jsonl"]
    # A member's recorded size must follow its rewritten body, or every
    # subsequent member reads at the wrong offset and the archive is scrap.
    assert members["vectors.txt"] == "the 0.1 0.2 0.3"


def test_an_unredactable_archive_is_discarded_not_written():
    """A harvest that cannot be cleaned must not fall back to writing it raw."""
    import inspect
    from boxlab import experiment
    src = inspect.getsource(experiment._harvest)
    assert "redact_archive" in src
    assert "changed < 0" in src
    # The redaction must sit between the decode and the write, not after it.
    # Compared over the body only: the docstring names `write_bytes` too, and
    # matching that instead would make this assertion pass on any ordering.
    body = src.split('"""')[-1]
    assert body.index("redact_archive") < body.index("write_bytes")


def test_no_harvested_file_under_research_runs_contains_a_secret():
    """The standing guarantee: nothing secret-shaped is on disk under runs/.

    This is the test the nine-run benchmark did not have. Twenty transcripts
    carrying live `OPENROUTER_API_KEY` and `GITHUB_TOKEN` values were committed
    across sixteen commits, and nothing failed.
    """
    from boxlab.redact import scan_tree
    runs = ROOT / "research" / "runs"
    findings = scan_tree(runs)
    assert not findings, (
        f"{len(findings)} secret-shaped value(s) under {runs}: "
        + "; ".join(f"{p}:{ln} ({label})" for p, ln, label in findings[:10]))


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


# ---- reporting ----------------------------------------------------------------

def _arm(median, lo, hi, runs=3, vec=3):
    return {"runs": runs, "produced_vectors": vec,
            "accuracy_median": median, "accuracy_range": (lo, hi),
            "accuracy_values": [lo, median, hi],
            "cold_start_s_median": None, "cold_start_s_range": None,
            "orientation_calls_median": None, "tool_calls_median": None,
            "turns_median": None, "cost_usd_median": None}


def test_overlapping_ranges_report_no_detectable_difference():
    """At n=3 an overlapping range means 'not detectable', not a ranking.

    Picking the higher median anyway would invent a result the data does not
    support — the single easiest way for this experiment to mislead.
    """
    from boxlab.report import verdict
    summary = {"git": _arm(0.19, 0.17, 0.21),
               "hypergraph": _arm(0.22, 0.205, 0.24)}
    assert "no detectable difference" in verdict(summary, "accuracy")


def test_separated_ranges_do_report_a_leader():
    from boxlab.report import verdict
    summary = {"git": _arm(0.19, 0.18, 0.20),
               "hypergraph": _arm(0.30, 0.28, 0.32)}
    out = verdict(summary, "accuracy")
    assert "hypergraph leads" in out and "no range overlap" in out


def test_a_missing_measure_prints_as_dash_not_zero():
    """An arm that produced nothing and an arm that scored zero differ."""
    from boxlab.report import _fmt
    assert _fmt(None, ".2%") == "-"
    assert _fmt(0.0, ".2%") == "0.00%"


def test_by_arm_counts_runs_that_produced_no_vectors():
    """A run that produced nothing must still count in `runs`, not vanish."""
    from boxlab.report import by_arm
    runs = [
        {"arm": "git", "totals": {"tool_calls": 10, "assistant_turns": 5,
                                  "cost_usd": 0.01},
         "fidelity": {"total": {"accuracy": 0.2}}},
        {"arm": "git", "totals": {"tool_calls": 8, "assistant_turns": 4,
                                  "cost_usd": 0.02}},
    ]
    summary = by_arm(runs)
    assert summary["git"]["runs"] == 2
    assert summary["git"]["produced_vectors"] == 1


def test_verdict_direction_for_lower_is_better_measures():
    """Cold-start seconds: lower is better. Ranking by highest inverts it.

    An earlier version ranked every measure by highest median and announced the
    SLOWEST arm as the cold-start leader.
    """
    from boxlab.report import verdict
    summary = {
        "fast": {"runs": 3, "usable_vectors": 3, "cold_start_s_median": 5.0,
                 "cold_start_s_range": (4.0, 6.0)},
        "slow": {"runs": 3, "usable_vectors": 3, "cold_start_s_median": 40.0,
                 "cold_start_s_range": (35.0, 45.0)},
    }
    out = verdict(summary, "cold_start_s")
    assert out.startswith("cold_start_s: fast leads"), out
    assert "lowest median" in out


def test_navigation_prefix_does_not_count_as_work():
    """`cd X && git log` is orientation. Prefix-matching `cd` inverted this.

    On the real run this misclassification made the control arm look instantly
    productive when it was still reading, which would have reversed the
    cold-start conclusion.
    """
    from boxlab.analyze import is_orientation_bash
    assert is_orientation_bash("cd ~/research && git log --oneline -30")
    assert is_orientation_bash("cd ~/research")
    assert not is_orientation_bash("cd ~/research && python3 train.py")


def test_chained_commands_need_every_segment_to_be_read_only():
    from boxlab.analyze import is_orientation_bash
    assert is_orientation_bash("ls -la && cat README.md")
    assert not is_orientation_bash("ls -la && rm -rf build")


def test_mcp_reads_are_orientation_but_writes_are_not():
    """Reading your own notes over MCP is orienting, not working."""
    from boxlab.analyze import is_orientation_tool
    assert is_orientation_tool("mcp__flywheel__flywheel_get_node", [])
    assert is_orientation_tool("mcp__flywheel__flywheel_list_nodes", [])
    assert not is_orientation_tool("mcp__flywheel__flywheel_commit_new_node", [])
    assert not is_orientation_tool("write", [])


# ---- isolation: the arms must not be able to reach each other -----------------
#
# On the nine-run benchmark they could, and did. Three runs picked the same repo
# name (`word2vec-skipgram-text8`); two force-pushed over it; one answered a
# rejected push with `git fetch && git reset --hard FETCH_HEAD`, replacing its
# tree with another arm's repo — graph, STATE.md and all — and then read it.

def test_the_harness_assigns_the_repo_name_and_it_is_unique_per_run():
    from boxlab.config import repo_name_for
    names = [repo_name_for(arm, seed)
             for arm in ARM_NAMES for seed in (1, 2, 3)]
    assert len(set(names)) == len(names), names
    assert repo_name_for("hypergraph", 2) == "boxlab-w2v-hypergraph-s2"


def test_publish_helper_refuses_every_argument(config):
    """`publish-repo <name>` is how three runs picked the same repository."""
    script = provision.build_script(config, arms_mod.get_arm("git"),
                                    get_harness("pi"), seed=1)
    assert "publish-repo: takes no arguments." in script
    assert 'if [ "$#" -gt 0 ]; then' in script
    # The name comes from the conf the harness wrote, never from argv.
    assert "BOXLAB_REPO_NAME=boxlab-w2v-git-s1" in script
    assert "BOXLAB_RUN_ID=git-s1" in script


def test_publish_helper_never_force_pushes(config):
    for name in ARM_NAMES:
        script = provision.build_script(config, arms_mod.get_arm(name),
                                        get_harness("pi"), seed=2)
        assert "push --force" not in script
        assert "--force-with-lease" not in script
        assert "git push " in script


def test_publish_helper_refuses_a_repo_another_run_established(config):
    """The run-id marker: a repo that is not this run's is never overwritten."""
    script = provision.build_script(config, arms_mod.get_arm("git"),
                                    get_harness("pi"), seed=3)
    assert ".boxlab-run" in script
    assert "REFUSING to push" in script


def test_each_arm_b_seed_gets_its_own_flywheel_key(config):
    """Three seeds on one account is three seeds reading each other's nodes."""
    config.values["FLYWHEEL_API_KEY_FLYWHEEL_S1"] = "fw-per-run-ONE"
    config.values["FLYWHEEL_API_KEY_FLYWHEEL_S2"] = "fw-per-run-TWO"
    arm = arms_mod.get_arm("flywheel")
    s1 = provision.build_script(config, arm, get_harness("pi"), seed=1)
    s2 = provision.build_script(config, arm, get_harness("pi"), seed=2)
    assert "fw-per-run-ONE" in s1 and "fw-per-run-TWO" not in s1
    assert "fw-per-run-TWO" in s2 and "fw-per-run-ONE" not in s2
    # …and the shared account-wide key reaches neither.
    assert "fw-key-CCC" not in s1 and "fw-key-CCC" not in s2


def test_a_seed_with_no_key_of_its_own_falls_back_only_when_asked(config):
    from boxlab.config import LabConfig
    cfg = LabConfig(values={"FLYWHEEL_API_KEY": "shared-account-key"})
    assert cfg.flywheel_key_for("flywheel", 1) is None
    assert cfg.flywheel_key_for("flywheel", 1,
                                allow_shared=True) == "shared-account-key"


def test_isolation_problems_name_both_failure_modes():
    from boxlab.config import LabConfig
    cfg = LabConfig(values={"FLYWHEEL_API_KEY_FLYWHEEL_S1": "same-key-xxxxxxxx",
                            "FLYWHEEL_API_KEY_FLYWHEEL_S2": "same-key-xxxxxxxx"})
    problems = cfg.flywheel_isolation_problems("flywheel", [1, 2, 3])
    assert any("seed(s) 3" in p for p in problems), problems
    assert any("share one Flywheel key" in p for p in problems), problems
    # All three distinct and present: nothing to report.
    ok = LabConfig(values={f"FLYWHEEL_API_KEY_FLYWHEEL_S{s}": f"key-{s}-xxxxxxxx"
                           for s in (1, 2, 3)})
    assert ok.flywheel_isolation_problems("flywheel", [1, 2, 3]) == []


# ---- provisioning correctness -------------------------------------------------

def test_flywheel_install_passes_a_skill_flag_and_fails_loudly(config):
    """`--mode mcp --yes` exited non-zero on all three arm-B boxes.

    "Non-interactive setup requires one of --install-skill or --skip-skill" —
    so arm B ran with the HTTP MCP, no CLI, and no contract doc, and spent its
    opening turns guessing tool names.
    """
    script = provision.build_script(config, arms_mod.get_arm("flywheel"),
                                    get_harness("pi"), seed=1)
    assert "--skip-skill" in script
    assert "FATAL: flywheel CLI not runnable after install" in script


def test_the_skill_layer_is_present_or_absent_for_BOTH_protocol_arms_together():
    """Whatever pi cannot read, neither protocol arm gets — or it is a confound.

    `.claude/skills` is a Claude Code convention. Giving arm B a skill there
    while arm C goes without would hand B a workflow layer C does not have, in
    the protocol's favour, and the result would measure that instead.
    """
    for hname in HARNESS_NAMES:
        harness = get_harness(hname)
        b = "install-skill" in arms_mod.get_arm("flywheel").install_for(harness)
        c = "skills install" in arms_mod.get_arm("hypergraph").install_for(harness)
        assert b == c == (hname == "claude_code"), (hname, b, c)


def test_arm_c_starts_with_an_initialised_empty_graph(config):
    """Arm B gets an empty Flywheel account; arm C must get the equivalent.

    hypergraph-s1 was given neither, hand-rolled the whole protocol in its second
    phase, never returned to training, and scored lowest in its arm. That
    measured whether the tool ships an init path, not whether the protocol helps.
    """
    script = provision.build_script(config, arms_mod.get_arm("hypergraph"),
                                    get_harness("pi"), seed=2)
    assert "hypergraph new record --root" in script
    assert "hypergraph new state --root --reconcile" in script
    assert "record_root:" in script and "state_root:" in script
    assert "FATAL: seeded hypergraph graph does not pass check" in script
    # Roots only. A seeded state skeleton would overshoot — arm B is not handed
    # one, and building it is part of the work under test.
    assert script.count("hypergraph new state") == 1


def test_only_arm_c_is_seeded(config):
    for name in ("git", "flywheel"):
        script = provision.build_script(config, arms_mod.get_arm(name),
                                        get_harness("pi"), seed=1)
        assert "hypergraph new record --root" not in script


# ---- publishing hygiene -------------------------------------------------------

def test_publish_helper_gates_on_file_size(config):
    """`boxwheel/word2vec-cpu` went public at 2,221 files / 81 MB."""
    script = provision.build_script(config, arms_mod.get_arm("git"),
                                    get_harness("pi"), seed=1)
    assert f"BOXLAB_MAX_FILE_MB={provision.MAX_PUBLISH_FILE_MB}" in script
    assert "EXCLUDED" in script
    assert provision.MAX_PUBLISH_FILE_MB < 100  # GitHub's hard limit


def test_publish_gitignore_excludes_the_bulk_but_keeps_the_source(config):
    script = provision.build_script(config, arms_mod.get_arm("git"),
                                    get_harness("pi"), seed=1)
    # The whole heredoc, not a fixed-width window — a slice that happened to cut
    # an entry short would fail for a reason unrelated to what is ignored.
    start = script.index("cat > .gitignore <<'BOXLAB_GITIGNORE_EOF'")
    body = script[start:script.index("BOXLAB_GITIGNORE_EOF\nfi", start)]
    for entry in ("venv/", ".venv/", "build/", "data/", "*.so", "*.o",
                  "text8*", "*.zip", "*.xz", "runs/", "artifacts/vectors*.txt"):
        assert entry in body, entry
    # NOT excluded, deliberately: a hand-written train.c IS the control arm's
    # work. Dropping `*.c` would delete the evidence it is meant to publish.
    assert "\n*.c\n" not in body


# ---- measurement, re-pre-registered (METRICS.md rev-1) ------------------------

def test_best_recoverable_finds_a_result_the_run_overwrote():
    """git-s2 reached 23.29%, published it, then overwrote the local artifact.

    Scoring only the teardown file reported that run as producing nothing. The
    published vectors and the number in its own record are both still there.
    """
    from boxlab.analyze import best_recoverable, cited_accuracies, fidelity_gap
    record = "Best run so far: 23.29% total accuracy on the Google analogy set."
    scored = [
        {"total": {"accuracy": 0.0009}, "source": "artifacts/vectors.txt"},
        {"total": {"accuracy": 0.2329}, "source": "published/vectors.txt"},
    ]
    best = best_recoverable(scored, cited_accuracies(record))
    assert best and abs(best["total"]["accuracy"] - 0.2329) < 1e-9
    gap = fidelity_gap(scored[0], best)
    assert gap is not None and abs(gap - 0.232) < 0.001


def test_a_better_model_the_run_never_mentions_does_not_count():
    """Otherwise the measure scores the harvest, not the memory system."""
    from boxlab.analyze import best_recoverable, cited_accuracies
    record = "Our best result was 12.00% total accuracy."
    scored = [{"total": {"accuracy": 0.12}, "source": "a"},
              {"total": {"accuracy": 0.31}, "source": "b"}]  # never mentioned
    best = best_recoverable(scored, cited_accuracies(record))
    assert best and abs(best["total"]["accuracy"] - 0.12) < 1e-9


def test_a_run_that_cites_no_number_recovers_nothing():
    from boxlab.analyze import best_recoverable
    assert best_recoverable([{"total": {"accuracy": 0.3}}], []) is None


def test_diverged_candidates_are_never_recoverable():
    from boxlab.analyze import best_recoverable
    scored = [{"total": {"accuracy": 0.30}, "diverged": True}]
    assert best_recoverable(scored, [0.30]) is None


def test_cited_accuracies_ignores_numbers_that_are_not_this_measure():
    """A 0.95 learning-rate decay is not a claim about analogy accuracy."""
    from boxlab.analyze import cited_accuracies
    found = cited_accuracies("lr decay 0.95, 100% of the corpus, acc 0.2203, 23.3%")
    assert 0.2203 in found and 0.233 in found
    assert 0.95 not in found and 1.0 not in found


def test_the_gap_is_null_not_zero_when_a_side_is_missing():
    """A gap between a number and a non-number is not a gap of nothing."""
    from boxlab.analyze import fidelity_gap
    assert fidelity_gap(None, {"total": {"accuracy": 0.2}}) is None
    assert fidelity_gap({"total": {"accuracy": 0.2}}, None) is None
    assert fidelity_gap({"total": {"accuracy": 0.2}}, {"total": {"accuracy": 0.2}}) == 0


def test_cold_start_excludes_runs_with_nothing_to_recover():
    """Two of three arm-B seeds wrote nothing before the cut and were scored anyway."""
    from boxlab.report import by_arm
    def run(rid, prior, seconds):
        return {"run": rid, "arm": "flywheel", "had_prior_state": prior,
                "cold_start": {"time_to_first_productive_s": seconds,
                               "orientation_tool_calls": 4},
                "totals": {"tool_calls": 10, "assistant_turns": 5,
                           "cost_usd": 0.01}}
    summary = by_arm([run("f1", True, 90.0), run("f2", False, 5.0),
                      run("f3", None, 5.0)])
    arm = summary["flywheel"]
    assert arm["cold_start_n"] == 1
    assert arm["cold_start_excluded"] == 2
    assert set(arm["cold_start_excluded_runs"]) == {"f2", "f3"}
    # The two vacuous runs would have dragged the median from 90 to 5 — turning
    # "this arm did not recover its state" into "this arm recovered instantly".
    assert arm["cold_start_s_median"] == 90.0


def test_an_unknown_prior_state_excludes_rather_than_counting_as_no():
    from boxlab.report import by_arm
    summary = by_arm([{"run": "x", "arm": "git", "had_prior_state": None,
                       "cold_start": {"time_to_first_productive_s": 1.0},
                       "totals": {"tool_calls": 1, "assistant_turns": 1,
                                  "cost_usd": 0.0}}])
    assert summary["git"]["cold_start_n"] == 0
    assert summary["git"]["cold_start_excluded"] == 1


def test_cold_start_verdict_uses_eligible_runs_as_its_denominator():
    """An arm with 3 runs but 1 eligible must not read as having n=3."""
    from boxlab.report import verdict
    summary = {
        "a": {"runs": 3, "cold_start_n": 1, "cold_start_s_median": 5.0,
              "cold_start_s_range": (4.0, 6.0)},
        "b": {"runs": 3, "cold_start_n": 3, "cold_start_s_median": 40.0,
              "cold_start_s_range": (35.0, 45.0)},
    }
    assert "not comparable" in verdict(summary, "cold_start_s")


def test_min_n_and_the_direction_table_are_unchanged():
    """Both were correct on the first run and are deliberately not touched."""
    from boxlab.report import HIGHER_IS_BETTER, MIN_N
    assert MIN_N == 3
    assert HIGHER_IS_BETTER["accuracy"] is True
    assert HIGHER_IS_BETTER["cold_start_s"] is False
    assert HIGHER_IS_BETTER["orientation_calls"] is False
    # Lower is better: the gap is work the memory system lost.
    assert HIGHER_IS_BETTER["fidelity_gap"] is False
    assert HIGHER_IS_BETTER["best_recoverable"] is True


def test_the_driver_probes_prior_state_before_it_kills_the_session():
    """Probing after the kill would race the agent's last writes."""
    import inspect
    from boxlab import experiment
    src = inspect.getsource(experiment._run_one)
    assert src.index("_had_prior_state(") < src.index("cold-start cut: killing")
