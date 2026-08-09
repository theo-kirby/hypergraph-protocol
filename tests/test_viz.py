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


def _record_graph(tmp_path, edges):
    """Build a record-graph export from {slug: [parent slugs]} in insertion order."""
    nodes = []
    for i, (slug, parents) in enumerate(edges.items(), start=1):
        nodes.append({
            "node_id": f"20000000-0000-0000-0000-{i:012d}", "slug_name": slug,
            "title": slug, "content": "## State Impact\n\nnone: fixture\n",
            "parent_ids": [f"20000000-0000-0000-0000-{list(edges).index(p) + 1:012d}"
                           for p in parents],
            "created_at": f"2026-08-01T00:{i:02d}:00+00:00",
        })
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"version": 1, "nodes": nodes}))
    return hg.load_graph(path)


def test_lane_layout_follows_the_earliest_parent(tmp_path):
    """A linear chain is one lane; a fork opens a second one."""
    graph = _record_graph(tmp_path, {
        "root-aaa-0001": [], "one-bbb-0002": ["root-aaa-0001"],
        "two-ccc-0003": ["one-bbb-0002"], "side-ddd-0004": ["one-bbb-0002"],
        "tip-eee-0005": ["two-ccc-0003"],
    })
    chrono, lanes = hg.lane_layout(graph)
    by_slug = {graph.nodes[nid].ref: lanes[nid] for nid in chrono}
    # the chain keeps lane 0; the fork's second child must go somewhere else
    assert by_slug["root-aaa-0001"] == by_slug["one-bbb-0002"] == 0
    assert by_slug["two-ccc-0003"] == 0 and by_slug["tip-eee-0005"] == 0
    assert by_slug["side-ddd-0004"] == 1


def test_lane_layout_reuses_a_lane_that_owes_nothing(tmp_path):
    """A finished branch releases its column instead of leaking width forever."""
    graph = _record_graph(tmp_path, {
        "root-aaa-0001": [],
        "fork-bbb-0002": ["root-aaa-0001"],
        "kid1-ccc-0003": ["fork-bbb-0002"],   # continues lane 0
        "kid2-ddd-0004": ["fork-bbb-0002"],   # fork still owed an edge -> lane 1
        "solo-eee-0005": [],                  # both branches now closed -> lane 0
    })
    chrono, lanes = hg.lane_layout(graph)
    by_slug = {graph.nodes[nid].ref: lanes[nid] for nid in chrono}
    assert by_slug["kid1-ccc-0003"] == 0 and by_slug["kid2-ddd-0004"] == 1
    assert by_slug["solo-eee-0005"] == 0, "a lane owing nothing must be reused"


def test_lane_layout_survives_a_child_older_than_its_parent(tmp_path):
    """Backdated imports and skewed clocks produce children that predate their
    parents. Lanes are assigned in time order, so such a parent has no lane yet —
    which used to raise. The edge just cannot continue a lane."""
    nodes = []
    for i, (slug, parents, when) in enumerate([
            ("root-aaa-0001", [], "2026-08-01T00:00:00+00:00"),
            ("late-bbb-0002", ["root-aaa-0001"], "2026-08-05T00:00:00+00:00"),
            # committed after its parent, but stamped before it
            ("early-ccc-0003", ["late-bbb-0002"], "2026-08-03T00:00:00+00:00")], start=1):
        nodes.append({"node_id": f"50000000-0000-0000-0000-{i:012d}",
                      "slug_name": slug, "title": slug, "content": "none: fixture",
                      "created_at": when,
                      "parent_ids": [f"50000000-0000-0000-0000-{j:012d}"
                                     for j in range(1, i) if nodes[j - 1]["slug_name"] in parents]})
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"version": 1, "nodes": nodes}))
    chrono, lanes = hg.lane_layout(hg.load_graph(path))
    assert len(lanes) == 3 and all(v >= 0 for v in lanes.values())


def test_lane_layout_keeps_a_shared_lane_adjacent():
    """The property the lanes exist for, checked on this repo's real graph.

    A node only ever shares a lane with a parent by *continuing* it, so its
    lane-neighbour to the left is that parent and the edge between them crosses
    nothing. (A merge's other parents live in other lanes and get a drawn bend —
    that is expected, and is what `git log --graph` does too.)
    """
    record = hg.load_graph(FIXTURES / "self" / "record.json")
    chrono, lanes = hg.lane_layout(record)
    order = {}
    for nid in chrono:
        order.setdefault(lanes[nid], []).append(nid)
    checked = 0
    for nid in chrono:
        kin = [p for p in record.nodes[nid].parent_ids
               if p in record.nodes and lanes[p] == lanes[nid]]
        if not kin:
            continue
        seq = order[lanes[nid]]
        before = seq[seq.index(nid) - 1] if seq.index(nid) else None
        assert before in kin, (
            f"{record.nodes[nid].ref} shares lane {lanes[nid]} with a parent but "
            f"follows {record.nodes[before].ref if before else 'nothing'}")
        checked += 1
    assert checked > 20, "fixture should exercise the rule broadly"


