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
