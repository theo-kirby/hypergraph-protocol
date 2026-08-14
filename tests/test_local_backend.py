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

from graph_fixtures import create_result, mirror_export_of, pushed_graph

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
    # regression guard: without --fork this is a re-home of a graph you own, so the
    # source identity stays the push target and no `origin:` block appears
    assert "origin" not in meta
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
    assert hwm == [] and hg.parse_ts(ts) is not None  # `none` parses as an empty frontier
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


# ------------------------------------------------------- op 7: re-parenting
# `--parent` on a state node is how the distilled graph gains depth. It is refused
# on record nodes by the same guard that refuses a body edit there — a parent edge in
# the record graph says "this happened after that", and history does not move.

def sha_of(capsys, graph_dir, slug):
    code, sha = run_out(capsys, "update", slug, "--graph-dir", graph_dir, "--print-sha")
    assert code == 0
    return sha.strip()


def test_update_reparents_a_state_node_without_touching_its_body(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    target = graph_dir / "state" / "quiet-lantern-0103.md"
    before = hg.split_frontmatter(target.read_text())[1]
    assert run("update", "quiet-lantern-0103", "--graph-dir", graph_dir, "--reconcile",
               "--expect", sha_of(capsys, graph_dir, "quiet-lantern-0103"),
               "--parent", "mellow-quartz-0102") == 0
    meta, content = hg.split_frontmatter(target.read_text())
    assert meta["parents"] == ["mellow-quartz-0102"]
    assert content == before          # no --body: the body is kept verbatim
    capsys.readouterr()


def test_update_refuses_a_reparent_that_would_close_a_cycle(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    before = (graph_dir / "state" / "amber-harbor-0101.md").read_text()
    assert run("update", "amber-harbor-0101", "--graph-dir", graph_dir, "--reconcile",
               "--expect", sha_of(capsys, graph_dir, "amber-harbor-0101"),
               "--parent", "mellow-quartz-0102") == 2
    assert "cycle" in capsys.readouterr().err
    assert (graph_dir / "state" / "amber-harbor-0101.md").read_text() == before


def test_update_refuses_a_second_root_and_an_unknown_or_self_parent(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    sha = sha_of(capsys, graph_dir, "mellow-quartz-0102")
    for flags, message in ((["--root"], "already has a root"),
                           (["--parent", "no-such-node-9999"], "is not a state node"),
                           (["--parent", "mellow-quartz-0102"], "its own parent")):
        assert run("update", "mellow-quartz-0102", "--graph-dir", graph_dir,
                   "--reconcile", "--expect", sha, *flags) == 2
        assert message in capsys.readouterr().err


def test_update_refuses_to_reparent_without_reconcile(tmp_path, capsys):
    graph_dir = imported(tmp_path)
    assert run("update", "quiet-lantern-0103", "--graph-dir", graph_dir,
               "--expect", sha_of(capsys, graph_dir, "quiet-lantern-0103"),
               "--parent", "mellow-quartz-0102") == 2
    assert "I3" in capsys.readouterr().err


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
    results = {"results": [create_result(op) for op in plan["ops"]]}
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


def _verify_mirror_before_the_refactor(graph_dir, against, exempt_ids=None):
    """The hand-rolled loop `verify_mirror` had before `diff_graphs` existed.

    Kept verbatim as the oracle for the refactor. A refactor of a diagnostic is only
    honest if its findings do not move, and the only way to say that mechanically is
    to keep the thing it replaced and compare."""
    report = hg.Report()
    exempt_ids = exempt_ids or set()
    remote = hg._load_export_nodes(against)
    matched = set()
    for kind in hg.GRAPH_KINDS:
        for node in hg.load_local_nodes(graph_dir, kind, missing_ok=True).values():
            fw = node.meta.get("flywheel") or {}
            fid = str(fw.get("node_id") or "")
            if not fid:
                report.add("violation", "mirror", node.slug,
                           f"local {kind} node never pushed to the mirror")
                continue
            raw = remote.get(fid)
            if raw is None:
                report.add("violation", "mirror", node.slug,
                           f"local {kind} node missing from the mirror export (flywheel id {fid})")
                continue
            matched.add(fid)
            if fw.get("content_sha256") and fw["content_sha256"] != node.sha256:
                report.add("violation", "mirror", node.slug,
                           "local body changed since last push (pending update)")
            if hg.body_sha256(str(raw.get("content") or "")) != node.sha256:
                report.add("violation", "mirror", node.slug,
                           "body hash mismatch between local file and mirror")
            if "summary" in raw and str(raw.get("summary") or "") != str(node.meta.get("summary") or ""):
                report.add("violation", "mirror", node.slug,
                           "summary mismatch between local file and mirror")
            revision = raw.get("committed_revision", raw.get("revision"))
            if revision is not None and fw.get("revision") is not None \
                    and int(revision) != int(fw["revision"]):
                report.add("violation", "mirror", node.slug,
                           f"revision skew: mirror at {revision}, frontmatter says {fw['revision']}")
    for nid, raw in sorted(remote.items()):
        if nid in matched or nid in exempt_ids \
                or str(raw.get("title") or "") == hg.LEGEND_TITLE:
            continue
        report.add("violation", "mirror", str(raw.get("slug_name") or raw.get("slug") or nid),
                   "mirror node has no local counterpart")
    return report


def _every_drift_kind(tmp_path):
    """A graph and an export carrying every drift the old loop could report, with the
    kinds *interleaved* across nodes rather than grouped — that is what catches an
    ordering regression."""
    graph_dir = pushed_graph(tmp_path)
    export = mirror_export_of(graph_dir)
    by_id = {n["node_id"]: n for n in export["nodes"]}
    by_id["fw-wise-anchor-1001"]["content"] += "\ntampered\n"       # body
    by_id["fw-quiet-summit-2002"]["summary"] = "different"           # summary
    by_id["fw-brave-otter-1002"]["revision"] = 7                     # revision skew
    by_id["fw-brave-otter-1002"]["content"] += "\nalso tampered\n"   # two on one node
    del by_id["fw-bright-harbor-2001"]["summary"]        # absent ≠ empty: not a finding
    export["nodes"] = [n for n in export["nodes"]
                       if n["node_id"] != "fw-calm-fern-1003"]       # missing right
    export["nodes"].append({"node_id": "fw-extra", "slug_name": "extra-node-9999",
                            "title": "Orphan", "content": "x", "summary": ""})
    export["nodes"].append({"node_id": "fw-legend", "slug_name": "shiny-map-0001",
                            "title": hg.LEGEND_TITLE, "content": "|", "summary": ""})
    # a node edited since its push: pending-push drift, ahead of the body finding
    src = next((graph_dir / "state").glob("*.md"))
    meta, content = hg.split_frontmatter(src.read_text())
    src.write_text(hg.render_node_file(meta, content + "\nlocal edit\n"))
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    return graph_dir, path


def test_verify_mirror_findings_are_byte_identical_after_the_refactor(tmp_path):
    graph_dir, export = _every_drift_kind(tmp_path)
    for exempt in (None, {"fw-extra"}):
        old = _verify_mirror_before_the_refactor(graph_dir, export, exempt)
        new = hg.verify_mirror(graph_dir, export, exempt)
        # str(Finding) is what the CLI prints — comparing it compares the output
        assert [str(f) for f in new.findings] == [str(f) for f in old.findings]
        assert [f.level for f in new.findings] == [f.level for f in old.findings]
    assert len(hg.verify_mirror(graph_dir, export).violations()) >= 6


def test_verify_exempts_declared_mirror_roots(tmp_path):
    graph_dir = pushed_graph(tmp_path)
    export = mirror_export_of(graph_dir)
    export["nodes"].append({"node_id": "fw-mirror-root", "slug_name": "fresh-root-0001",
                            "title": "demo — record (hypergraph mirror)",
                            "content": "mirror-only root", "summary": ""})
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    assert [f.node for f in hg.verify_mirror(graph_dir, path).violations()] == ["fresh-root-0001"]
    assert hg.verify_mirror(graph_dir, path, {"fw-mirror-root"}).violations() == []


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


# ----------------------------------------------------------------- fork import

def forked(tmp_path, name="graph"):
    """The clean fixture imported as an adoption fork: `origin:`, no `flywheel:`."""
    graph_dir = tmp_path / name
    assert run("import", "--record", CLEAN / "record.json", "--state", CLEAN / "state.json",
               "--graph-dir", graph_dir, "--fork") == 0
    return graph_dir


ARCHIVE_CONFIG = """
project: demo
graph_dir: graph
archive:
  backend: flywheel
  roots:
    - slug: royal-anchor-0001
      node_id: 10000000-0000-0000-0000-000000000001
      title: 'demo: the graph we forked from'
  artifacts: retained-on-archive
"""


def archive_config(tmp_path, text=ARCHIVE_CONFIG):
    path = tmp_path / "config.yml"
    path.write_text(text)
    return path


def test_import_fork_writes_origin_and_omits_flywheel(tmp_path):
    graph_dir = forked(tmp_path)
    meta, _body = hg.split_frontmatter((graph_dir / "record" / "brisk-otter-0002.md").read_text())
    assert meta["node_id"] == "10000000-0000-0000-0000-000000000002"  # verbatim, no drift
    assert meta["parents"] == ["royal-anchor-0001"]
    assert meta["origin"]["backend"] == "flywheel"
    assert meta["origin"]["node_id"] == meta["node_id"]
    assert meta["origin"]["slug"] == "brisk-otter-0002"
    assert meta["origin"]["exported_at"]
    assert "flywheel" not in meta          # the fork owns its own mirror identity
    assert "content_sha256" not in meta["origin"]  # provenance, not a change detector
    # frontmatter order: origin sits immediately before where flywheel would go
    keys = list(meta)
    assert keys == ["node_id", "slug", "title", "created_at", "parents", "summary", "origin"]


def test_import_fork_preserves_the_archive_revision(tmp_path):
    graph = json.loads((CLEAN / "record.json").read_text())
    for node in graph["nodes"]:
        node["committed_revision"] = 3
    path = tmp_path / "record.json"
    path.write_text(json.dumps(graph))
    graph_dir = tmp_path / "graph"
    assert run("import", "--record", path, "--graph-dir", graph_dir, "--fork") == 0
    meta, _ = hg.split_frontmatter((graph_dir / "record" / "royal-anchor-0001.md").read_text())
    assert meta["origin"]["revision"] == 3


def test_reimport_with_fork_force_replaces_flywheel_with_origin(tmp_path):
    graph_dir = imported(tmp_path)                     # old format: flywheel: present
    before, _ = hg.split_frontmatter((graph_dir / "record" / "calm-heron-0003.md").read_text())
    assert "flywheel" in before and "origin" not in before
    assert run("import", "--record", CLEAN / "record.json", "--state", CLEAN / "state.json",
               "--graph-dir", graph_dir, "--fork", "--force") == 0
    after, _ = hg.split_frontmatter((graph_dir / "record" / "calm-heron-0003.md").read_text())
    assert "flywheel" not in after
    assert after["origin"]["node_id"] == before["flywheel"]["node_id"]


def test_push_plan_over_a_forked_import_creates_every_node_parents_first(tmp_path):
    graph_dir = forked(tmp_path)
    plan = hg.push_plan(graph_dir)
    assert plan["violations"] == []
    assert {o["op"] for o in plan["ops"]} == {"create"}
    assert len(plan["ops"]) == 7                       # 4 record + 3 state, none skipped
    seen = set()
    for op in plan["ops"]:
        for parent in op["parent_slugs"]:
            assert parent in seen, f"{op['slug']} planned before its parent {parent}"
        seen.add(op["slug"])


def test_check_is_unchanged_by_the_presence_of_origin(tmp_path):
    plain = tmp_path / "plain-cache"
    fork = tmp_path / "fork-cache"
    run("export", "--graph-dir", imported(tmp_path), "--out-dir", plain)
    run("export", "--graph-dir", forked(tmp_path, "fork-graph"), "--out-dir", fork)
    assert json.loads((plain / "record.json").read_text())["nodes"] == \
           json.loads((fork / "record.json").read_text())["nodes"]
    report = hg.run_check(fork / "record.json", fork / "state.json")
    assert report.violations() == [] and report.warnings() == []


def pushed_fork(tmp_path):
    """A forked import with the whole plan executed against a mirror we own."""
    graph_dir = forked(tmp_path)
    plan = hg.push_plan(graph_dir)
    hg.apply_push_results(graph_dir, {"results": [
        create_result(op, prefix="ours-", slug_prefix="lively-feather-")
        for op in plan["ops"]]})
    return graph_dir


def test_verify_is_clean_against_a_mirror_roots_only_export_after_a_full_push(tmp_path):
    graph_dir = pushed_fork(tmp_path)
    export = mirror_export_of(graph_dir)               # only nodes on our own mirror
    ids = {n["node_id"] for n in export["nodes"]}
    assert len(ids) == 7
    assert not any(i.startswith("10000000") or i.startswith("20000000") for i in ids), \
        "no archive anchor is spliced into the export"
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    assert hg.verify_mirror(graph_dir, path).violations() == []
    assert run("push", "--verify", "--against", path, "--graph-dir", graph_dir) == 0
    assert hg.push_plan(graph_dir)["ops"] == []        # nothing left to mirror


def test_legend_maps_every_forked_node_from_its_archive_slug(tmp_path):
    text = hg.legend_content(pushed_fork(tmp_path))
    assert "archive→mirror map" in text
    assert "| record | brisk-otter-0002 | lively-feather-0002 |" in text
    assert "| state | quiet-lantern-0103 | lively-feather-0103 |" in text


def test_push_lineage_renders_from_the_config_archive_block(tmp_path, capsys):
    graph_dir = forked(tmp_path)
    code, out = run_out(capsys, "push", "--lineage", "--graph-dir", graph_dir,
                        "--config", archive_config(tmp_path))
    assert code == 0
    assert "frozen" in out and "never writes to it" in out
    assert "| royal-anchor-0001 | 10000000-0000-0000-0000-000000000001 |" in out
    assert "demo: the graph we forked from" in out
    assert "7 node(s) were imported verbatim" in out   # counted from `origin:` blocks
    assert "Artifacts did not survive the import" in out


def test_push_lineage_errors_without_an_archive_block(tmp_path, capsys):
    graph_dir = forked(tmp_path)
    config = archive_config(tmp_path, "project: demo\ngraph_dir: graph\n")
    capsys.readouterr()
    assert run("push", "--lineage", "--graph-dir", graph_dir, "--config", config) == 2
    assert "`archive:` block" in capsys.readouterr().err


def test_push_plan_warns_above_the_create_threshold(tmp_path, capsys, monkeypatch):
    graph_dir = forked(tmp_path)
    monkeypatch.setattr(hg, "PUSH_CREATE_WARN", 3)     # 7 creates in the fixture
    assert run("push", "--plan", "--graph-dir", graph_dir, "-o", tmp_path / "plan.json") == 0
    err = capsys.readouterr().err
    assert "push plan: 7 create(s)" in err
    assert "WARNING 7 creates" in err and "epoch" in err
    monkeypatch.setattr(hg, "PUSH_CREATE_WARN", 200)
    assert run("push", "--plan", "--graph-dir", graph_dir, "-o", tmp_path / "plan.json") == 0
    assert "WARNING" not in capsys.readouterr().err


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


def test_skills_install_refuses_to_clobber_a_link_to_the_source(tmp_path, capsys):
    """The dogfooding case: .claude/skills/* are symlinks back into skills/.

    Copying over them would replace the live skill with a stale snapshot of itself,
    silently. Exit 2 instead."""
    target = tmp_path / "sk"
    target.mkdir()
    source = hg.skills_data_root() / "skills" / "hypergraph-record"
    (target / "hypergraph-record").symlink_to(source, target_is_directory=True)
    assert run("skills", "install", "--target", target) == 2
    err = capsys.readouterr().err
    assert "already linked to the source" in err
    # untouched: still a link, not a copy
    assert (target / "hypergraph-record").is_symlink()


def test_skills_install_link_edits_through(tmp_path, capsys):
    """--link installs symlinks, so editing the source edits the installed skill."""
    target = tmp_path / "sk"
    assert run("skills", "install", "--link", "--target", target) == 0
    dst = target / "hypergraph-record"
    assert dst.is_symlink()
    assert dst.resolve() == (hg.skills_data_root() / "skills" / "hypergraph-record").resolve()
    # and a link into the source is then refused rather than replaced
    assert run("skills", "install", "--target", target) == 2
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


# ------------------------------------------------------------------- artifacts
# Evidence links, local half. The load-bearing property is the first test here:
# `artifacts:` is frontmatter a tool owns, so editing it on a *committed record
# node* leaves the append-only body untouched. Everything else in this feature —
# `push` stamping ids, `check` warning about a moved file — rests on that being
# true rather than merely believed.

def artifact_project(tmp_path, files=("runs/train.log",)):
    """A git checkout holding the local-graph fixture plus some evidence files."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    graph_dir = repo / "graph"
    for kind in ("record", "state"):
        (graph_dir / kind).mkdir(parents=True)
        for src in (LOCAL / "graph" / kind).glob("*.md"):
            (graph_dir / kind / src.name).write_text(src.read_text())
    for name in files:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"evidence for {name}\n")
    return repo, graph_dir


def in_artifact_repo(monkeypatch, tmp_path, files=("runs/train.log",)):
    """The project, plus a chdir into it.

    Artifact paths are typed **cwd-relative**, exactly as `git add` takes them, so a
    test that types one has to stand where an agent would."""
    repo, graph_dir = artifact_project(tmp_path, files)
    monkeypatch.chdir(repo)
    return repo, graph_dir


def artifact_config(tmp_path, graph_dir, extra=""):
    path = tmp_path / "artifact-config.yml"
    path.write_text(f"project: demo\ngraph_dir: {graph_dir}\n"
                    f"cache_dir: {tmp_path / 'cache'}\n{extra}")
    return path


def test_artifacts_add_leaves_the_body_sha256_untouched(tmp_path, capsys, monkeypatch):
    """**Decision 4, and the load-bearing test for the whole feature.**

    The record graph is append-only in its *bodies*. `LocalNode.sha256` hashes the
    body alone, so a frontmatter-only edit cannot reach it — which is what makes
    `artifacts add` legal on a node that was committed and published years ago."""
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    before = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    body_before = before.sha256
    file_before = before.path.read_text()

    assert run("artifacts", "add", "brave-otter-1002", "runs/train.log",
               "--graph-dir", graph_dir, "--repo", repo) == 0
    after = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    assert after.sha256 == body_before
    assert after.artifacts == ["runs/train.log"]
    assert after.path.read_text() != file_before      # only the frontmatter moved
    _meta, body = hg.split_frontmatter(after.path.read_text())
    assert body == hg.split_frontmatter(file_before)[1]
    capsys.readouterr()


def test_artifacts_add_leaves_the_push_plan_empty(tmp_path, capsys, monkeypatch):
    """A frontmatter-only edit must not read as a body change to publish."""
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    pushed = pushed_graph(tmp_path)          # a separate, already-stamped copy
    for kind in ("record", "state"):
        for src in (pushed / kind).glob("*.md"):
            (graph_dir / kind / src.name).write_text(src.read_text())
    assert hg.push_plan(graph_dir, do_artifacts=False)["ops"] == []
    assert run("artifacts", "add", "brave-otter-1002", "runs/train.log",
               "--graph-dir", graph_dir, "--repo", repo) == 0
    plan = hg.push_plan(graph_dir, do_artifacts=False)
    assert plan["ops"] == [] and plan["violations"] == []
    # with artifacts on, the only op is the upload — no body update, no violation
    creates, updates, tags, artifacts = hg.plan_op_counts(
        hg.push_plan(graph_dir, repo=repo))
    assert (creates, updates, tags, artifacts) == (0, 0, 0, 1)
    capsys.readouterr()


def test_artifacts_add_leaves_verify_mirror_clean(tmp_path, capsys, monkeypatch):
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    pushed = pushed_graph(tmp_path)
    for kind in ("record", "state"):
        for src in (pushed / kind).glob("*.md"):
            (graph_dir / kind / src.name).write_text(src.read_text())
    export = tmp_path / "export.json"
    export.write_text(json.dumps(mirror_export_of(graph_dir)))
    assert run("artifacts", "add", "brave-otter-1002", "runs/train.log",
               "--graph-dir", graph_dir, "--repo", repo) == 0
    assert hg.verify_mirror(graph_dir, export).violations() == []
    capsys.readouterr()


def test_update_still_refuses_record_nodes(tmp_path, capsys, monkeypatch):
    """Proof the refusal was not weakened to make room for `artifacts`."""
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    assert run("artifacts", "add", "brave-otter-1002", "runs/train.log",
               "--graph-dir", graph_dir, "--repo", repo) == 0
    code, sha = run_out(capsys, "update", "brave-otter-1002", "--graph-dir", graph_dir,
                        "--print-sha")
    assert code == 0
    replacement = body_file(tmp_path, "new.md", "## State Impact\n\nnone: nothing\n")
    assert run("update", "brave-otter-1002", "--graph-dir", graph_dir,
               "--body", replacement, "--expect", sha.strip(), "--reconcile") == 2
    assert "append-only" in capsys.readouterr().err


def test_a_repo_reached_through_a_symlink_still_reads_as_inside(tmp_path):
    """Lexical containment first, `realpath` only as a fallback.

    On darwin `/tmp` is a symlink to `/private/tmp`, so a repo root and a cwd
    describing the same directory routinely disagree lexically. Free on this
    platform, and the reason the fallback exists at all."""
    real = tmp_path / "real"
    (real / "runs").mkdir(parents=True)
    (real / "runs" / "train.log").write_text("x\n")
    link = tmp_path / "link"
    link.symlink_to(real)
    stored, abs_path, outside = hg.normalize_artifact_path(
        str(real / "runs" / "train.log"), link)
    assert (stored, outside) == ("runs/train.log", False)
    assert abs_path.exists()
    # and the other direction: a path through the link, a root at the real place
    stored, _abs, outside = hg.normalize_artifact_path(
        str(link / "runs" / "train.log"), real)
    assert (stored, outside) == ("runs/train.log", False)


def test_a_symlink_inside_the_repo_is_kept_as_the_pointer_the_author_meant(tmp_path):
    """A link into `/Volumes/big` is not rewritten into an absolute path: the author
    pointed at the repo-relative name on purpose, and that is what travels."""
    repo, _graph_dir = artifact_project(tmp_path, files=())
    outside_dir = tmp_path / "big"
    (outside_dir / "runs").mkdir(parents=True)
    (outside_dir / "runs" / "train.log").write_text("x\n")
    (repo / "runs").symlink_to(outside_dir / "runs")
    stored, _abs, outside = hg.normalize_artifact_path("runs/train.log", repo,
                                                       cwd=repo)
    assert (stored, outside) == ("runs/train.log", False)


def test_artifacts_on_a_state_node_is_a_violation(tmp_path):
    repo, graph_dir = artifact_project(tmp_path)
    node = hg.load_local_nodes(graph_dir, "state")["bright-harbor-2001"]
    hg.write_node_artifacts(node, ["runs/train.log"])
    report = hg.Report()
    hg.check_artifact_placement(hg.load_local_graph(graph_dir, "state"), report)
    assert len(report.violations()) == 1
    assert "Provenance" in report.violations()[0].message


def test_artifacts_add_refuses_a_state_node(tmp_path, capsys, monkeypatch):
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    assert run("artifacts", "add", "bright-harbor-2001", "runs/train.log",
               "--graph-dir", graph_dir, "--repo", repo) == 2
    assert "state node" in capsys.readouterr().err


def test_a_missing_artifact_warns_and_check_still_exits_zero(tmp_path, capsys):
    """A gitignored dataset absent on a fresh clone must never fail CI."""
    repo, graph_dir = artifact_project(tmp_path)
    node = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    hg.write_node_artifacts(node, ["runs/gone.log"])
    config = artifact_config(tmp_path, graph_dir)
    assert run("export", "--graph-dir", graph_dir, "--out-dir", tmp_path / "cache") == 0
    code, out = run_out(capsys, "check", "--record", tmp_path / "cache" / "record.json",
                        "--state", tmp_path / "cache" / "state.json",
                        "--config", config, "--repo", repo)
    assert code == 0
    assert "not in the working tree" in out
    assert "0 violation(s)" in out


def test_a_project_that_declares_no_artifacts_hears_nothing(tmp_path, capsys):
    repo, graph_dir = artifact_project(tmp_path)
    config = artifact_config(tmp_path, graph_dir)
    assert run("export", "--graph-dir", graph_dir, "--out-dir", tmp_path / "cache") == 0
    code, out = run_out(capsys, "check", "--record", tmp_path / "cache" / "record.json",
                        "--state", tmp_path / "cache" / "state.json",
                        "--config", config, "--repo", repo)
    assert code == 0 and "artifact" not in out


def test_import_force_preserves_a_locally_added_artifact_list(tmp_path, capsys):
    """No export can supply `artifacts:`, so a re-import would otherwise delete the
    author's whole evidence index — and `--force` is exactly what an upgrade needs."""
    graph_dir = imported(tmp_path)
    node = hg.load_local_nodes(graph_dir, "record")["brisk-otter-0002"]
    hg.write_node_artifacts(node, ["runs/train.log"])
    assert run("import", "--graph-dir", graph_dir, "--record", CLEAN / "record.json",
               "--state", CLEAN / "state.json", "--force") == 0
    assert hg.load_local_nodes(graph_dir, "record")["brisk-otter-0002"].artifacts \
        == ["runs/train.log"]
    capsys.readouterr()


def test_artifacts_are_appended_in_argument_order_never_sorted(tmp_path, capsys, monkeypatch):
    """An evidence list has a reading order — the log, then the plot it explains."""
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path, files=("z.log", "a.png"))
    assert run("artifacts", "add", "brave-otter-1002", "z.log", "a.png",
               "--graph-dir", graph_dir, "--repo", repo) == 0
    assert hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"].artifacts \
        == ["z.log", "a.png"]
    capsys.readouterr()


def test_artifacts_add_refuses_a_missing_file_unless_allowed(tmp_path, capsys, monkeypatch):
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    assert run("artifacts", "add", "brave-otter-1002", "runs/nope.log",
               "--graph-dir", graph_dir, "--repo", repo) == 2
    assert "no such file" in capsys.readouterr().err
    assert run("artifacts", "add", "brave-otter-1002", "runs/nope.log",
               "--graph-dir", graph_dir, "--repo", repo, "--allow-missing") == 0
    assert hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"].artifacts \
        == ["runs/nope.log"]
    capsys.readouterr()


def test_artifacts_rm_is_loud_about_an_unmatched_path(tmp_path, capsys, monkeypatch):
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    assert run("artifacts", "add", "brave-otter-1002", "runs/train.log",
               "--graph-dir", graph_dir, "--repo", repo) == 0
    assert run("artifacts", "rm", "brave-otter-1002", "runs/other.log",
               "--graph-dir", graph_dir, "--repo", repo) == 2
    assert "is not on `brave-otter-1002`" in capsys.readouterr().err
    code, out = run_out(capsys, "artifacts", "rm", "brave-otter-1002", "runs/train.log",
                        "--graph-dir", graph_dir, "--repo", repo)
    assert code == 0 and "it did not delete runs/train.log" in out
    node = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    assert node.artifacts == [] and "artifacts" not in node.meta   # omitted when empty
    assert (repo / "runs" / "train.log").exists()                  # and nothing deleted


def test_artifacts_mv_replaces_in_position_and_never_touches_the_tree(tmp_path, capsys, monkeypatch):
    repo, graph_dir = in_artifact_repo(
        monkeypatch, tmp_path, files=("a.log", "b.png", "c.txt", "moved.png"))
    assert run("artifacts", "add", "brave-otter-1002", "a.log", "b.png", "c.txt",
               "--graph-dir", graph_dir, "--repo", repo) == 0
    code, out = run_out(capsys, "artifacts", "mv", "brave-otter-1002", "b.png",
                        "moved.png", "--graph-dir", graph_dir, "--repo", repo)
    assert code == 0 and "git mv" in out
    assert hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"].artifacts \
        == ["a.log", "moved.png", "c.txt"]
    assert (repo / "b.png").exists()          # the working tree is untouched


def test_artifacts_ls_flags_what_is_wrong_with_each_path(tmp_path, capsys):
    import subprocess

    repo, graph_dir = artifact_project(tmp_path, files=("tracked.log", "loose.log"))
    subprocess.run(["git", "-C", str(repo), "add", "tracked.log"], check=True)
    node = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    hg.write_node_artifacts(node, ["tracked.log", "loose.log", "gone.log",
                                   "../outside.log"])
    code, out = run_out(capsys, "artifacts", "ls", "--graph-dir", graph_dir,
                        "--repo", repo, "--json")
    assert code == 0
    flags = {r["path"]: r["flags"] for r in json.loads(out)["artifacts"]}
    assert flags == {"tracked.log": [], "loose.log": ["untracked"],
                     "gone.log": ["missing"], "../outside.log": ["outside repo"]}


def test_a_non_string_artifact_entry_fails_at_load(tmp_path):
    """A mirror export's `artifacts` are attachment objects; this key is not that."""
    repo, graph_dir = artifact_project(tmp_path)
    node = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    meta = dict(node.meta)
    meta["artifacts"] = [{"artifact_id": "art-1"}]
    node.path.write_text(hg.render_node_file(meta, node.content))
    with pytest.raises(hg.LocalGraphError, match="is not a string"):
        hg.load_local_nodes(graph_dir, "record")


def test_new_record_carries_artifacts_and_warns_without_refusing(tmp_path, capsys, monkeypatch):
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    capsys.readouterr()
    assert run("new", "record", "--graph-dir", graph_dir,
               "--repo", repo, "--parent", "brave-otter-1002",
               "--title", "Ran the sweep", "--none", "nothing yet",
               "--artifact", "runs/train.log", "--artifact", "runs/gone.log") == 0
    captured = capsys.readouterr()
    node = hg.load_local_nodes(graph_dir, "record")[captured.out.split()[0]]
    assert node.artifacts == ["runs/train.log", "runs/gone.log"]
    # warned, not refused: the whole node was already composed and validated
    assert "not in the working tree" in captured.err


def test_new_state_refuses_an_artifact(tmp_path, capsys, monkeypatch):
    repo, graph_dir = in_artifact_repo(monkeypatch, tmp_path)
    assert run("new", "state", "--graph-dir", graph_dir, "--repo", repo, "--reconcile",
               "--parent", "bright-harbor-2001", "--title", "Claim",
               "--status", "working", "--prov", "brave-otter-1002 — why",
               "--artifact", "runs/train.log") == 2
    assert "record-only" in capsys.readouterr().err


def test_the_viz_payload_carries_record_artifacts_and_no_state_key(tmp_path):
    """The state-node dict's *absence* of the key documents decision 3."""
    repo, graph_dir = artifact_project(tmp_path)
    node = hg.load_local_nodes(graph_dir, "record")["brave-otter-1002"]
    hg.write_node_artifacts(node, ["runs/train.log"])
    data = hg.build_viz_data(hg.load_local_graph(graph_dir, "record"),
                             hg.load_local_graph(graph_dir, "state"))
    entry = next(n for n in data["record"]["nodes"] if n["slug"] == "brave-otter-1002")
    assert entry["artifacts"] == ["runs/train.log"]
    assert all("artifacts" not in n for n in data["state"]["nodes"])
