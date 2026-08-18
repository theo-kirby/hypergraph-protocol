"""Shared graph fixtures for the test suite.

`hg` is the tool loaded straight from `tools/hypergraph.py` — it runs as a `uv run`
script, so there is no installed package to import in a dev checkout.
"""
import importlib.util
import json
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

# The mirror sibling, loaded through the same `_mirror()` the CLI uses — so the
# loader itself is under test on every run. Its public symbols are re-exported
# onto `hg` for the many existing `hg.<symbol>` reads; tests that *patch* mirror
# internals must patch `hgm` (the module the mirror code actually reads).
hgm = hg._mirror()
for _name in dir(hgm):
    if not _name.startswith("__") and not hasattr(hg, _name):
        setattr(hg, _name, getattr(hgm, _name))


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
    hg.apply_push_results(graph_dir, {"results": [create_result(op)
                                                  for op in plan["ops"]]})
    return graph_dir


def create_result(op, *, prefix="fw-", slug_prefix="wild-river-", revision=1):
    """What one executed `create` op folds back — ids, body stamp, **and topology**.

    The parent stamp is not decoration here: a create is a node's first edge write, so
    a fixture that skips it leaves a graph whose next `push_plan` schedules an edge
    move for edges the create already made. Fabricating it is what keeps "stamped by
    the fixture" and "stamped by driving the real loop" indistinguishable — including
    the part where a **root is never stamped**, because an empty parent set hashes to a
    stable value that the plan would then read as "parents cleared locally"."""
    result = {"slug": op["slug"],
              "flywheel": {"node_id": f"{prefix}{op['slug']}",
                           "slug_name": f"{slug_prefix}{op['slug'][-4:]}",
                           "revision": revision},
              "content_sha256": op["content_sha256"]}
    if op["parent_slugs"]:
        result["parents_sha256"] = op["parents_sha256"]
        result["parents"] = [f"{prefix}{p}" for p in op["parent_slugs"]]
    return result


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
    """The export a faithful mirror would produce for pushed_graph.

    `parent_ids` is part of "faithful": a real `export:subgraph` carries the edges —
    it is the only read that does, since `nodes:get` reports `has_parents` and no ids
    at any projection — and `verify_mirror` compares them by default."""
    nodes = []
    for kind in ("record", "state"):
        local = hg.load_local_nodes(graph_dir, kind)
        for node in local.values():
            fw = node.meta["flywheel"]
            nodes.append({"node_id": fw["node_id"], "slug_name": fw["slug"],
                          "title": node.title, "content": node.content,
                          "summary": str(node.meta.get("summary") or ""),
                          "revision": fw["revision"],
                          "parent_ids": [local[p].meta["flywheel"]["node_id"]
                                         for p in node.parents if p in local]})
    return {"version": 1, "nodes": nodes}


# --------------------------------------------------------------- the fake host
# deliberately not `fw-`-prefixed: `landed()` uses that prefix to count
# the nodes this push created, and the roots pre-exist.
RECORD_ROOT = "host-root-record"
STATE_ROOT = "host-root-state"


# --------------------------------------------------------------- the fake host

