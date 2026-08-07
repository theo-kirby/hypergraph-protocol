"""Local (git-native) backend tests: round-trip fidelity, authoring gates, mirror plan.

The strongest guarantee here is the round-trip — importing a Flywheel export into node
files and exporting it back must reproduce the graph node-for-node, because that is
what makes the local backend a drop-in behind backend/INTERFACE.md.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools" / "fixtures"
CLEAN = FIXTURES / "clean"
LOCAL = FIXTURES / "local-graph"

_spec = importlib.util.spec_from_file_location("hypergraph_local", ROOT / "tools" / "hypergraph.py")
hg = importlib.util.module_from_spec(_spec)
sys.modules["hypergraph_local"] = hg
_spec.loader.exec_module(hg)


def run(*argv):
    """Invoke the CLI the way a skill does; returns the exit code."""
    return hg.main([str(a) for a in argv])


def run_out(capsys, *argv):
    """Run with a cleared capture buffer → (exit code, stdout). `new` prints the slug."""
    capsys.readouterr()
    code = run(*argv)
    return code, capsys.readouterr().out


def imported(tmp_path):
    graph_dir = tmp_path / "graph"
    assert run("import", "--record", CLEAN / "record.json", "--state", CLEAN / "state.json",
               "--graph-dir", graph_dir) == 0
    return graph_dir


# ------------------------------------------------------------------ round-trip

def test_import_export_round_trip_is_node_for_node_identical(tmp_path):
    graph_dir = imported(tmp_path)
    out_dir = tmp_path / "cache"
    assert run("export", "--graph-dir", graph_dir, "--out-dir", out_dir) == 0
    for kind in ("record", "state"):
        original = hg.load_graph(CLEAN / f"{kind}.json")
        round_tripped = hg.load_graph(out_dir / f"{kind}.json")
        assert round_tripped.nodes == original.nodes
        assert set(round_tripped.by_slug) == set(original.by_slug)


def test_round_tripped_clean_fixture_still_passes_the_checker(tmp_path):
    graph_dir = imported(tmp_path)
    out_dir = tmp_path / "cache"
    run("export", "--graph-dir", graph_dir, "--out-dir", out_dir)
    report = hg.run_check(out_dir / "record.json", out_dir / "state.json")
    assert report.violations() == []
    assert report.warnings() == []


def test_import_preserves_flywheel_identity_and_is_idempotent(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    meta, body = hg.split_frontmatter((graph_dir / "record" / "brisk-otter-0002.md").read_text())
    assert meta["node_id"] == "10000000-0000-0000-0000-000000000002"  # verbatim, no drift
    assert meta["parents"] == ["royal-anchor-0001"]                   # edges as slugs
    assert meta["flywheel"]["node_id"] == meta["node_id"]
    assert meta["flywheel"]["content_sha256"] == hg.body_sha256(body)
    capsys.readouterr()
    assert run("import", "--record", CLEAN / "record.json", "--state", CLEAN / "state.json",
               "--graph-dir", graph_dir) == 0
    assert "0 node file(s), 7 already up to date" in capsys.readouterr().out


def test_node_body_is_the_content_byte_for_byte(tmp_path):
    graph_dir = imported(tmp_path)
    source = {n.slug: n.content for n in hg.load_graph(CLEAN / "state.json").nodes.values()}
    for path in (graph_dir / "state").glob("*.md"):
        _meta, body = hg.split_frontmatter(path.read_text())
        assert body == source[path.stem]


# ------------------------------------------------------- the committed fixture

def test_local_graph_fixture_exports_to_its_golden_json():
    for kind in ("record", "state"):
        golden = json.loads((LOCAL / f"{kind}.json").read_text())
        payload = hg.export_graph_json(LOCAL / "graph", kind)
        assert payload["nodes"] == golden["nodes"]
        assert payload["version"] == golden["version"]


def test_local_graph_fixture_is_protocol_clean():
    report = hg.run_check(LOCAL / "record.json", LOCAL / "state.json")
    assert report.violations() == []
    assert report.warnings() == []


def test_export_is_ordered_by_created_at_then_node_id():
    payload = hg.export_graph_json(LOCAL / "graph", "record")
    keys = [(n["created_at"], n["node_id"]) for n in payload["nodes"]]
    assert keys == sorted(keys)


def test_node_ids_are_uuid5_of_the_slug():
    for node in hg.export_graph_json(LOCAL / "graph", "state")["nodes"]:
        assert node["node_id"] == hg.node_id_for(node["slug_name"])


# ----------------------------------------------------------------- authoring

def body_file(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_new_record_mints_a_valid_slug_without_collisions(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    body = body_file(tmp_path, "b.md", "## What\n\nDid a thing.\n")
    minted = set()
    for _ in range(5):
        code, out = run_out(capsys, "new", "record", "--graph-dir", graph_dir, "--title", "T",
                            "--body", body, "--parent", "dim-walrus-0004",
                            "--impact", "mellow-quartz-0102 — refreshed")
        assert code == 0
        slug = out.split()[0]
        assert hg.SLUG_RE.fullmatch(slug), slug
        assert slug not in minted
        minted.add(slug)
    assert len(list((graph_dir / "record").glob("*.md"))) == 4 + 5


def test_new_record_rejects_an_impact_target_that_is_not_a_state_node(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    body = body_file(tmp_path, "b.md", "## What\n\nDid a thing.\n")
    assert run("new", "record", "--graph-dir", graph_dir, "--title", "T", "--body", body,
               "--parent", "dim-walrus-0004", "--impact", "absent-node-9999 — nope") == 2
    assert "unknown state node" in capsys.readouterr().err
    assert len(list((graph_dir / "record").glob("*.md"))) == 4  # nothing written


def test_new_record_requires_a_state_impact_declaration(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    body = body_file(tmp_path, "b.md", "## What\n\nDid a thing.\n")
    assert run("new", "record", "--graph-dir", graph_dir, "--title", "T", "--body", body,
               "--parent", "dim-walrus-0004") == 2
    assert "State Impact" in capsys.readouterr().err


def test_new_record_generates_repo_and_impact_sections(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    body = body_file(tmp_path, "b.md", "## What\n\nDid a thing.\n")
    run("new", "record", "--graph-dir", graph_dir, "--title", "T", "--body", body,
        "--parent", "dim-walrus-0004", "--slug", "swift-comet-4242",
        "--none", "pure refactor, no claim changes")
    _meta, content = hg.split_frontmatter(
        (graph_dir / "record" / "swift-comet-4242.md").read_text())
    _pre, sections = hg.split_sections(content)
    assert sections["what"] == "Did a thing."
    entries, none_reason, bad = hg.parse_impacts(sections["state impact"])
    assert (entries, bad) == ([], [])
    assert none_reason == "pure refactor, no claim changes"
    capsys.readouterr()


def test_new_record_guards_generated_headings_but_allows_prose_mentions(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    common = ["new", "record", "--graph-dir", graph_dir, "--title", "T",
              "--parent", "dim-walrus-0004", "--none", "n/a"]
    duplicated = body_file(tmp_path, "dup.md", "## What\n\nx\n\n## State Impact\n\nnone: x\n")
    assert run(*common, "--body", duplicated) == 2
    assert "generates that section" in capsys.readouterr().err
    # an inline mention of the heading in prose is not a duplicate section
    mention = body_file(tmp_path, "ok.md",
                        "## What\n\nThe CLI generates `## State Impact` from flags.\n")
    assert run(*common, "--body", mention, "--slug", "swift-comet-4243") == 0
    capsys.readouterr()


def test_new_state_without_reconcile_is_refused(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    body = body_file(tmp_path, "s.md", "- A claim [rec: dim-walrus-0004].\n")
    args = ["new", "state", "--graph-dir", graph_dir, "--title", "New thing",
            "--status", "open", "--body", body, "--parent", "amber-harbor-0101",
            "--prov", "dim-walrus-0004 — why"]
    assert run(*args) == 2
    assert "I3" in capsys.readouterr().err
    assert len(list((graph_dir / "state").glob("*.md"))) == 3
    assert run(*args, "--reconcile") == 0
    assert len(list((graph_dir / "state").glob("*.md"))) == 4
    capsys.readouterr()


def test_new_state_rejects_a_prescaffolded_body(tmp_path, capsys):
    """A --body carrying the template would be double-wrapped (found live by
    push --verify: the first M0 reconcile nested Status/## Current twice)."""
    graph_dir = imported(tmp_path)
    for bad in ("Status: open\n\n- A claim [rec: dim-walrus-0004].\n",
                "## Current\n\n- A claim [rec: dim-walrus-0004].\n",
                "- A claim [rec: dim-walrus-0004].\n\n## Provenance\n\n- x\n"):
        body = body_file(tmp_path, "s.md", bad)
        assert run("new", "state", "--graph-dir", graph_dir, "--title", "New thing",
                   "--status", "open", "--body", body, "--parent", "amber-harbor-0101",
                   "--prov", "dim-walrus-0004 — why", "--reconcile") == 2
        assert "the CLI generates" in capsys.readouterr().err
    assert len(list((graph_dir / "state").glob("*.md"))) == 3


def test_new_state_rejects_provenance_that_does_not_resolve(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    body = body_file(tmp_path, "s.md", "- A claim [rec: dim-walrus-0004].\n")
    assert run("new", "state", "--graph-dir", graph_dir, "--title", "New thing",
               "--status", "open", "--body", body, "--parent", "amber-harbor-0101",
               "--prov", "absent-node-9999 — why", "--reconcile") == 2
    assert "does not resolve to a record node" in capsys.readouterr().err


def test_new_rejects_a_slug_that_breaks_slug_re(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    body = body_file(tmp_path, "b.md", "## What\n\nDid a thing.\n")
    assert run("new", "record", "--graph-dir", graph_dir, "--title", "T", "--body", body,
               "--parent", "dim-walrus-0004", "--slug", "NotASlug",
               "--none", "n/a") == 2
    assert "adjective-noun-####" in capsys.readouterr().err


def test_roots_can_be_minted_offline_and_only_once(tmp_path, capsys):
    graph_dir = tmp_path / "graph"
    overview = body_file(tmp_path, "o.md", "A fresh project.\n")
    assert run("new", "record", "--graph-dir", graph_dir, "--root",
               "--title", "demo — record", "--body", overview) == 0
    code, out = run_out(capsys, "new", "state", "--graph-dir", graph_dir, "--root",
                        "--reconcile", "--title", "demo — state", "--body", overview)
    assert code == 0
    state_root = out.split()[0]
    _meta, content = hg.split_frontmatter(
        (graph_dir / "state" / f"{state_root}.md").read_text())
    hwm, ts = hg.read_hwm(hg.Node("", state_root, "", content, [], ""))
    assert hwm == "none" and hg.parse_ts(ts) is not None
    assert run("new", "record", "--graph-dir", graph_dir, "--root",
               "--title", "second root", "--body", overview) == 2
    assert "already has a root" in capsys.readouterr().err


# -------------------------------------------------------------- op 7: the CAS

def test_update_refuses_a_stale_expect_and_leaves_the_file_untouched(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    target = graph_dir / "state" / "mellow-quartz-0102.md"
    before = target.read_text()
    replacement = body_file(tmp_path, "new.md",
                            "Status: broken\n\n## Current\n\n- Broken [rec: dim-walrus-0004].\n"
                            "\n## Provenance\n\n- dim-walrus-0004 — why\n")
    assert run("update", "mellow-quartz-0102", "--graph-dir", graph_dir,
               "--body", replacement, "--expect", "deadbeef", "--reconcile") == 2
    assert "stale write refused" in capsys.readouterr().err
    assert target.read_text() == before


def test_update_applies_with_the_current_sha_and_requires_reconcile(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    target = graph_dir / "state" / "mellow-quartz-0102.md"
    code, sha = run_out(capsys, "update", "mellow-quartz-0102", "--graph-dir", graph_dir,
                        "--print-sha")
    assert code == 0
    sha = sha.strip()
    replacement = body_file(tmp_path, "new.md",
                            "Status: broken\n\n## Current\n\n- Broken [rec: dim-walrus-0004].\n"
                            "\n## Provenance\n\n- dim-walrus-0004 — why\n")
    assert run("update", "mellow-quartz-0102", "--graph-dir", graph_dir,
               "--body", replacement, "--expect", sha) == 2
    assert "I3" in capsys.readouterr().err
    assert run("update", "mellow-quartz-0102", "--graph-dir", graph_dir,
               "--body", replacement, "--expect", sha, "--reconcile") == 0
    _meta, content = hg.split_frontmatter(target.read_text())
    assert hg.node_status(hg.Node("", "", "", content, [], "")) == "broken"
    capsys.readouterr()


def test_update_refuses_record_nodes_outright(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    replacement = body_file(tmp_path, "new.md", "## State Impact\n\nnone: nothing\n")
    code, sha = run_out(capsys, "update", "dim-walrus-0004", "--graph-dir", graph_dir,
                        "--print-sha")
    assert code == 0
    sha = sha.strip()
    assert run("update", "dim-walrus-0004", "--graph-dir", graph_dir,
               "--body", replacement, "--expect", sha, "--reconcile") == 2
    assert "append-only" in capsys.readouterr().err


# ------------------------------------------------------------- mirror planning

def test_push_plan_on_a_never_pushed_graph_creates_parents_first():
    plan = hg.push_plan(LOCAL / "graph")
    assert plan["violations"] == []
    assert {o["op"] for o in plan["ops"]} == {"create"}
    seen = set()
    for op in plan["ops"]:
        for parent in op["parent_slugs"]:
            assert parent in seen, f"{op['slug']} planned before its parent {parent}"
        seen.add(op["slug"])
    assert [o["slug"] for o in plan["ops"] if o["graph"] == "record"][0] == "wise-anchor-1001"


def test_push_plan_is_empty_after_results_are_recorded_and_reopens_on_edit(tmp_path, capsys):
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    for kind in ("record", "state"):
        target = graph_dir / kind
        target.mkdir()
        for src in (LOCAL / "graph" / kind).glob("*.md"):
            (target / src.name).write_text(src.read_text())

    plan = hg.push_plan(graph_dir)
    results = {"results": [{"slug": op["slug"],
                            "flywheel": {"node_id": f"fw-{op['slug']}",
                                         "slug_name": f"wild-river-{op['slug'][-4:]}",
                                         "revision": 1},
                            "content_sha256": op["content_sha256"]} for op in plan["ops"]]}
    (tmp_path / "results.json").write_text(json.dumps(results))
    assert run("push", "--graph-dir", graph_dir,
               "--record-result", tmp_path / "results.json") == 0
    assert hg.push_plan(graph_dir)["ops"] == []

    target = graph_dir / "state" / "quiet-summit-2002.md"
    meta, content = hg.split_frontmatter(target.read_text())
    target.write_text(hg.render_node_file(meta, content.replace("84s", "79s")))
    reopened = hg.push_plan(graph_dir)
    assert [(o["op"], o["slug"]) for o in reopened["ops"]] == [("update", "quiet-summit-2002")]
    assert reopened["ops"][0]["base_revision"] == 1
    assert reopened["ops"][0]["flywheel_node_id"] == "fw-quiet-summit-2002"
    assert reopened["violations"] == []
    capsys.readouterr()


def test_push_flags_a_record_body_that_changed_after_being_pushed(tmp_path, capsys):
    graph_dir = tmp_path / "graph"
    (graph_dir / "record").mkdir(parents=True)
    src = LOCAL / "graph" / "record" / "wise-anchor-1001.md"
    meta, content = hg.split_frontmatter(src.read_text())
    meta["flywheel"] = {"node_id": "fw-1", "slug": "wild-river-0001", "revision": 1,
                        "pushed_at": "2026-08-02T04:00:00+00:00",
                        "content_sha256": hg.body_sha256(content)}
    (graph_dir / "record" / src.name).write_text(
        hg.render_node_file(meta, content + "\nsneaky edit\n"))
    assert run("push", "--plan", "--graph-dir", graph_dir, "-o", tmp_path / "plan.json") == 1
    assert "append-only" in capsys.readouterr().err


# ------------------------------------------------------------ mirror verification

def pushed_graph(tmp_path):
    """LOCAL graph copied, planned, and stamped as if the mirror push ran."""
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    for kind in ("record", "state"):
        target = graph_dir / kind
        target.mkdir()
        for src in (LOCAL / "graph" / kind).glob("*.md"):
            (target / src.name).write_text(src.read_text())
    plan = hg.push_plan(graph_dir)
    results = {"results": [{"slug": op["slug"],
                            "flywheel": {"node_id": f"fw-{op['slug']}",
                                         "slug_name": f"wild-river-{op['slug'][-4:]}",
                                         "revision": 1},
                            "content_sha256": op["content_sha256"]} for op in plan["ops"]]}
    hg.apply_push_results(graph_dir, results)
    return graph_dir


def mirror_export_of(graph_dir):
    """The export a faithful mirror would produce for pushed_graph."""
    nodes = []
    for kind in ("record", "state"):
        for node in hg.load_local_nodes(graph_dir, kind).values():
            fw = node.meta["flywheel"]
            nodes.append({"node_id": fw["node_id"], "slug_name": fw["slug"],
                          "title": node.title, "content": node.content,
                          "summary": str(node.meta.get("summary") or ""),
                          "revision": fw["revision"]})
    return {"version": 1, "nodes": nodes}


def test_verify_clean_mirror_has_no_drift(tmp_path):
    graph_dir = pushed_graph(tmp_path)
    export = tmp_path / "export.json"
    export.write_text(json.dumps(mirror_export_of(graph_dir)))
    assert run("push", "--verify", "--against", export, "--graph-dir", graph_dir) == 0
    assert hg.verify_mirror(graph_dir, export).violations() == []


def test_verify_detects_each_drift_kind(tmp_path):
    graph_dir = pushed_graph(tmp_path)
    export = mirror_export_of(graph_dir)
    by_id = {n["node_id"]: n for n in export["nodes"]}
    by_id["fw-wise-anchor-1001"]["content"] += "\ntampered\n"      # body hash
    by_id["fw-quiet-summit-2002"]["summary"] = "different"          # summary
    by_id["fw-brave-otter-1002"]["revision"] = 7                    # revision skew
    export["nodes"] = [n for n in export["nodes"]                    # missing from mirror
                       if n["node_id"] != "fw-calm-fern-1003"]
    export["nodes"].append({"node_id": "fw-extra", "slug_name": "extra-node-9999",
                            "title": "Orphan", "content": "x", "summary": ""})
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    messages = {f.node: f.message for f in hg.verify_mirror(graph_dir, path).violations()}
    assert "body hash mismatch" in messages["wise-anchor-1001"]
    assert "summary mismatch" in messages["quiet-summit-2002"]
    assert "revision skew" in messages["brave-otter-1002"]
    assert any("missing from the mirror export" in m for m in messages.values())
    assert "no local counterpart" in messages["extra-node-9999"]
    assert run("push", "--verify", "--against", path, "--graph-dir", graph_dir) == 1


def test_verify_exempts_the_slug_legend_and_flags_unpushed(tmp_path):
    graph_dir = pushed_graph(tmp_path)
    export = mirror_export_of(graph_dir)
    export["nodes"].append({"node_id": "fw-legend", "slug_name": "shiny-map-0001",
                            "title": hg.LEGEND_TITLE, "content": "| legend |", "summary": ""})
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    assert hg.verify_mirror(graph_dir, path).violations() == []
    # a never-pushed graph is all drift: every local node unpushed, every mirror
    # node unmatched — except the legend, still exempt
    report = hg.verify_mirror(LOCAL / "graph", path)
    messages = [f.message for f in report.violations()]
    assert sum("never pushed" in m for m in messages) == 5
    assert sum("no local counterpart" in m for m in messages) == 5
    assert len(messages) == 10  # the legend node adds nothing


def test_legend_lists_diverged_slug_pairs(tmp_path, capsys):
    graph_dir = pushed_graph(tmp_path)
    text = hg.legend_content(graph_dir)
    assert "| record | wise-anchor-1001 | wild-river-1001 |" in text
    assert "| state | quiet-summit-2002 | wild-river-2002 |" in text
    code, out = run_out(capsys, "push", "--legend", "--graph-dir", graph_dir)
    assert code == 0 and "wild-river-1001" in out


def test_import_skips_the_mirror_legend_node(tmp_path, capsys):
    graph = json.loads((CLEAN / "record.json").read_text())
    graph["nodes"].append({"node_id": "40000000-0000-0000-0000-000000000009",
                           "slug_name": "shiny-map-0009", "title": hg.LEGEND_TITLE,
                           "content": "| legend |", "parent_ids": [],
                           "created_at": "2026-08-05T00:00:00+00:00"})
    path = tmp_path / "record.json"
    path.write_text(json.dumps(graph))
    graph_dir = tmp_path / "graph"
    code, out = run_out(capsys, "import", "--record", path, "--graph-dir", graph_dir)
    assert code == 0
    assert "mirror-only" in out
    assert not (graph_dir / "record" / "shiny-map-0009.md").exists()


# -------------------------------------------------------------- skills install

def test_skills_install_copies_self_contained_skills(tmp_path, capsys):
    code, out = run_out(capsys, "skills", "install", "--target", tmp_path / "sk")
    assert code == 0
    names = {p.name for p in (tmp_path / "sk").iterdir()}
    assert {"hypergraph-init", "hypergraph-adopt", "hypergraph-record",
            "hypergraph-reconcile", "hypergraph-orient"} <= names
    spec = tmp_path / "sk" / "hypergraph-adopt" / "references" / "spec.md"
    assert spec.is_file() and not spec.is_symlink()  # materialized, self-contained
    assert "Invariants" in spec.read_text()
    # idempotent: second run overwrites in place
    assert run("skills", "install", "--target", tmp_path / "sk") == 0
    capsys.readouterr()


# ------------------------------------------------------------------ diagnostics

@pytest.mark.parametrize("mutate,expected", [
    (lambda p: p.write_text(p.read_text().replace("slug: wise-anchor-1001",
                                                  "slug: not_a_slug")), "adjective-noun-####"),
    (lambda p: p.rename(p.with_name("renamed-node-1001.md")), "does not match frontmatter slug"),
    (lambda p: p.write_text(p.read_text().replace("created_at: '2026-08-02T00:00:00+00:00'",
                                                  "created_at: yesterday")), "ISO-8601"),
    (lambda p: p.write_text(p.read_text().split("---", 2)[2]), "frontmatter"),
])
def test_broken_node_files_fail_loudly(tmp_path, mutate, expected):
    graph_dir = tmp_path / "graph"
    (graph_dir / "record").mkdir(parents=True)
    path = graph_dir / "record" / "wise-anchor-1001.md"
    path.write_text((LOCAL / "graph" / "record" / "wise-anchor-1001.md").read_text())
    mutate(path)
    with pytest.raises(hg.LocalGraphError) as excinfo:
        hg.load_local_nodes(graph_dir, "record")
    assert expected in str(excinfo.value)


def test_unknown_parent_slug_is_rejected(tmp_path):
    graph_dir = tmp_path / "graph"
    (graph_dir / "record").mkdir(parents=True)
    src = LOCAL / "graph" / "record" / "brave-otter-1002.md"
    (graph_dir / "record" / src.name).write_text(src.read_text())  # parent left behind
    with pytest.raises(hg.LocalGraphError, match="is not a record node"):
        hg.load_local_graph(graph_dir, "record")
