"""Shared graph fixtures for the test suite.

Not named conftest.py: tests/browser/ has one, and two same-named modules on the
path shadow each other.

`hg` is the tool loaded straight from `tools/hypergraph.py` — it runs as a `uv run`
script, so there is no installed package to import in a dev checkout.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tools" / "fixtures"
CLEAN = FIXTURES / "clean"
LOCAL = FIXTURES / "local-graph"

_spec = importlib.util.spec_from_file_location("hypergraph_local", ROOT / "tools" / "hypergraph.py")
hg = importlib.util.module_from_spec(_spec)
sys.modules["hypergraph_local"] = hg
_spec.loader.exec_module(hg)


def local_graph_copy(tmp_path):
    """A writable copy of the local-graph fixture: 3 record + 2 state nodes."""
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    for kind in ("record", "state"):
        target = graph_dir / kind
        target.mkdir()
        for src in (LOCAL / "graph" / kind).glob("*.md"):
            (target / src.name).write_text(src.read_text())
    return graph_dir


def pushed_graph(tmp_path):
    """LOCAL graph copied, planned, and stamped as if the mirror push ran.

    The fabricated ids are `fw-<slug>`, which is exactly what FakeTransport mints —
    so a graph built here and a graph built by driving the real push loop are
    indistinguishable, and the verify assertions work against both."""
    graph_dir = local_graph_copy(tmp_path)
    plan = hg.push_plan(graph_dir)
    results = {"results": [{"slug": op["slug"],
                            "flywheel": {"node_id": f"fw-{op['slug']}",
                                         "slug_name": f"wild-river-{op['slug'][-4:]}",
                                         "revision": 1},
                            "content_sha256": op["content_sha256"]} for op in plan["ops"]]}
    hg.apply_push_results(graph_dir, results)
    return graph_dir


# The archive vocabulary the heal tests repair against. Shaped like the real one
# [rec: fresh-spire-9002]: family prefixes, a `★` pointer tag with `one_only` and
# `track_history` set, and colours that must survive the trip.
ARCHIVE_TAGS = [
    {"tag_id": "tag-e71a", "name": "kind:experiment", "bg_color": "#1F3A5F",
     "text_color": "#E8F0FB", "one_only": False, "track_history": False},
    {"tag_id": "tag-7d89", "name": "outcome:GREEN", "bg_color": "#1E5F2E",
     "text_color": "#E7FBE9", "one_only": False, "track_history": False},
    {"tag_id": "tag-4860", "name": "★ studio-baseline", "bg_color": "#7A5A1A",
     "text_color": "#FFF4DD", "one_only": True, "track_history": True},
]
ARCHIVE_ASSIGNMENTS = {
    "wise-anchor-1001": [],                        # the root, untagged as in the field
    "brave-otter-1002": ["tag-e71a", "tag-7d89"],
    "calm-fern-1003": ["tag-e71a", "tag-4860"],
    "bright-harbor-2001": ["tag-7d89"],
    "quiet-summit-2002": ["tag-e71a"],
}


def forked_graph(tmp_path):
    """local_graph_copy with an `origin:` block on every node — what `import --fork`
    leaves behind, and the state every adopted repo is in before it is healed."""
    graph_dir = local_graph_copy(tmp_path)
    for kind in ("record", "state"):
        for slug, node in hg.load_local_nodes(graph_dir, kind).items():
            meta = dict(node.meta)
            meta["origin"] = {"backend": "flywheel", "node_id": f"arch-{slug}",
                              "slug": slug, "exported_at": "2026-08-01T00:00:00+00:00"}
            node.path.write_text(hg.render_node_file(meta, node.content))
    return graph_dir


def archive_export_of(graph_dir, assignments=None, *, echo_every=3):
    """The frozen archive's export for a `forked_graph`.

    Reproduces the split the real archive has: only *some* nodes echo `graph_tags`
    (130 of 189 in neural-whoop) while the rest carry `tag_ids` beside an empty list.
    A resolver that reads one node's copy silently loses a third of the graph, so this
    fixture is what makes the union in `collect_source_tags` a tested requirement
    rather than a defensive habit. The parentless node always echoes — it is the
    authoritative copy."""
    assignments = ARCHIVE_ASSIGNMENTS if assignments is None else assignments
    nodes = []
    index = 0
    for kind in ("record", "state"):
        for slug, node in hg.load_local_nodes(graph_dir, kind).items():
            index += 1
            parentless = not node.parents
            echoes = parentless or index % echo_every == 0
            nodes.append({
                "node_id": f"arch-{slug}", "slug_name": slug, "title": node.title,
                "created_at": node.created_at, "content": node.content,
                "summary": str(node.meta.get("summary") or ""),
                "revision": 3,
                "incoming_ids": [f"arch-{p}" for p in node.parents],
                "tag_ids": list(assignments.get(slug, [])),
                "graph_tags": [dict(t) for t in ARCHIVE_TAGS] if echoes else [],
            })
    return {"version": 1, "exported_at": "2026-08-01T00:00:00+00:00", "nodes": nodes}


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