def test_payload_carries_timeline_and_board_facts():
    data = build(CLEAN)
    rec = {n["slug"]: n for n in data["record"]["nodes"]}
    # chrono is a dense rank over real creation order, independent of `seq`
    assert sorted(n["chrono"] for n in data["record"]["nodes"]) == [0, 1, 2, 3]
    assert rec["royal-anchor-0001"]["chrono"] == 0
    assert all(n["lane"] == 0 for n in data["record"]["nodes"]), "linear chain"
    st = {n["slug"]: n for n in data["state"]["nodes"]}
    quartz = st["mellow-quartz-0102"]
    assert quartz["prov_count"] == 3 and quartz["impact_count"] == 2
    assert quartz["last_record_at"] == rec["dim-walrus-0004"]["created_at"]
    assert st[data["state"]["root"]]["prov_count"] == 0


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


def test_template_carries_the_ported_distance_field():
    """The blob geometry is excaligraph's, ported. Keep the pieces and the credit."""
    tpl = hg.VIZ_TEMPLATE
    for fn in ("blobOutline", "traceContour", "spanningSegments", "routeCorridor",
               "smoothMin", "smoothMax", "douglasPeucker", "sdRectangle",
               "sdEllipse", "sdSegment", "blobPathFor"):
        assert fn in tpl, f"{fn} missing from the blob port"
    assert "excaligraph" in tpl and "MIT licence" in tpl, "attribution must survive"
    # the hull stays as the fast fallback, it is not replaced
    assert "BLOB_FIELD_MIN_ZOOM" in tpl


def _spec(links="none", fixture=CLEAN):
    return hg.excaligraph_spec(hg.load_graph(fixture / "record.json"),
                               hg.load_graph(fixture / "state.json"), None, links)


def test_excaligraph_spec_shape():
    """Nodes carry a link back to their source; blobs are the impact sets."""
    spec = _spec()
    assert spec["layout"] == {"engine": "dagre", "rankdir": "LR"}
    assert set(spec["nodes"]) == set(bySlug_of(CLEAN))
    assert spec["nodes"]["brisk-otter-0002"]["link"] == \
        ".hypergraph/graph/record/brisk-otter-0002.md"
    assert spec["nodes"]["mellow-quartz-0102"]["link"] == \
        ".hypergraph/graph/state/mellow-quartz-0102.md"
    # the state root is the one ellipse; everything else is a rectangle
    shapes = {s: n["shape"] for s, n in spec["nodes"].items()}
    assert shapes["amber-harbor-0101"] == "ellipse"
    assert shapes["brisk-otter-0002"] == "rectangle"
    # one hyperedge per state node with a declared impact set
    assert [h["nodes"] for h in spec["hyperedges"]] == \
        [["brisk-otter-0002", "calm-heron-0003"]]
    # the same seed for the same project, so a regenerated figure matches
    assert spec["seed"] == _spec()["seed"]


def test_excaligraph_links_default_to_parent_edges_only():
    """The impact relation *is* the blob membership; drawing it again as edges
    says nothing new and costs the figure its legibility."""
    parents = sum(len(n.parent_ids) for g in ("record", "state")
                  for n in hg.load_graph(CLEAN / f"{g}.json").nodes.values())
    assert len(_spec("none")["edges"]) == parents
    assert len(_spec("all")["edges"]) == parents + 6      # 4 provenance + 2 impact
    assert len(_spec("provenance")["edges"]) == parents + 4
    assert len(_spec("impact")["edges"]) == parents + 2


def test_excaligraph_truncates_paragraph_edge_labels():
    """An impact delta is a paragraph; on an edge in a figure it is noise."""
    labels = [e["label"] for e in _spec("all")["edges"] if "label" in e]
    assert labels, "labelled cross-links should survive"
    assert all(len(l) <= 60 for l in labels)
    assert all("\n" not in l for l in labels)


def test_palette_matches_the_page():
    """Figures and the interactive page must not quietly disagree on colour."""
    tpl = hg.VIZ_TEMPLATE
    for name, value in hg.PALETTE.items():
        for hexcode in (value if isinstance(value, list) else [value]):
            assert hexcode in tpl, f"PALETTE[{name}] = {hexcode} is not in the page"


def test_viz_format_excaligraph_cli(tmp_path):
    out = tmp_path / "graph.yaml"
    rc = hg.main(["viz", "--format", "excaligraph", "--record", str(CLEAN / "record.json"),
                  "--state", str(CLEAN / "state.json"), "-o", str(out)])
    assert rc == 0
    import yaml
    text = out.read_text()
    assert text.startswith("# Generated by")
    spec = yaml.safe_load(text)
    assert set(spec) == {"seed", "layout", "defaults", "nodes", "edges", "hyperedges"}


def bySlug_of(fixture):
    record = hg.load_graph(fixture / "record.json")
    state = hg.load_graph(fixture / "state.json")
    return [n.ref for n in record.nodes.values()] + [n.ref for n in state.nodes.values()]


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
