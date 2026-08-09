"""Viz tests: payload structure, cross-link extraction, layout determinism, HTML emission."""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools" / "fixtures"

_spec = importlib.util.spec_from_file_location("hypergraph_viz", ROOT / "tools" / "hypergraph.py")
hg = importlib.util.module_from_spec(_spec)
sys.modules["hypergraph_viz"] = hg
_spec.loader.exec_module(hg)

CLEAN = FIXTURES / "clean"


def build(fixture_dir):
    record = hg.load_graph(fixture_dir / "record.json")
    state = hg.load_graph(fixture_dir / "state.json")
    return hg.build_viz_data(record, state)


def test_payload_shape_and_counts():
    data = build(CLEAN)
    assert data["record"]["root"] == "royal-anchor-0001"
    assert data["state"]["root"] == "amber-harbor-0101"
    assert len(data["record"]["nodes"]) == 4
    assert len(data["state"]["nodes"]) == 3
    assert data["reconciliation"]["high_water_mark"] == "dim-walrus-0004"


def test_provenance_links_extracted():
    data = build(CLEAN)
    prov = {(l["state"], l["record"]) for l in data["links"] if l["kind"] == "provenance"}
    assert prov == {
        ("mellow-quartz-0102", "brisk-otter-0002"),
        ("mellow-quartz-0102", "calm-heron-0003"),
        ("mellow-quartz-0102", "dim-walrus-0004"),
        ("quiet-lantern-0103", "brisk-otter-0002"),
    }
    # provenance-section notes survive onto the link
    noted = next(l for l in data["links"]
                 if l["kind"] == "provenance" and l["record"] == "calm-heron-0003")
    assert "streaming parser" in noted["label"]


def test_impact_links_including_new_target_resolution():
    data = build(CLEAN)
    impacts = {(l["record"], l["state"]) for l in data["links"] if l["kind"] == "impact"}
    # brisk-otter declares `NEW ingest-pipeline`, resolved by kebab(title) match
    assert impacts == {
        ("brisk-otter-0002", "mellow-quartz-0102"),
        ("calm-heron-0003", "mellow-quartz-0102"),
    }


def test_state_root_produces_no_provenance_links():
    data = build(CLEAN)
    root = data["state"]["root"]
    assert not any(l["state"] == root for l in data["links"])


def test_flags_hwm_impact_none_and_status():
    data = build(CLEAN)
    rec = {n["slug"]: n for n in data["record"]["nodes"]}
    assert rec["dim-walrus-0004"]["is_hwm"]
    assert rec["dim-walrus-0004"]["impact_none"].startswith("pure refactor")
    assert rec["royal-anchor-0001"]["is_root"]
    assert not any(n["unreconciled"] for n in data["record"]["nodes"])
    st = {n["slug"]: n for n in data["state"]["nodes"]}
    assert st["mellow-quartz-0102"]["status"] == "working"
    assert st["quiet-lantern-0103"]["frontier"]
    assert not st["mellow-quartz-0102"]["frontier"]


def test_unreconciled_flagged_after_hwm_rollback(tmp_path):
    graph = json.loads((CLEAN / "state.json").read_text())
    for node in graph["nodes"]:
        node["content"] = node["content"].replace(
            "high_water_mark: dim-walrus-0004", "high_water_mark: brisk-otter-0002")
    rolled = tmp_path / "state.json"
    rolled.write_text(json.dumps(graph))
    record = hg.load_graph(CLEAN / "record.json")
    state = hg.load_graph(rolled)
    data = hg.build_viz_data(record, state)
    unrec = {n["slug"] for n in data["record"]["nodes"] if n["unreconciled"]}
    assert unrec == {"calm-heron-0003", "dim-walrus-0004"}


