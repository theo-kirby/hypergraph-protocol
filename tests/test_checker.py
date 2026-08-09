"""Checker tests over committed fixtures: clean passes, each seeded violation is caught."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools" / "fixtures"

_spec = importlib.util.spec_from_file_location("hypergraph", ROOT / "tools" / "hypergraph.py")
hg = importlib.util.module_from_spec(_spec)
sys.modules["hypergraph"] = hg
_spec.loader.exec_module(hg)

VIOLATION_DIRS = sorted(p for p in (FIXTURES / "violations").iterdir() if p.is_dir())


def check(fixture_dir):
    return hg.run_check(fixture_dir / "record.json", fixture_dir / "state.json")


def test_clean_fixture_passes():
    report = check(FIXTURES / "clean")
    assert report.violations() == []
    assert report.warnings() == []


def test_clean_fixture_reports_zero_unreconciled():
    report = check(FIXTURES / "clean")
    unrec = [f for f in report.infos() if "unreconciled" in f.message]
    assert len(unrec) == 1
    assert unrec[0].message.startswith("0 unreconciled")


@pytest.mark.parametrize("fixture_dir", VIOLATION_DIRS, ids=lambda p: p.name)
def test_violation_fixture_fails_with_right_invariant(fixture_dir):
    expected = fixture_dir.name.split("-")[0].upper()  # i2-missing-impact -> I2
    report = check(fixture_dir)
    violations = report.violations()
    assert violations, f"{fixture_dir.name}: expected at least one violation"
    assert {f.invariant for f in violations} == {expected}, (
        f"{fixture_dir.name}: expected only {expected} violations, "
        f"got {[(f.invariant, f.message) for f in violations]}"
    )


def test_all_seeded_invariants_covered():
    assert {p.name.split("-")[0].upper() for p in VIOLATION_DIRS} == {"I2", "I4", "I5", "I6", "I7"}


def test_check_cli_exit_codes(capsys):
    clean = FIXTURES / "clean"
    bad = FIXTURES / "violations" / "i6-bad-status"
    assert hg.main(["check", "--record", str(clean / "record.json"),
                    "--state", str(clean / "state.json")]) == 0
    assert hg.main(["check", "--record", str(bad / "record.json"),
                    "--state", str(bad / "state.json")]) == 1
    out = capsys.readouterr().out
    assert "VIOLATION I6" in out


def test_render_frontier_and_tree(tmp_path):
    out = hg.render_state(FIXTURES / "clean" / "state.json")
    assert "## Frontier" in out
    assert "[open]" in out and "Query API" in out          # frontier node
    assert "Ingest pipeline" in out and "[working]" in out  # architecture tree
    assert "Reconciled through `dim-walrus-0004`" in out
    # working nodes stay out of the frontier section
    frontier_section = out.split("## Frontier")[1].split("## Architecture")[0]
    assert "Ingest pipeline" not in frontier_section


EPOCH = FIXTURES / "epoch"
EPOCH_CONFIG = {"epoch": {"marker": "bright-gate-0003"}}


def test_epoch_legacy_node_exempt_from_i2():
    report = hg.run_check(EPOCH / "record.json", EPOCH / "state.json", EPOCH_CONFIG)
    assert report.violations() == []
    exempt = [f for f in report.infos() if "pre-epoch" in f.message]
    assert len(exempt) == 1 and exempt[0].message.startswith("1 pre-epoch")


def test_epoch_only_shields_legacy_nodes():
    """Without the epoch config, the same legacy node is an I2 violation."""
    report = hg.run_check(EPOCH / "record.json", EPOCH / "state.json")
    assert [f.node for f in report.violations()] == ["faded-scroll-0002"]
    assert all(f.invariant == "I2" for f in report.violations())


def test_epoch_post_epoch_node_still_fails_i2(tmp_path):
    """A node created after the marker gets no exemption."""
    import json
    graph = json.loads((EPOCH / "record.json").read_text())
    graph["nodes"].append({
        "node_id": "20000000-0000-0000-0000-000000000004",
        "slug_name": "loud-comet-0004",
        "title": "Post-epoch work without an impact",
        "content": "## What\n\nWork done after adoption, missing its impact declaration.\n",
        "parent_ids": ["20000000-0000-0000-0000-000000000003"],
        "created_at": "2026-08-03T00:00:00+00:00",
    })
    path = tmp_path / "record.json"
    path.write_text(json.dumps(graph))
    report = hg.run_check(path, EPOCH / "state.json", EPOCH_CONFIG)
    assert [f.node for f in report.violations()] == ["loud-comet-0004"]
    assert all(f.invariant == "I2" for f in report.violations())


def test_epoch_unresolvable_marker_is_violation():
    report = hg.run_check(EPOCH / "record.json", EPOCH / "state.json",
                          {"epoch": {"marker": "no-such-slug-0000"}})
    assert any(f.invariant == "I2" and "epoch.marker" in f.message
               for f in report.violations())


def test_staleness_reported_for_unreconciled_impacts():
    """Roll the HWM back one node; the impact of calm-heron-0003 becomes pending."""
    import json
    graph = json.loads((FIXTURES / "clean" / "state.json").read_text())
    for node in graph["nodes"]:
        node["content"] = node["content"].replace(
            "high_water_mark: dim-walrus-0004", "high_water_mark: brisk-otter-0002"
        )
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(graph, f)
        path = Path(f.name)
    try:
        report = hg.run_check(FIXTURES / "clean" / "record.json", path)
        assert report.violations() == []
        infos = " | ".join(f.message + ":" + f.node for f in report.infos())
        assert "2 unreconciled" in infos
        assert "mellow-quartz-0102" in infos  # calm-heron's target has a pending impact
    finally:
        os.unlink(path)


# ---- the config defects that cost two arm-C runs their memory system ----------
#
# On the nine-run benchmark, `check --config .hypergraph/config.yml` was run
# before the config existed. It died with a raw FileNotFoundError traceback out
# of `read_text`, naming pathlib rather than the missing file. Two of three arm-C
# agents read that as "the contents are wrong", wrote a one-line stub
# (`backend: local`), and got "0 violations" — because the checker had silently
# fallen back to guessing the roots. Both runs then carried a config that
# declared neither `record_root` nor `state_root`.

def test_missing_config_fails_with_an_instruction_not_a_traceback(tmp_path):
    clean = FIXTURES / "clean"
    with pytest.raises(SystemExit) as excinfo:
        hg.main(["check", "--record", str(clean / "record.json"),
                 "--state", str(clean / "state.json"),
                 "--config", str(tmp_path / "config.yml")])
    message = str(excinfo.value)
    assert "no config at" in message
    assert "record_root" in message and "state_root" in message
    # The old failure was a stack ending in pathlib. If that name is back, the
    # agent is being shown the plumbing again instead of the problem.
    assert "Traceback" not in message and "pathlib" not in message


def test_unparseable_config_names_the_file(tmp_path):
    bad = tmp_path / "config.yml"
    bad.write_text("record_root: [unclosed\n")
    clean = FIXTURES / "clean"
    with pytest.raises(SystemExit) as excinfo:
        hg.main(["check", "--record", str(clean / "record.json"),
                 "--state", str(clean / "state.json"), "--config", str(bad)])
    assert str(bad) in str(excinfo.value)


def test_a_config_declaring_no_roots_warns_rather_than_passing_silently(tmp_path):
    """The stub config must not read as a clean bill of health."""
    stub = tmp_path / "config.yml"
    stub.write_text("backend: local\n")
    clean = FIXTURES / "clean"
    report = hg.run_check(clean / "record.json", clean / "state.json",
                          hg.load_config(stub), config_given=True)
    # Still a pass — the inferred root may be right, and a correct graph should
    # not fail over how its root was located.
    assert report.violations() == []
    warnings = [f.message for f in report.warnings()]
    assert any("declares no `record_root:`" in w for w in warnings), warnings
    assert any("declares no `state_root:`" in w for w in warnings), warnings


def test_inference_without_a_config_stays_silent():
    """No --config is a deliberate choice, not an oversight — do not nag."""
    clean = FIXTURES / "clean"
    report = hg.run_check(clean / "record.json", clean / "state.json")
    assert report.warnings() == []


def test_cli_reports_a_version():
    """preflight pins the installed version against pyproject; both need this."""
    import re
    with pytest.raises(SystemExit) as excinfo:
        hg.main(["--version"])
    assert excinfo.value.code == 0
    pyproject = (ROOT / "pyproject.toml").read_text()
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert hg.__version__ == declared