class FakeTransport:
    """In-memory stand-in for the hosted graph.

    Mints `fw-<local slug>` node ids — the exact shape `pushed_graph()` fabricates —
    so a graph produced by driving this loop and one stamped by the fixture are
    indistinguishable, and every existing verify assertion keeps working."""

    name = "fake"

    def __init__(self, graph_dir=None, *, user_id="acct-1"):
        self.nodes: dict[str, dict] = {}
        self.kids: dict[str, list[str]] = {}
        self.calls: list[tuple[str, str]] = []
        self.faults: dict[str, list] = {}      # what → exceptions to raise, in order
        self.tags: dict[str, list[dict]] = {}  # root node_id → tag definitions
        self.attachments: dict[str, list[dict]] = {}   # node_id → artifact records
        self.blobs: dict[str, bytes] = {}      # artifact_id → the bytes it received
        self._artifact_seq = 0
        self.user_id = user_id
        self._slug_by_sha: dict[str, str] = {}
        if graph_dir is not None:
            for kind in ("record", "state"):
                for slug, node in hg.load_local_nodes(graph_dir, kind, missing_ok=True).items():
                    self._slug_by_sha[node.sha256] = slug
        for root in (RECORD_ROOT, STATE_ROOT):
            self.nodes[root] = {"node_id": root, "slug_name": f"mirror-{root}",
                                "title": "root", "content": "root\n", "summary": "",
                                "revision": 0, "can_write": True, "is_owner": True}
            self.kids[root] = []

    # --- fault injection -----------------------------------------------------
    def fail(self, what: str, *excs):
        self.faults.setdefault(what, []).extend(excs)

    def _maybe_fail(self, what: str):
        queue = self.faults.get(what)
        if queue:
            raise queue.pop(0)

    def version(self):
        return "fake 0"

    # --- the seven operations ------------------------------------------------
    def auth_status(self):
        self.calls.append(("auth_status", ""))
        self._maybe_fail("auth_status")
        return {"authenticated": True, "user_id": self.user_id, "auth_method": "api_key"}

    def get_node(self, node_id):
        self.calls.append(("get_node", node_id))
        raw = self.nodes.get(node_id)
        if raw is None:
            raise hg.MirrorError(f"nodes:get {node_id}: not found")
        return hg.MirrorNode.from_raw(raw, context="get_node")

    def children(self, node_id):
        self.calls.append(("children", node_id))
        for kid in self.kids.get(node_id, []):
            yield hg.MirrorNode.from_raw(self.nodes[kid], context="children",
                                         need_revision=False)

    def commit_new(self, *, parent_ids, title, content, summary="", repo_context=None,
                   temp_id=None):
        slug = self._slug_by_sha.get(hg.body_sha256(content), f"anon-{len(self.nodes)}")
        self.calls.append(("commit_new", slug))
        self._maybe_fail(f"create {slug}")
        self._maybe_fail("create")
        node_id = f"fw-{slug}"
        if node_id in self.nodes:
            raise AssertionError(f"duplicate create of {slug} — the journal failed")
        self.nodes[node_id] = {"node_id": node_id,
                               "slug_name": f"wild-river-{slug[-4:]}", "title": title,
                               "content": content, "summary": summary, "revision": 1,
                               "can_write": True, "is_owner": True,
                               "parent_ids": list(parent_ids)}
        self.kids.setdefault(node_id, [])
        for parent in parent_ids:
            self.kids.setdefault(parent, []).append(node_id)
        return hg.MirrorNode.from_raw(self.nodes[node_id], context="commit_new")

    def commit(self, *, node_id, base_revision, title, content, summary="",
               repo_context=None):
        slug = self._slug_by_sha.get(hg.body_sha256(content), node_id)
        self.calls.append(("commit", str(slug)))
        self._maybe_fail(f"update {slug}")
        self._maybe_fail("update")
        raw = self.nodes.get(node_id)
        if raw is None:
            raise hg.MirrorError(f"nodes:commit {node_id}: not found")
        if int(base_revision) != int(raw["revision"]):
            raise hg.MirrorConflict(
                f"nodes:commit {node_id}: stale committed revision")
        raw.update({"title": title, "content": content, "summary": summary,
                    "revision": raw["revision"] + 1})
        return hg.MirrorNode.from_raw(raw, context="commit")

    def export_subgraph(self, node_ids, out, *, include_descendants=True, max_nodes=5000):
        self.calls.append(("export", ",".join(node_ids)))
        reach, queue = set(), list(node_ids)
        while queue:
            nid = queue.pop()
            if nid in reach or nid not in self.nodes:
                continue
            reach.add(nid)
            queue.extend(self.kids.get(nid, []))
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        exported = []
        for nid in sorted(reach):
            raw = dict(self.nodes[nid])
            if nid in self.tags:      # the host echoes the vocabulary on graph roots
                raw["graph_tags"] = [dict(t) for t in self.tags[nid]]
            exported.append(raw)
        out.write_text(json.dumps({"version": 1, "nodes": exported}))
        return out

    def delete_node(self, node_id, *, mode="detach_shared"):
        self.calls.append(("delete", node_id))
        self.nodes.pop(node_id, None)

    # --- re-parenting --------------------------------------------------------
    # Models the four properties the real host has and a naive fake would not: both
    # endpoints take four optimistic locks, the add **bumps the child** (so a caller
    # that computes a revision once and reuses it across a batch 409s), the add
    # refuses an edge that would close a cycle, and removing the last parent is
    # refused — the reason add-before-remove is the stated ordering.
    def _edge_locks(self, node_id, parent_id, expected_revision,
                    expected_parent_revision, what):
        child, parent = self.nodes.get(node_id), self.nodes.get(parent_id)
        if child is None or parent is None:
            raise hg.MirrorError(f"{what}: {node_id} or {parent_id} not found")
        if int(expected_revision) != int(child["revision"]):
            raise hg.MirrorConflict(f"{what} {node_id}: stale child revision")
        if int(expected_parent_revision) != int(parent["revision"]):
            raise hg.MirrorConflict(f"{what} {parent_id}: stale parent revision")
        return child, parent

    def add_parent(self, *, node_id, parent_id, expected_revision,
                   expected_parent_revision):
        self.calls.append(("add_parent", f"{node_id}->{parent_id}"))
        self._maybe_fail(f"add_parent {node_id}")
        self._maybe_fail("add_parent")
        child, _parent = self._edge_locks(node_id, parent_id, expected_revision,
                                          expected_parent_revision, "nodes:add-parent")
        seen, stack = set(), [parent_id]
        while stack:
            current = stack.pop()
            if current == node_id:
                raise hg.MirrorError(
                    f"nodes:add-parent {node_id}: that edge would create a cycle")
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.nodes.get(current, {}).get("parent_ids") or [])
        held = child.setdefault("parent_ids", [])
        if parent_id not in held:
            held.append(parent_id)
            self.kids.setdefault(parent_id, []).append(node_id)
        child["revision"] += 1

    def remove_parent(self, *, node_id, parent_id, expected_revision,
                      expected_parent_revision):
        self.calls.append(("remove_parent", f"{node_id}->{parent_id}"))
        self._maybe_fail(f"remove_parent {node_id}")
        self._maybe_fail("remove_parent")
        child, _parent = self._edge_locks(node_id, parent_id, expected_revision,
                                          expected_parent_revision,
                                          "nodes:remove-parent")
        held = child.setdefault("parent_ids", [])
        if held == [parent_id]:
            raise AssertionError(
                f"removing {parent_id} would leave {node_id} parentless — "
                "add-before-remove exists to make this unreachable")
        if parent_id in held:
            held.remove(parent_id)
            if node_id in self.kids.get(parent_id, []):
                self.kids[parent_id].remove(node_id)
        child["revision"] += 1

    # --- op 10: tags ---------------------------------------------------------
    # Models the two properties the real host has and a naive fake would not:
    # `tags:create` bumps the *root* revision every time, and `tags:assign` is an
    # atomic replace that bumps the *node* revision.
    def graph_tags(self, root_node_id):
        self.calls.append(("graph_tags", root_node_id))
        self._maybe_fail("graph_tags")
        raw = self.nodes.get(root_node_id)
        if raw is None:
            raise hg.MirrorError(f"nodes:get {root_node_id}: not found")
        return list(self.tags.get(root_node_id, [])), int(raw["revision"])

    def create_tag(self, *, root_node_id, name, expected_revision, bg_color,
                   text_color, one_only=False, track_history=False):
        self.calls.append(("create_tag", name))
        self._maybe_fail(f"create_tag {name}")
        self._maybe_fail("create_tag")
        root = self.nodes[root_node_id]
        if int(expected_revision) != int(root["revision"]):
            raise hg.MirrorConflict(
                f"tags:create {name}: stale root revision "
                f"({expected_revision} vs {root['revision']})")
        existing = self.tags.setdefault(root_node_id, [])
        if any(t["name"] == name for t in existing):
            raise AssertionError(
                f"duplicate tag definition for {name!r} — resolve-by-name failed")
        tag = {"tag_id": f"tag-{name}", "name": name, "bg_color": bg_color,
               "text_color": text_color, "one_only": bool(one_only),
               "track_history": bool(track_history)}
        existing.append(tag)
        # Measured on the live host: creating a tag bumps the committed revision of
        # EVERY node in that graph, not just the root. 22 creations moved all 196
        # nodes of neural-whoop's mirror. Modelling only the root here would let a
        # push that leaves the whole graph reading as drift pass its tests.
        reach, queue = set(), [root_node_id]
        while queue:
            nid = queue.pop()
            if nid in reach or nid not in self.nodes:
                continue
            reach.add(nid)
            queue.extend(self.kids.get(nid, []))
        for nid in reach:
            self.nodes[nid]["revision"] += 1
        return dict(tag)

    def assign_tags(self, *, node_id, tag_ids, expected_revision):
        self.calls.append(("assign_tags", node_id))
        self._maybe_fail(f"assign_tags {node_id}")
        self._maybe_fail("assign_tags")
        raw = self.nodes.get(node_id)
        if raw is None:
            raise hg.MirrorError(f"tags:assign {node_id}: not found")
        if int(expected_revision) != int(raw["revision"]):
            raise hg.MirrorConflict(f"tags:assign {node_id}: stale revision")
        raw["tag_ids"] = list(tag_ids)     # atomic replace, never an add
        raw["revision"] += 1               # and it moves the node

    # --- op 9: artifacts -----------------------------------------------------
    # Models the three properties the real host has and a naive fake would not:
    # finalize appends a whole batch with **one** revision bump (a fake that bumped
    # per item would let a broken fold pass), the listing carries the node revision
    # so one read answers both questions, and a duplicate title is an AssertionError
    # rather than a second row — the artifact analogue of the duplicate-create guard.
    def artifacts(self, node_id):
        self.calls.append(("artifacts", node_id))
        self._maybe_fail(f"artifacts {node_id}")
        self._maybe_fail("artifacts")
        raw = self.nodes.get(node_id)
        if raw is None:
            raise hg.MirrorError(f"artifacts:list {node_id}: not found")
        return [dict(a) for a in self.attachments.get(node_id, [])], int(raw["revision"])

    def upload_artifacts(self, *, node_id, expected_revision, items):
        self.calls.append(("upload_artifacts", node_id))
        self._maybe_fail(f"upload_artifacts {node_id}")
        self._maybe_fail("upload_artifacts")
        raw = self.nodes.get(node_id)
        if raw is None:
            raise hg.MirrorError(f"artifacts:upload {node_id}: not found")
        if int(expected_revision) != int(raw["revision"]):
            raise hg.MirrorConflict(f"artifacts:upload {node_id}: stale revision")
        if len(items) > hg.ARTIFACT_BATCH_ITEMS:
            raise AssertionError(
                f"{len(items)} items in one batch is over the host's "
                f"{hg.ARTIFACT_BATCH_ITEMS} ceiling")
        held = self.attachments.setdefault(node_id, [])
        for item in items:
            title = str(item["title"])
            if any(a["title"] == title for a in held):
                raise AssertionError(
                    f"duplicate artifact {title!r} on {node_id} — the dedupe or the "
                    "journal failed")
            self._artifact_seq += 1
            path = Path(item["local_path"])
            if not path.is_file():
                raise hg.MirrorError(f"artifacts:upload: no such file {path}")
            self.blobs[f"art-{self._artifact_seq}"] = path.read_bytes()
            held.append({"artifact_id": f"art-{self._artifact_seq}", "title": title,
                         "artifact_type": item["artifact_type"],
                         "media_type": item["media_type"],
                         "metadata": item.get("metadata"),
                         "created_at": "2026-08-14T00:00:00+00:00"})
        raw["revision"] += 1        # ONE bump for the whole batch
        return {}

    def delete_artifact(self, *_a, **_k):
        raise AssertionError("nothing in this design may ever call artifacts:delete")

    # --- assertions ----------------------------------------------------------
    def creates(self):
        """Create *attempts*, including ones that failed — not what the host holds."""
        return [slug for kind, slug in self.calls if kind == "commit_new"]

    def landed(self):
        """Nodes that actually exist on the host. A duplicate create raises before
        it can get here, so this is the count that matters."""
        return sorted(n for n in self.nodes if n.startswith("fw-"))


def config_for(graph_dir, **extra):
    cfg = {"project": "t", "graph_dir": str(graph_dir),
           "cache_dir": str(Path(graph_dir).parent / "cache"),
           "mirror": "flywheel",
           "mirror_roots": {"record": {"node_id": RECORD_ROOT},
                            "state": {"node_id": STATE_ROOT}}}
    cfg.update(extra)
    return cfg