def test_layout_is_deterministic_and_layered():
    a, b = build(CLEAN), build(CLEAN)
    assert a == b
    rec = {n["slug"]: n for n in a["record"]["nodes"]}
    # linear causal chain root -> otter -> heron -> walrus
    assert [rec[s]["layer"] for s in ("royal-anchor-0001", "brisk-otter-0002",
                                      "calm-heron-0003", "dim-walrus-0004")] == [0, 1, 2, 3]
    seqs = sorted(n["seq"] for n in a["record"]["nodes"])
    assert seqs == [0, 1, 2, 3]


def test_render_viz_emits_selfcontained_html():
    html = hg.render_viz(CLEAN / "record.json", CLEAN / "state.json")
    assert html.startswith("<!doctype html>")
    assert "__VIZ_DATA__" not in html and "__TITLE__" not in html
    for slug in ("brisk-otter-0002", "mellow-quartz-0102"):
        assert slug in html
    # embedded payload is valid JSON (undo the </-escape used to keep it script-safe)
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert m, "embedded DATA payload not found"
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert data["project"]
    # self-contained: no external fetches
    assert "http://" not in html.replace("http://www.w3.org/", "")
    assert "https://" not in html


def test_template_preset_toggle_machinery():
    tpl = hg.VIZ_TEMPLATE
    # view chips present, in job order: Timeline, Frontier, Provenance, Clusters
    assert (tpl.index('data-preset="timeline"') < tpl.index('data-preset="frontier"')
            < tpl.index('data-preset="provenance"') < tpl.index('data-preset="clusters"'))
    for marker in ("const PRESETS", "applyPreset", "const show", "layoutKey",
                   'id="controls"', 'id="divider"', 'id="exportMenu"',
                   'id="svgBtn"', 'id="printBtn"'):
        assert marker in tpl
    assert 'id="tabs"' not in tpl  # the tab bar is gone


def test_template_keeps_pre_rename_deep_link_aliases():
    """Views were renamed after their job; old #hashes must keep resolving."""
    tpl = hg.VIZ_TEMPLATE
    assert "VIEW_ALIASES" in tpl
    for old, new in (("record", "timeline"), ("state", "frontier"),
                     ("combo", "provenance"), ("combination", "provenance"),
                     ("hyper", "clusters")):
        assert f"{old}:\"{new}\"" in tpl.replace(" ", "")


def test_template_force_view_machinery():
    tpl = hg.VIZ_TEMPLATE
    for fn in ("convexHull", "blobPath", "runSim", "hyperedges"):
        assert fn in tpl
    # determinism guard: layout must be reproducible across loads
    assert "Math.random" not in tpl


def test_viz_bundle_in_sync():
    """The page is authored under tools/viz/ and bundled into VIZ_TEMPLATE.

    Re-bundle in memory and compare: editing the sources without re-running
    tools/bundle_viz.py fails here instead of shipping a stale page.
    """
    assert hg.assemble_viz_template(ROOT / "tools" / "viz") == hg.VIZ_TEMPLATE, (
        "tools/viz/ and VIZ_TEMPLATE have drifted — run tools/bundle_viz.py")


def test_viz_dev_flag_matches_bundled_output(tmp_path):
    """`viz --dev` reads the sources; with them in sync it emits the same page."""
    out_a, out_b = tmp_path / "a.html", tmp_path / "b.html"
    args = ["viz", "--record", str(CLEAN / "record.json"), "--state", str(CLEAN / "state.json")]
    assert hg.main(args + ["-o", str(out_a)]) == 0
    assert hg.main(args + ["--dev", "-o", str(out_b)]) == 0
    assert out_a.read_text() == out_b.read_text()


def test_viz_cli_writes_file(tmp_path, capsys):
    out = tmp_path / "viz.html"
    rc = hg.main(["viz", "--record", str(CLEAN / "record.json"),
                  "--state", str(CLEAN / "state.json"), "-o", str(out)])
    assert rc == 0
    assert out.exists() and out.read_text().startswith("<!doctype html>")
