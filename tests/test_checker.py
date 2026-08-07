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
