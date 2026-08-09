#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Hypergraph protocol tooling: invariant checker, STATE.md renderer, local backend.

Consumes JSON graph exports (backend `export_graph`, e.g. flywheel_export_subgraph
saved to .hypergraph/cache/{record,state}.json). No network, no auth, deterministic.

    hypergraph.py check  --record record.json --state state.json [--config config.yml]
    hypergraph.py render --state state.json [--config config.yml] [-o STATE.md]
    hypergraph.py viz    --record record.json --state state.json [--config config.yml] [-o viz.html]
                         [--format html|excaligraph] [--live] [--dev]

check exits 1 on any I2/I4/I5/I6/I7 violation (see SPEC.md). Warnings (I1 proxies)
and info lines never affect the exit code.

viz emits a self-contained interactive HTML file (no network, no JS dependencies)
with four views — Timeline (record graph as git-log lanes), Frontier (state graph
as a status board), Provenance (both graphs with cross-graph links) and Clusters
(impact sets as distance-field blobs). Open it straight from file://. The page is
authored under tools/viz/ and bundled into VIZ_TEMPLATE by tools/bundle_viz.py;
`--dev` reads those sources instead. `--format excaligraph` emits a graph spec for
`excaligraph build` instead, for hand-editable figures. `--live` additionally
writes a sibling <output>.data.json and has the page poll it — the one output that
is deliberately not a single file, which is why it takes a flag and needs the
directory served over http.

The local (git-native) backend keeps both graphs as committed markdown files under
.hypergraph/graph/{record,state}/<slug>.md and produces the very same export JSON
(backend/local-adapter.md):

    hypergraph.py export [--config config.yml] [--graph-dir D] [--out-dir cache/]
    hypergraph.py import --record record.json --state state.json [--graph-dir D]
    hypergraph.py new record|state --title T --body body.md ...
    hypergraph.py update SLUG --body new.md --expect <sha256> --reconcile
    hypergraph.py push --plan [-o plan.json] | --record-result results.json
    hypergraph.py push --verify --against export.json | --legend [-o legend.md]
    hypergraph.py skills install [--user | --target DIR]

Mirroring to Flywheel stays out of this file: `push --plan` emits an ordered plan of
MCP calls for the skill layer to execute, and `push --record-result` folds the
returned ids back into the node files. The tool itself never touches the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SLUG_RE = re.compile(r"\b[a-z][a-z0-9]*-[a-z][a-z0-9]*-\d{4}\b")
STATUS_RE = re.compile(r"^Status:\s*(?P<status>[a-z]+)\s*$")
STATUSES = {"working", "open", "broken", "blocked", "superseded"}
FRONTIER = {"open", "broken", "blocked"}
FRONTIER_ORDER = {"broken": 0, "blocked": 1, "open": 2}

IMPACT_LINE_RE = re.compile(r"^-\s*target:\s*(?P<target>.+?)\s*(?:—|--)\s*(?P<delta>.+)$")
IMPACT_NONE_RE = re.compile(r"^none:\s*(?P<reason>.+)$")
NEW_TARGET_RE = re.compile(r"^NEW\s+(?P<name>[a-z0-9][a-z0-9-]*)$")
CITE_RE = re.compile(r"\[rec:\s*(?P<slug>[a-z0-9-]+)\s*\]")
NEG_ENTRY_RE = re.compile(
    r"^-\s*\[\s*scope:\s*(?P<scope>[^|\]]+?)\s*"
    r"\|\s*confidence:\s*(?P<conf>[a-z]+)\s*"
    r"\|\s*evidence:\s*(?P<ev>[^|\]]+?)\s*"
    r"(?:\|\s*decision:\s*(?P<dec>[^|\]]+?)\s*)?"
    r"\]\s*(?P<stmt>.+)$"
)
HWM_RE = re.compile(r"^-?\s*high_water_mark:\s*(?P<hwm>\S+)\s*$")
RECONCILED_AT_RE = re.compile(r"^-?\s*reconciled_at:\s*(?P<ts>\S+)\s*$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


@dataclass
class Node:
    node_id: str
    slug: str
    title: str
    content: str
    parent_ids: list[str]
    created_at: str

    @property
    def ref(self) -> str:
        return self.slug or self.node_id

    @property
    def created(self) -> datetime | None:
        return parse_ts(self.created_at)


@dataclass
class Graph:
    nodes: dict[str, Node]  # by node_id
    by_slug: dict[str, Node]

    def roots(self) -> list[Node]:
        return [n for n in self.nodes.values() if not n.parent_ids]


@dataclass
class Finding:
    level: str  # violation | warning | info
    invariant: str  # I1..I8 or "-"
    node: str  # slug/id of the offending node, or "-"
    message: str

    def __str__(self) -> str:
        return f"{self.invariant} [{self.node}] {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, invariant: str, node: str, message: str) -> None:
        self.findings.append(Finding(level, invariant, node, message))

    def violations(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "violation"]

    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]

    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "info"]


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _norm_parents(raw: object) -> list[str]:
    if not raw:
        return []
    out = []
    for p in raw if isinstance(raw, list) else [raw]:
        if isinstance(p, dict):
            pid = p.get("node_id") or p.get("id")
            if pid:
                out.append(str(pid))
        else:
            out.append(str(p))
    return out


def load_graph(path: Path) -> Graph:
    data = json.loads(Path(path).read_text())
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    nodes: dict[str, Node] = {}
    for raw in raw_nodes:
        node = Node(
            node_id=str(raw.get("node_id") or raw.get("id") or ""),
            slug=str(raw.get("slug_name") or raw.get("slug") or ""),
            title=str(raw.get("title") or ""),
            content=str(raw.get("content") or ""),
            # flywheel_export_subgraph encodes parent edges as incoming_ids
            parent_ids=_norm_parents(
                raw.get("parent_ids") or raw.get("parents") or raw.get("incoming_ids")
            ),
            created_at=str(raw.get("created_at") or raw.get("committed_at") or ""),
        )
        if node.node_id:
            nodes[node.node_id] = node
    by_slug = {n.slug: n for n in nodes.values() if n.slug}
    return Graph(nodes=nodes, by_slug=by_slug)


def split_sections(content: str) -> tuple[str, dict[str, str]]:
    """Split markdown on `## ` headings → (preamble, {lowercased heading: body})."""
    content = COMMENT_RE.sub("", content)
    pre: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in content.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1).lower()
            sections.setdefault(current, [])
        elif current is None:
            pre.append(line)
        else:
            sections[current].append(line)
    return "\n".join(pre), {k: "\n".join(v).strip() for k, v in sections.items()}


def find_root(graph: Graph, configured: dict | None, report: Report, label: str) -> Node | None:
    if configured:
        node = graph.by_slug.get(configured.get("slug") or "") or graph.nodes.get(
            configured.get("node_id") or ""
        )
        if node:
            return node
        report.add("violation", "I5", str(configured.get("slug")),
                   f"configured {label} root not present in the {label} export")
        return None
    roots = graph.roots()
    if len(roots) == 1:
        return roots[0]
    report.add("violation", "I5", "-",
               f"cannot identify {label} root: {len(roots)} parentless nodes in export "
               "(pass --config to disambiguate)")
    return None


# ---------------------------------------------------------------- invariant checks

def check_impacts(record: Graph, state: Graph, record_root: Node | None, report: Report,
                  epoch_cutoff: datetime | None = None) -> None:
    """I2: every non-root record node declares parseable state impact.

    Record nodes created strictly before `epoch_cutoff` (the adoption-epoch marker's
    created_at) are legacy history and exempt from I2 (SPEC: Adoption epochs).
    """
    exempted = 0
    for node in record.nodes.values():
        if record_root and node.node_id == record_root.node_id:
            continue
        if epoch_cutoff is not None:
            created = node.created
            if created is not None and created < epoch_cutoff:
                exempted += 1
                continue
        _, sections = split_sections(node.content)
        body = sections.get("state impact")
        if body is None:
            report.add("violation", "I2", node.ref, "missing `## State Impact` section")
            continue
        entries, none_reason, bad = parse_impacts(body)
        for line in bad:
            report.add("violation", "I2", node.ref, f"unparseable impact line: {line!r}")
        if none_reason is not None and entries:
            report.add("violation", "I2", node.ref,
                       "declares both `none:` and impact targets — pick one")
        elif none_reason is None and not entries:
            report.add("violation", "I2", node.ref,
                       "`## State Impact` has no impact lines and no `none: <reason>`")
        for target, _delta, is_new in entries:
            if not is_new and target not in state.by_slug:
                report.add("violation", "I2", node.ref,
                           f"impact targets unknown state node `{target}`")
    if exempted:
        report.add("info", "I2", "-",
                   f"{exempted} pre-epoch record node(s) exempt from I2 (legacy history)")


def parse_impacts(body: str) -> tuple[list[tuple[str, str, bool]], str | None, list[str]]:
    """→ ([(target, delta, is_new)], none_reason, bad_lines)."""
    entries: list[tuple[str, str, bool]] = []
    none_reason: str | None = None
    bad: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if m := IMPACT_NONE_RE.match(line):
            none_reason = m.group("reason").strip()
            continue
        if m := IMPACT_LINE_RE.match(line):
            target = m.group("target").strip()
            delta = m.group("delta").strip()
            if new := NEW_TARGET_RE.match(target):
                entries.append((new.group("name"), delta, True))
            elif SLUG_RE.fullmatch(target):
                entries.append((target, delta, False))
            else:
                bad.append(line)
            continue
        bad.append(line)
    return entries, none_reason, bad


def check_state_nodes(record: Graph, state: Graph, state_root: Node | None, report: Report) -> None:
    """I4 provenance + citations, I6 status, I7 negative knowledge, I1 proxy."""
    for node in state.nodes.values():
        is_root = bool(state_root and node.node_id == state_root.node_id)
        _pre, sections = split_sections(node.content)

        if not is_root:
            check_status_line(node, report)
            check_provenance(node, sections, record, report)
            check_current_citations(node, sections, report)
        check_negative_knowledge(node, sections, record, report)

        for m in CITE_RE.finditer(COMMENT_RE.sub("", node.content)):
            slug = m.group("slug")
            if slug not in record.by_slug:
                report.add("violation", "I4", node.ref,
                           f"inline citation [rec: {slug}] does not resolve to a record node")


def check_status_line(node: Node, report: Report) -> None:
    first = next((ln for ln in node.content.splitlines() if ln.strip()), "")
    m = STATUS_RE.match(first.strip())
    if not m:
        report.add("violation", "I6", node.ref,
                   f"first line is not a Status line (got {first.strip()!r})")
    elif m.group("status") not in STATUSES:
        report.add("violation", "I6", node.ref,
                   f"invalid status {m.group('status')!r} (allowed: {', '.join(sorted(STATUSES))})")


def node_status(node: Node) -> str | None:
    first = next((ln for ln in node.content.splitlines() if ln.strip()), "")
    m = STATUS_RE.match(first.strip())
    return m.group("status") if m and m.group("status") in STATUSES else None


def check_provenance(node: Node, sections: dict[str, str], record: Graph, report: Report) -> None:
    body = sections.get("provenance")
    if not body:
        report.add("violation", "I4", node.ref, "missing or empty `## Provenance` section")
        return
    slugs: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        found = SLUG_RE.findall(line)
        if not found:
            report.add("violation", "I4", node.ref,
                       f"provenance line has no record slug: {line!r}")
        slugs.extend(found)
    if not slugs:
        report.add("violation", "I4", node.ref, "`## Provenance` lists no record slugs")
    for slug in slugs:
        if slug not in record.by_slug:
            report.add("violation", "I4", node.ref,
                       f"provenance slug `{slug}` does not resolve to a record node")


def check_current_citations(node: Node, sections: dict[str, str], report: Report) -> None:
    """I1 proxy (warning): claim units in ## Current without an inline citation."""
    body = sections.get("current")
    if body is None:
        report.add("warning", "I1", node.ref, "no `## Current` section")
        return
    bullets = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("- ")]
    units = bullets or [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    for unit in units:
        if not CITE_RE.search(unit):
            head = unit.splitlines()[0][:60]
            report.add("warning", "I1", node.ref,
                       f"claim without [rec: …] citation: {head!r}")


def check_negative_knowledge(node: Node, sections: dict[str, str], record: Graph, report: Report) -> None:
    body = sections.get("negative knowledge")
    if not body:
        return
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        m = NEG_ENTRY_RE.match(line)
        if not m:
            report.add("violation", "I7", node.ref,
                       f"negative-knowledge entry not in [scope | confidence | evidence] form: {line[:80]!r}")
            continue
        if m.group("conf") not in {"low", "medium", "high"}:
            report.add("violation", "I7", node.ref,
                       f"confidence must be low|medium|high, got {m.group('conf')!r}")
        ev_slugs = SLUG_RE.findall(m.group("ev"))
        if not ev_slugs:
            report.add("violation", "I7", node.ref,
                       f"negative-knowledge entry cites no evidence slugs: {line[:80]!r}")
        for slug in ev_slugs:
            if slug not in record.by_slug:
                report.add("violation", "I7", node.ref,
                           f"evidence slug `{slug}` does not resolve to a record node")
        scope = m.group("scope").strip().lower()
        dec = (m.group("dec") or "").strip()
        if scope.startswith("general"):
            if not dec:
                report.add("violation", "I7", node.ref,
                           "generalized scope requires a `decision:` record slug (SPEC I7)")
            elif dec not in record.by_slug:
                report.add("violation", "I7", node.ref,
                           f"decision slug `{dec}` does not resolve to a record node")


def read_hwm(state_root: Node) -> tuple[str | None, str | None]:
    """→ (hwm slug or 'none' or None-if-missing, reconciled_at or None)."""
    _, sections = split_sections(state_root.content)
    body = sections.get("reconciliation")
    if body is None:
        return None, None
    hwm = ts = None
    for line in body.splitlines():
        if m := HWM_RE.match(line.strip()):
            hwm = m.group("hwm")
        elif m := RECONCILED_AT_RE.match(line.strip()):
            ts = m.group("ts")
    return hwm, ts


def check_hwm(record: Graph, state: Graph, record_root: Node | None,
              state_root: Node | None, report: Report) -> None:
    """I5: parseable high-water mark on the state root + unreconciled enumeration."""
    if state_root is None:
        return
    hwm, ts = read_hwm(state_root)
    if hwm is None and ts is None:
        report.add("violation", "I5", state_root.ref,
                   "state root missing `## Reconciliation` section")
        return
    if not hwm:
        report.add("violation", "I5", state_root.ref, "missing `high_water_mark:` line")
    if not ts or parse_ts(ts) is None:
        report.add("violation", "I5", state_root.ref,
                   f"missing or unparseable `reconciled_at:` timestamp (got {ts!r})")

    hwm_node = None
    if hwm and hwm != "none":
        hwm_node = record.by_slug.get(hwm)
        if hwm_node is None:
            report.add("violation", "I5", state_root.ref,
                       f"high_water_mark `{hwm}` does not resolve to a record node")
            return
    if hwm is None:
        return

    cutoff = hwm_node.created if hwm_node else None
    unreconciled = []
    for node in record.nodes.values():
        if record_root and node.node_id == record_root.node_id:
            continue
        if hwm_node and node.node_id == hwm_node.node_id:
            continue
        created = node.created
        if cutoff is None or (created is not None and created > cutoff):
            unreconciled.append(node)
    report.add("info", "I5", state_root.ref,
               f"{len(unreconciled)} unreconciled record node(s) past high-water mark")
    stale: dict[str, int] = {}
    for node in unreconciled:
        _, sections = split_sections(node.content)
        entries, _none, _bad = parse_impacts(sections.get("state impact") or "")
        for target, _delta, is_new in entries:
            key = f"NEW {target}" if is_new else target
            stale[key] = stale.get(key, 0) + 1
    for target, count in sorted(stale.items()):
        report.add("info", "I5", target, f"{count} pending impact(s) awaiting reconcile")


# ------------------------------------------------------------------------- check

def load_config(path: Path | None) -> dict:
    if path is None:
        return {}
    import yaml  # deferred: PEP 723 dep, only needed when --config is passed

    return yaml.safe_load(Path(path).read_text()) or {}


def resolve_epoch_cutoff(config: dict, record: Graph, report: Report) -> datetime | None:
    """`epoch.marker` (config) → the marker record node's created_at, or None.

    Record nodes created strictly before the cutoff are legacy history (SPEC:
    Adoption epochs). An unresolvable marker is a violation — a silently ignored
    epoch would re-flag every legacy node.
    """
    marker = (config.get("epoch") or {}).get("marker")
    if not marker:
        return None
    node = record.by_slug.get(str(marker))
    if node is None:
        report.add("violation", "I2", str(marker),
                   "epoch.marker does not resolve to a record node")
        return None
    if node.created is None:
        report.add("violation", "I2", node.ref,
                   f"epoch marker has no parseable created_at (got {node.created_at!r})")
        return None
    return node.created


def run_check(record_path: Path, state_path: Path, config: dict | None = None) -> Report:
    config = config or {}
    report = Report()
    record = load_graph(record_path)
    state = load_graph(state_path)
    record_root = find_root(record, config.get("record_root"), report, "record")
    state_root = find_root(state, config.get("state_root"), report, "state")
    epoch_cutoff = resolve_epoch_cutoff(config, record, report)
    check_impacts(record, state, record_root, report, epoch_cutoff)
    check_state_nodes(record, state, state_root, report)
    check_hwm(record, state, record_root, state_root, report)
    return report


def cmd_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = run_check(args.record, args.state, config)
    violations, warnings, infos = report.violations(), report.warnings(), report.infos()
    for f in violations:
        print(f"VIOLATION {f}")
    for f in warnings:
        print(f"warning   {f}")
    for f in infos:
        print(f"info      {f}")
    print(f"\ncheck: {len(violations)} violation(s), {len(warnings)} warning(s)")
    return 1 if violations else 0


# ------------------------------------------------------------------------ render

def summary_line(node: Node) -> str:
    _, sections = split_sections(node.content)
    body = sections.get("current") or ""
    first = next((ln.strip().lstrip("- ") for ln in body.splitlines() if ln.strip()), "")
    return (first[:137] + "…") if len(first) > 140 else first


def render_state(state_path: Path, config: dict | None = None) -> str:
    config = config or {}
    state = load_graph(state_path)
    scratch = Report()
    root = find_root(state, config.get("state_root"), scratch, "state")
    if root is None:
        raise SystemExit("render: cannot identify state root; pass --config")

    project = config.get("project") or root.title.split(" — ")[0].strip() or "project"
    hwm, ts = read_hwm(root)

    children: dict[str, list[Node]] = {}
    for node in state.nodes.values():
        for pid in node.parent_ids:
            children.setdefault(pid, []).append(node)
    for kids in children.values():
        kids.sort(key=lambda n: (n.created_at, n.slug))

    def entry(node: Node) -> str:
        status = node_status(node) or "?"
        line = f"[{status}] **{node.title}** (`{node.ref}`)"
        if summary := summary_line(node):
            line += f" — {summary}"
        return line

    frontier = sorted(
        (n for n in state.nodes.values()
         if n.node_id != root.node_id and (node_status(n) or "") in FRONTIER),
        key=lambda n: (FRONTIER_ORDER[node_status(n)], n.title),
    )

    lines = [
        f"# {project} — State",
        "",
        "> Generated by `tools/hypergraph.py render` from the state-graph export.",
        "> Do not hand-edit — run the hypergraph-reconcile skill instead.",
        "",
        f"Reconciled through `{hwm or 'unknown'}` at {ts or 'unknown'}.",
        "",
        "## Frontier",
        "",
    ]
    if frontier:
        lines += [f"- {entry(n)}" for n in frontier]
    else:
        lines.append("_Nothing on the frontier — all state nodes working or superseded._")
    lines += ["", "## Architecture", "", f"- **{root.title}** (`{root.ref}`)"]

    seen: set[str] = {root.node_id}

    def walk(node_id: str, depth: int) -> None:
        for child in children.get(node_id, []):
            indent = "  " * depth
            if child.node_id in seen:
                lines.append(f"{indent}- [{node_status(child) or '?'}] {child.title} (`{child.ref}`) *(see above)*")
                continue
            seen.add(child.node_id)
            lines.append(f"{indent}- {entry(child)}")
            walk(child.node_id, depth + 1)

    walk(root.node_id, 1)
    lines.append("")
    return "\n".join(lines)


def cmd_render(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output = render_state(args.state, config)
    if args.output:
        Path(args.output).write_text(output)
        print(f"wrote {args.output}")
    else:
        print(output)
    return 0


# --------------------------------------------------------------------------- viz

def kebab(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def layered_layout(graph: Graph) -> dict[str, tuple[int, int]]:
    """Deterministic Sugiyama-lite: longest-path layering + barycenter ordering.

    Returns {node_id: (layer, order-within-layer)}.
    """
    def sort_key(nid: str):
        n = graph.nodes[nid]
        return (n.created_at, n.slug, nid)

    children: dict[str, list[str]] = {}
    indeg: dict[str, int] = {nid: 0 for nid in graph.nodes}
    for node in graph.nodes.values():
        for pid in node.parent_ids:
            if pid in graph.nodes:
                children.setdefault(pid, []).append(node.node_id)
                indeg[node.node_id] += 1

    layer: dict[str, int] = {nid: 0 for nid in graph.nodes}
    queue = sorted((nid for nid, d in indeg.items() if d == 0), key=sort_key)
    topo: list[str] = []
    while queue:
        nid = queue.pop(0)
        topo.append(nid)
        for cid in sorted(children.get(nid, []), key=sort_key):
            layer[cid] = max(layer[cid], layer[nid] + 1)
            indeg[cid] -= 1
            if indeg[cid] == 0:
                queue.append(cid)
    for nid in graph.nodes:  # cycle guard: layer 0, appended in stable order
        if nid not in set(topo):
            topo.append(nid)

    by_layer: dict[int, list[str]] = {}
    for nid in topo:
        by_layer.setdefault(layer[nid], []).append(nid)
    for nids in by_layer.values():
        nids.sort(key=sort_key)
    order = {nid: i for nids in by_layer.values() for i, nid in enumerate(nids)}
    parents = {nid: [p for p in graph.nodes[nid].parent_ids if p in graph.nodes]
               for nid in graph.nodes}

    for sweep in range(4):
        down = sweep % 2 == 0
        for ln in sorted(by_layer, reverse=not down):
            nids = by_layer[ln]

            def barycenter(nid: str) -> float:
                rel = parents[nid] if down else children.get(nid, [])
                vals = [order[r] for r in rel]
                return sum(vals) / len(vals) if vals else float(order[nid])

            nids.sort(key=lambda nid: (barycenter(nid), sort_key(nid)))
            for i, nid in enumerate(nids):
                order[nid] = i

    return {nid: (layer[nid], order[nid]) for nid in graph.nodes}


def state_dfs_order(state: Graph, root: Node) -> list[str]:
    """Pre-order DFS node_ids from the state root (same child sort as render)."""
    children: dict[str, list[Node]] = {}
    for node in state.nodes.values():
        for pid in node.parent_ids:
            children.setdefault(pid, []).append(node)
    for kids in children.values():
        kids.sort(key=lambda n: (n.created_at, n.slug))
    out: list[str] = []
    seen: set[str] = set()

    def walk(nid: str) -> None:
        if nid in seen:
            return
        seen.add(nid)
        out.append(nid)
        for child in children.get(nid, []):
            walk(child.node_id)

    walk(root.node_id)
    for node in sorted(state.nodes.values(), key=lambda n: (n.created_at, n.slug)):
        walk(node.node_id)  # disconnected stragglers still render
    return out


def lane_layout(record: Graph) -> tuple[list[str], dict[str, int]]:
    """`git log --graph` lane assignment over the record graph, in real time order.

    Returns (chronological node_ids, {node_id: lane}). A node continues its earliest
    parent's lane when that lane's tip *is* that parent — that is the only case where
    the edge can be drawn straight without crossing an intervening node. Otherwise it
    opens the lowest lane with no edge still pending through it.

    "Pending" is the load-bearing part. A lane stays reserved while *any* node in it
    still has an unplaced child, not merely while its tip does: a parent whose lane
    was taken over by its first child still owes an edge to its second, and that edge
    has to have somewhere to go. Once a lane owes nothing it is reused, so width stays
    bounded by the number of genuinely concurrent threads (3 on this repo, not 29).
    """
    chrono = [n.node_id for n in sorted(record.nodes.values(),
                                        key=lambda n: (n.created_at, n.slug))]
    index = {nid: i for i, nid in enumerate(chrono)}
    parents = {nid: sorted((p for p in record.nodes[nid].parent_ids if p in record.nodes),
                           key=lambda p: index[p]) for nid in chrono}
    remaining: dict[str, int] = {nid: 0 for nid in chrono}
    for nid in chrono:
        for pid in parents[nid]:
            remaining[pid] += 1

    tips: list[str | None] = []
    pending: list[int] = []          # nodes in this lane that still owe an edge
    lane: dict[str, int] = {}
    for nid in chrono:
        # `p in lane` is not paranoia: a child may carry an earlier timestamp than
        # its parent (a backdated import, a skewed clock), and then the parent has
        # no lane yet. Such an edge simply cannot continue a lane, so it opens a
        # new one — the drawing stays honest and nothing raises.
        take = next((lane[p] for p in parents[nid]
                     if p in lane and tips[lane[p]] == p), None)
        if take is None:
            take = next((i for i, owed in enumerate(pending) if owed == 0), len(pending))
            if take == len(pending):
                tips.append(None)
                pending.append(0)
        tips[take] = nid
        lane[nid] = take
        if remaining[nid]:
            pending[take] += 1
        for pid in parents[nid]:
            remaining[pid] -= 1
            # An unplaced parent never incremented `pending`, because that happens
            # at placement using the count of children still to come.
            if remaining[pid] == 0 and pid in lane:
                pending[lane[pid]] -= 1
    return chrono, lane


def build_viz_data(record: Graph, state: Graph, config: dict | None = None) -> dict:
    """Assemble the JSON payload the viz page consumes: both graphs with
    deterministic layout hints, cross-graph provenance/impact links, HWM flags."""
    config = config or {}
    scratch = Report()
    record_root = find_root(record, config.get("record_root"), scratch, "record")
    state_root = find_root(state, config.get("state_root"), scratch, "state")

    hwm = ts = None
    if state_root is not None:
        hwm, ts = read_hwm(state_root)
    hwm_node = record.by_slug.get(hwm) if hwm and hwm != "none" else None
    cutoff = hwm_node.created if hwm_node else None

    rec_layout = layered_layout(record)
    st_layout = layered_layout(state)
    chrono_order, lanes = lane_layout(record)
    chrono_index = {nid: i for i, nid in enumerate(chrono_order)}
    by_kebab = {kebab(n.title): n for n in state.nodes.values()}
    id_to_slug = {g: {n.node_id: n.ref for n in gr.nodes.values()}
                  for g, gr in (("record", record), ("state", state))}

    links: list[dict] = []
    seen_links: set[tuple[str, str, str]] = set()

    def add_link(rec_slug: str, st_slug: str, kind: str, label: str = "") -> None:
        key = (rec_slug, st_slug, kind)
        if key in seen_links:
            return
        seen_links.add(key)
        links.append({"record": rec_slug, "state": st_slug, "kind": kind, "label": label})

    record_nodes = []
    rec_seq = sorted(record.nodes.values(),
                     key=lambda n: (rec_layout[n.node_id] + (n.created_at, n.slug)))
    for seq, node in enumerate(rec_seq):
        is_root = bool(record_root and node.node_id == record_root.node_id)
        _, sections = split_sections(node.content)
        entries, none_reason, _bad = parse_impacts(sections.get("state impact") or "")
        impacts = []
        for target, delta, is_new in entries:
            resolved = None
            if is_new:
                match = by_kebab.get(target)
                resolved = match.ref if match else None
            elif target in state.by_slug:
                resolved = target
            impacts.append({"target": target, "resolved": resolved, "delta": delta, "new": is_new})
            if resolved:
                add_link(node.ref, resolved, "impact", delta)
        if hwm is None or is_root or (hwm_node and node.node_id == hwm_node.node_id):
            unreconciled = False
        else:
            unreconciled = cutoff is None or (node.created is not None and node.created > cutoff)
        ly, od = rec_layout[node.node_id]
        record_nodes.append({
            "slug": node.ref, "title": node.title, "created_at": node.created_at,
            "parents": [id_to_slug["record"][p] for p in node.parent_ids
                        if p in id_to_slug["record"]],
            "content": node.content, "is_root": is_root,
            "is_hwm": bool(hwm_node and node.node_id == hwm_node.node_id),
            "unreconciled": unreconciled,
            "impacts": impacts, "impact_none": none_reason,
            "layer": ly, "order": od, "seq": seq,
            # timeline view: real chronological rank, and the `git log` lane
            "chrono": chrono_index[node.node_id], "lane": lanes[node.node_id],
        })

    state_nodes = []
    st_seq = (state_dfs_order(state, state_root) if state_root
              else [n.node_id for n in sorted(state.nodes.values(),
                                              key=lambda n: (n.created_at, n.slug))])
    for seq, nid in enumerate(st_seq):
        node = state.nodes[nid]
        is_root = bool(state_root and node.node_id == state_root.node_id)
        _, sections = split_sections(node.content)
        prov_notes: dict[str, str] = {}
        for line in (sections.get("provenance") or "").splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            note = re.split(r"—|--", line, maxsplit=1)
            note = note[1].strip() if len(note) > 1 else ""
            for slug in SLUG_RE.findall(line):
                prov_notes.setdefault(slug, note)
        prov_slugs: list[str] = []
        if not is_root:
            for slug in sorted(set(SLUG_RE.findall(COMMENT_RE.sub("", node.content)))):
                if slug in record.by_slug:
                    add_link(slug, node.ref, "provenance", prov_notes.get(slug, ""))
                    prov_slugs.append(slug)
        status = None if is_root else node_status(node)
        ly, od = st_layout[node.node_id]
        # Board-card facts: how much record work stands behind this claim, and how
        # long ago the newest of it landed. Both answer "is this still current?".
        touched = [record.by_slug[s].created_at for s in prov_slugs
                   if record.by_slug[s].created_at]
        state_nodes.append({
            "slug": node.ref, "title": node.title, "created_at": node.created_at,
            "parents": [id_to_slug["state"][p] for p in node.parent_ids
                        if p in id_to_slug["state"]],
            "content": node.content, "is_root": is_root,
            "status": status, "frontier": bool(status in FRONTIER),
            "layer": ly, "order": od, "seq": seq,
            "prov_count": len(prov_slugs),
            "last_record_at": max(touched) if touched else None,
            "impact_count": sum(1 for l in links
                                if l["state"] == node.ref and l["kind"] == "impact"),
        })

    project = (config.get("project")
               or (state_root.title.split(" — ")[0].strip() if state_root else "")
               or "project")
    return {
        "project": project,
        "record": {"root": record_root.ref if record_root else None, "nodes": record_nodes},
        "state": {"root": state_root.ref if state_root else None, "nodes": state_nodes},
        "links": links,
        "reconciliation": {"high_water_mark": hwm, "reconciled_at": ts},
    }


# The page's light-theme palette, restated here so exported figures and the
# interactive page agree on what "broken" looks like. tests/test_viz.py asserts
# every value below still appears in the bundled template — a palette that drifts
# is worse than no palette, because the two pictures then quietly disagree.
PALETTE = {
    "working": "#0ca30c", "open": "#2a78d6", "broken": "#d03b3b",
    "blocked": "#fab219", "superseded": "#898781",
    "prov": "#2a78d6", "impact": "#eb6834", "hwm": "#4a3aa7", "unrec": "#fab219",
    "ink": "#0b0b0b", "muted": "#898781", "axis": "#c3c2b7",
    "cat": ["#2a78d6", "#eb6834", "#0ca30c", "#4a3aa7", "#c22f7a", "#0b8f8f",
            "#a8790a", "#5f7a2a"],
}


def excaligraph_spec(record: Graph, state: Graph, config: dict | None = None,
                     links: str = "none") -> dict:
    """The graph spec `excaligraph build` consumes (its src/cli/spec.ts schema).

    Two-step by design — `viz --format excaligraph -o g.yaml`, then
    `excaligraph build g.yaml`. Node stays optional and nothing here shells out,
    so the core path keeps working on a machine that has never seen npm.

    `links` is the page's own focus/all idea applied to a static figure, and for
    the same reason: 177 cross-graph edges over 51 nodes is a hairball however it
    is drawn. The default figure is nodes + parent edges + one blob per claim,
    which already tells the whole story — the impact relation *is* the blob
    membership, so drawing it again as edges says nothing new.
    """
    config = config or {}
    data = build_viz_data(record, state, config)
    graph_dir = str(config.get("graph_dir") or DEFAULT_GRAPH_DIR).rstrip("/")

    nodes: dict[str, dict] = {}
    for kind, key in (("record", "record"), ("state", "state")):
        for node in data[key]["nodes"]:
            if key == "state":
                accent = (PALETTE["ink"] if node["is_root"]
                          else PALETTE.get(node["status"] or "", PALETTE["muted"]))
            elif node["is_hwm"]:
                accent = PALETTE["hwm"]
            elif node["unreconciled"]:
                accent = PALETTE["unrec"]
            else:
                accent = PALETTE["ink"] if node["is_root"] else PALETTE["axis"]
            nodes[node["slug"]] = {
                "label": f"{node['title']}\n{node['slug']}",
                "shape": "ellipse" if key == "state" and node["is_root"] else "rectangle",
                "strokeColor": accent,
                "link": f"{graph_dir}/{kind}/{node['slug']}.md",
            }

    edges: list[dict] = []
    for key in ("record", "state"):
        for node in data[key]["nodes"]:
            for parent in node["parents"]:
                edges.append({"from": parent, "to": node["slug"],
                              "strokeColor": PALETTE["axis"]})
    for link in data["links"]:
        impact = link["kind"] == "impact"
        if links != "all" and links != link["kind"]:
            continue
        edge = {
            "from": link["record"] if impact else link["state"],
            "to": link["state"] if impact else link["record"],
            "strokeColor": PALETTE["impact"] if impact else PALETTE["prov"],
            "opacity": 60,
        }
        if impact:
            edge["strokeStyle"] = "dashed"
        # An impact delta is a paragraph. On an edge in a figure it is noise, so
        # labels are cut to a phrase — the full text is in the node file the
        # `link:` on each node points at.
        label = " ".join((link["label"] or "").split())
        if label:
            edge["label"] = label if len(label) <= 60 else label[:59] + "…"
        edges.append(edge)

    # One hyperedge per state node with a declared impact set — the same grouping
    # the page's Clusters view blobs, and the same colour order.
    by_state: dict[str, list[str]] = {}
    for link in data["links"]:
        if link["kind"] == "impact":
            by_state.setdefault(link["state"], []).append(link["record"])
    hyperedges = []
    for node in data["state"]["nodes"]:
        members = by_state.get(node["slug"])
        if not members:
            continue
        color = PALETTE["cat"][len(hyperedges) % len(PALETTE["cat"])]
        hyperedges.append({
            "nodes": members, "label": node["title"], "labelPosition": "top",
            "strokeColor": color, "backgroundColor": color,
        })

    return {
        # Derived from the project name, so a figure regenerated tomorrow has the
        # same hand-drawn jitter as the one in yesterday's paper.
        "seed": int(hashlib.sha256(data["project"].encode()).hexdigest()[:8], 16),
        "layout": {"engine": "dagre", "rankdir": "LR"},
        "defaults": {
            "node": {"shape": "rectangle", "width": 230, "height": 66,
                     "roundness": "round", "fontSize": 16},
            "edge": {"routing": "curved"},
            "hyperedge": {"padding": 16, "corridor": 12, "smoothing": 18,
                          "avoid": True, "clearance": 12, "opacity": 22},
        },
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges,
    }


def render_excaligraph(record_path: Path, state_path: Path,
                       config: dict | None = None, links: str = "none") -> str:
    import yaml  # deferred: PEP 723 dep, only needed for this one output format
    spec = excaligraph_spec(load_graph(record_path), load_graph(state_path),
                            config, links)
    header = ("# Generated by `hypergraph viz --format excaligraph`.\n"
              "# Build it with:  excaligraph build THIS.yaml -o graph.excalidraw\n"
              "#\n"
              "# Each blob is one state node wrapping the record work that declares\n"
              "# impact on it. Cross-graph edges are off by default (--links); every\n"
              "# node carries a `link:` to its markdown source, so the full text of a\n"
              "# claim is one click away in the built scene.\n")
    return header + yaml.safe_dump(spec, sort_keys=False, allow_unicode=True,
                                   default_flow_style=False, width=100)


def _esc_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# The page is authored as separate files under tools/viz/ and concatenated into the
# single VIZ_TEMPLATE constant at build time (tools/bundle_viz.py), which keeps both
# hard properties: this script stays one copyable file, and its output stays
# self-contained. The assembly lives here, not in the bundler, so `viz --dev` (which
# reads the sources straight off disk) can never disagree with the bundled constant.
VIZ_SRC_DIR = Path(__file__).resolve().parent / "viz"
VIZ_PART_RE = re.compile(r"/\*\{\{(?:CSS|JS)\}\}\*/\n")


def assemble_viz_template(viz_dir: Path = VIZ_SRC_DIR) -> str:
    """Concatenate the tools/viz/ sources into the page template.

    Parts join in `manifest.json` order, separated by exactly one blank line —
    trailing newlines in a source file are normalized away, so whether a file ends
    with a blank line can never change the bundle.
    """
    manifest = json.loads((viz_dir / "manifest.json").read_text())

    def join(names: list[str]) -> str:
        return "\n\n".join((viz_dir / p).read_text().rstrip("\n") for p in names) + "\n"

    parts = {"/*{{CSS}}*/\n": join(manifest["css"]), "/*{{JS}}*/\n": join(manifest["js"])}
    return VIZ_PART_RE.sub(lambda m: parts[m.group(0)], (viz_dir / manifest["html"]).read_text())


def viz_payload(record_path: Path, state_path: Path, config: dict | None = None) -> dict:
    data = build_viz_data(load_graph(record_path), load_graph(state_path), config)
    for path, key in ((record_path, "record"), (state_path, "state")):
        try:
            raw = json.loads(Path(path).read_text())
            if isinstance(raw, dict):
                data[key]["exported_at"] = raw.get("exported_at")
        except (OSError, json.JSONDecodeError):
            pass
    return data


def render_viz(record_path: Path, state_path: Path, config: dict | None = None,
               template: str | None = None, live: dict | None = None) -> str:
    data = viz_payload(record_path, state_path, config)
    if live:
        data["live"] = live
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return ((template if template is not None else VIZ_TEMPLATE)
            .replace("__TITLE__", _esc_html(data["project"]))
            .replace("__VIZ_DATA__", payload))


def cmd_viz(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if getattr(args, "format", "html") == "excaligraph":
        output = render_excaligraph(args.record, args.state, config, args.links)
        if args.output:
            Path(args.output).write_text(output)
            print(f"wrote {args.output} — build it with "
                  f"`excaligraph build {args.output} -o graph.excalidraw`")
        else:
            print(output)
        return 0
    template = None
    if getattr(args, "dev", False):
        if not (VIZ_SRC_DIR / "manifest.json").exists():
            print(f"error: --dev needs the viz sources at {VIZ_SRC_DIR}", file=sys.stderr)
            return 2
        template = assemble_viz_template(VIZ_SRC_DIR)

    # --live is the one output that is deliberately not self-contained: the page
    # polls a sibling JSON file. It therefore needs a real path to be a sibling
    # of, and it needs to be served over http (browsers refuse cross-file fetch
    # from file://). Both are said out loud rather than discovered.
    live = None
    if getattr(args, "live", False):
        if not args.output:
            print("error: --live needs -o (it writes a sibling .data.json)",
                  file=sys.stderr)
            return 2
        data_path = Path(args.output).with_suffix(".data.json")
        live = {"url": data_path.name, "interval_ms": args.live_interval * 1000}

    output = render_viz(args.record, args.state, config, template, live)
    if args.output:
        Path(args.output).write_text(output)
        print(f"wrote {args.output}")
        if live:
            data = viz_payload(args.record, args.state, config)
            data_path.write_text(json.dumps(data, separators=(",", ":")))
            print(f"wrote {data_path} — the page polls it every "
                  f"{args.live_interval}s and pulses what is new")
            print(f"serve it: python3 -m http.server -d {data_path.parent or '.'} "
                  "(browsers block fetch from file://)")
    else:
        print(output)
    return 0


# ----------------------------------------------------------------- local backend
# The git-native adapter (backend/local-adapter.md): markdown files under
# .hypergraph/graph/{record,state}/<slug>.md are the source of truth, and `export`
# turns them into exactly the JSON that check/render/viz already consume — so the
# local backend is a drop-in behind backend/INTERFACE.md without touching any of
# the code above. Flywheel, when used, becomes a regenerable mirror.

# uuid5(NAMESPACE_URL, "https://github.com/theo-kirby/hypergraph-protocol"): node ids
# are derived from slugs, so they are reproducible and never depend on randomness.
HYPERGRAPH_NS = uuid.UUID("830284cc-4acf-58ee-a7cc-67d88855cb41")
GRAPH_KINDS = ("record", "state")
# Title of the mirror-only slug-legend node (local↔flywheel slug map). It exists only
# on the mirror — excluded from `import` and `push --verify` by this exact title.
LEGEND_TITLE = "Hypergraph mirror slug legend"
DEFAULT_GRAPH_DIR = Path(".hypergraph/graph")
DEFAULT_CACHE_DIR = Path(".hypergraph/cache")
EXPORT_VERSION = 1
# Above this many creates in one plan, `push --plan` warns: each create is a mirror
# write, so a plan this size is a rate-limit and partial-push risk (not a violation).
PUSH_CREATE_WARN = 200
FM_ORDER = ("node_id", "slug", "title", "created_at", "parents", "summary",
            "origin", "flywheel")

# Two wordlists for slug minting; `adjective-noun-####` matches SLUG_RE, which every
# provenance line, [rec:] citation, impact target and high-water mark depends on.
SLUG_ADJECTIVES = """
amber ancient autumn blue bold brave brisk calm candid careful chilly civic clear
clever cold cool copper crimson crisp curious damp dawn deep dry dusty eager early
easy empty even fair falling fierce first flat floral fond forest fresh frosty gentle
gilded glad golden grand green happy hidden hollow honest humble icy idle jolly keen
kind late lawful lean light little lively lone long loyal lucid lucky mellow merry
mild misty modest morning narrow neat nimble noble northern odd old open pale patient
peaceful placid plain polished proud quiet rapid rare ready red restless rich rising
rough round royal rustic sage salty scarlet shady sharp shy silent silver simple
sleepy slender small smooth snowy soft solar solemn southern spring square staid
steady still stormy strong sunny sweet swift tender terse tidy tiny true twilight
upright vast violet warm wandering weathered western wild windy winter wise witty
young zesty
""".split()
SLUG_NOUNS = """
anchor arbor arrow ash aspen badger banner basin bay beacon bell birch bloom bluff
bramble branch brook cabin canyon cedar chart cliff cloud clover comet cove crane
creek crest crow current dawn delta dew dune dusk eagle ember falcon fern field
fjord flame flint forest fountain fox garden gate glacier glade grove grotto harbor
harvest haven hawk heron hill hollow horizon isle ivy jasper journey key lake lantern
ledge light lily lodge loom marsh meadow mesa mist moon moss mountain nest oak ocean
orchard otter path peak pebble pine pond prairie quartz quill rain raven reef ridge
river road rock rose sail sage sand sea shade shore sky slope snow spark spire spring
star stone stream summit sun tide timber tooth tower trail tree union vale valley
vine walrus water wave willow wind wing wolf wood
""".split()


class LocalGraphError(Exception):
    """Anything wrong with the on-disk graph; the CLI turns these into exit 2."""


@dataclass
class LocalNode:
    """One `.hypergraph/graph/<kind>/<slug>.md` file: frontmatter + verbatim body."""
    kind: str
    path: Path
    meta: dict
    content: str

    @property
    def slug(self) -> str:
        return str(self.meta.get("slug") or "")

    @property
    def node_id(self) -> str:
        return str(self.meta.get("node_id") or "")

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or "")

    @property
    def created_at(self) -> str:
        return str(self.meta.get("created_at") or "")

    @property
    def parents(self) -> list[str]:
        raw = self.meta.get("parents") or []
        return [str(p) for p in (raw if isinstance(raw, list) else [raw])]

    @property
    def sha256(self) -> str:
        return body_sha256(self.content)


def node_id_for(slug: str) -> str:
    return str(uuid.uuid5(HYPERGRAPH_NS, slug))


def body_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def mint_slug(taken: set[str], rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    for _ in range(10000):
        slug = f"{rng.choice(SLUG_ADJECTIVES)}-{rng.choice(SLUG_NOUNS)}-{rng.randrange(10000):04d}"
        if slug not in taken and SLUG_RE.fullmatch(slug):
            return slug
    raise LocalGraphError("could not mint a free slug — the wordlists are exhausted")


# ------------------------------------------------------------- node file plumbing

def split_frontmatter(text: str, where: str = "node file") -> tuple[dict, str]:
    """`---` YAML block then the body. The body is returned byte-for-byte: it *is*
    the node `content` the checker sees, with no transformation anywhere."""
    import yaml

    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise LocalGraphError(f"{where}: file does not start with a `---` frontmatter block")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            meta = yaml.safe_load("\n".join(lines[1:i])) or {}
            if not isinstance(meta, dict):
                raise LocalGraphError(f"{where}: frontmatter is not a YAML mapping")
            return meta, "\n".join(lines[i + 1:])
    raise LocalGraphError(f"{where}: unterminated frontmatter block (no closing `---`)")


def render_node_file(meta: dict, content: str) -> str:
    import yaml

    ordered = {k: meta[k] for k in FM_ORDER if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    # width high enough that no value line-wraps: frontmatter stays greppable
    fm = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True,
                        default_flow_style=False, width=4096).rstrip("\n")
    return f"---\n{fm}\n---\n{content}"


def graph_kind_dir(graph_dir: Path, kind: str) -> Path:
    return Path(graph_dir) / kind


def load_local_nodes(graph_dir: Path, kind: str, missing_ok: bool = False) -> dict[str, LocalNode]:
    """→ {slug: LocalNode} for one graph, with per-file structural validation."""
    directory = graph_kind_dir(graph_dir, kind)
    if not directory.is_dir():
        if missing_ok:
            return {}
        raise LocalGraphError(f"no {kind} graph directory at {directory}")
    nodes: dict[str, LocalNode] = {}
    seen_ids: dict[str, str] = {}
    for path in sorted(directory.glob("*.md")):
        meta, content = split_frontmatter(path.read_text(), str(path))
        node = LocalNode(kind=kind, path=path, meta=meta, content=content)
        if not SLUG_RE.fullmatch(node.slug):
            raise LocalGraphError(
                f"{path}: slug {node.slug!r} is not `adjective-noun-####` — every "
                "provenance pointer in the protocol depends on that shape")
        if path.stem != node.slug:
            raise LocalGraphError(f"{path}: filename does not match frontmatter slug {node.slug!r}")
        if not node.node_id:
            raise LocalGraphError(f"{path}: frontmatter has no `node_id`")
        if node.node_id in seen_ids:
            raise LocalGraphError(
                f"{path}: node_id collides with {seen_ids[node.node_id]}")
        if parse_ts(node.created_at) is None:
            raise LocalGraphError(
                f"{path}: `created_at` missing or not ISO-8601 (got {node.created_at!r}) — "
                "the unreconciled/high-water-mark partition is timestamp-ordered")
        seen_ids[node.node_id] = str(path)
        nodes[node.slug] = node
    return nodes


def local_graph(nodes: dict[str, LocalNode], kind: str) -> Graph:
    """Resolve parent *slugs* to node_ids and build the same Graph load_graph builds."""
    out: dict[str, Node] = {}
    for node in nodes.values():
        parent_ids = []
        for parent in node.parents:
            if parent not in nodes:
                raise LocalGraphError(
                    f"{node.path}: parent slug `{parent}` is not a {kind} node")
            parent_ids.append(nodes[parent].node_id)
        out[node.node_id] = Node(node_id=node.node_id, slug=node.slug, title=node.title,
                                 content=node.content, parent_ids=parent_ids,
                                 created_at=node.created_at)
    return Graph(nodes=out, by_slug={n.slug: n for n in out.values() if n.slug})


def load_local_graph(graph_dir: Path, kind: str, missing_ok: bool = False) -> Graph:
    return local_graph(load_local_nodes(graph_dir, kind, missing_ok), kind)


def topo_order(nodes: dict[str, LocalNode]) -> list[LocalNode]:
    """Parents before children; ties broken by (created_at, slug) for determinism."""
    key = lambda s: (nodes[s].created_at, s)  # noqa: E731
    pending = {s: [p for p in n.parents if p in nodes] for s, n in nodes.items()}
    out: list[LocalNode] = []
    done: set[str] = set()
    while pending:
        ready = sorted((s for s, ps in pending.items() if all(p in done for p in ps)), key=key)
        if not ready:  # cycle guard: emit the rest in stable order rather than hang
            ready = sorted(pending, key=key)
        for slug in ready:
            out.append(nodes[slug])
            done.add(slug)
            pending.pop(slug)
    return out


# ---------------------------------------------------------------- export / import

def export_graph_json(graph_dir: Path, kind: str) -> dict:
    nodes = load_local_nodes(graph_dir, kind)
    graph = local_graph(nodes, kind)  # validates parent references
    records = []
    for slug, node in nodes.items():
        records.append({
            "node_id": node.node_id,
            "slug_name": slug,
            "title": node.title,
            "content": node.content,
            "summary": str(node.meta.get("summary") or ""),
            "parent_ids": graph.nodes[node.node_id].parent_ids,
            "created_at": node.created_at,
        })
    records.sort(key=lambda r: (r["created_at"], r["node_id"]))  # INTERFACE op 8
    return {"version": EXPORT_VERSION, "exported_at": utc_now(), "nodes": records}


def cmd_export(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    out_dir = args.out_dir or Path(config.get("cache_dir") or DEFAULT_CACHE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind in GRAPH_KINDS:
        payload = export_graph_json(graph_dir, kind)
        path = out_dir / f"{kind}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {path} ({len(payload['nodes'])} {kind} node(s))")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    written = skipped = 0
    for kind, path in (("record", args.record), ("state", args.state)):
        if path is None:
            continue
        graph = load_graph(path)
        raw = json.loads(Path(path).read_text())
        extras = {}
        if isinstance(raw, dict):
            for item in raw.get("nodes") or []:
                if isinstance(item, dict) and item.get("node_id"):
                    extras[str(item["node_id"])] = item
        pushed_at = (isinstance(raw, dict) and raw.get("exported_at")) or utc_now()
        directory = graph_kind_dir(graph_dir, kind)
        directory.mkdir(parents=True, exist_ok=True)
        for node in sorted(graph.nodes.values(), key=lambda n: (n.created_at, n.node_id)):
            if node.title == LEGEND_TITLE:
                # mirror-only bookkeeping, never part of the graph proper
                print(f"skipping mirror slug-legend node {node.slug} (mirror-only)")
                skipped += 1
                continue
            if not SLUG_RE.fullmatch(node.slug):
                raise LocalGraphError(
                    f"{path}: node {node.node_id} has slug {node.slug!r}, which is not "
                    "`adjective-noun-####`; the local backend needs it to name the file")
            parents = []
            for pid in node.parent_ids:
                parent = graph.nodes.get(pid)
                if parent is None:
                    raise LocalGraphError(
                        f"{path}: node `{node.slug}` has parent id {pid} that is not in "
                        "the export (re-export with include_descendants from the root)")
                parents.append(parent.slug)
            src = extras.get(node.node_id, {})
            revision = src.get("committed_revision", src.get("revision"))
            meta = {
                "node_id": node.node_id,          # preserved verbatim: no identity drift
                "slug": node.slug,
                "title": node.title,
                "created_at": node.created_at,
                "parents": parents,
                "summary": str(src.get("summary") or ""),
            }
            if args.fork:
                # A fork takes its own mirror identity: the source graph's ids are
                # provenance only (`origin:`), never a push target. With `flywheel:`
                # absent, push plans every node as a create under our own roots.
                origin = {"backend": "flywheel", "node_id": node.node_id,
                          "slug": node.slug}
                if revision is not None:
                    origin["revision"] = revision
                origin["exported_at"] = str(pushed_at)
                meta["origin"] = origin
            else:
                # Re-homing a graph you own: keep mirroring to the same nodes.
                flywheel = {"node_id": node.node_id, "slug": node.slug}
                if revision is not None:
                    flywheel["revision"] = revision
                flywheel["pushed_at"] = str(pushed_at)
                flywheel["content_sha256"] = body_sha256(node.content)
                meta["flywheel"] = flywheel
            text = render_node_file(meta, node.content)
            target = directory / f"{node.slug}.md"
            if target.exists() and not args.force:
                if target.read_text() == text:
                    skipped += 1
                    continue
                raise LocalGraphError(
                    f"{target} exists and differs from the import — pass --force to overwrite")
            target.write_text(text)
            written += 1
    print(f"import: wrote {written} node file(s), {skipped} already up to date "
          f"under {graph_dir}")
    return 0


# ------------------------------------------------------------------- authoring

def read_body(spec: str | None) -> str:
    if spec is None:
        return ""
    if spec == "-":
        return sys.stdin.read()
    return Path(spec).read_text()


def git_repo_context() -> dict[str, str]:
    """Local `git` reads only (no fetch, no remote round-trip)."""
    def run(*argv: str) -> str | None:
        try:
            proc = subprocess.run(["git", *argv], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None

    return {
        "repo": run("config", "--get", "remote.origin.url") or "none",
        "branch": run("rev-parse", "--abbrev-ref", "HEAD") or "none",
        "commit": run("rev-parse", "HEAD") or "none",
    }


def compose_record_content(body: str, impacts: list[str], none_reason: str | None,
                           repo: dict[str, str] | None, is_root: bool) -> str:
    parts: list[str] = []
    if body.strip():
        parts.append(body.strip())
    if repo:
        parts.append("## Repo\n\n"
                     f"- repo: {repo['repo']}\n- branch: {repo['branch']}\n"
                     f"- commit: {repo['commit']}")
    lines = [f"- target: {i}" for i in impacts]
    if none_reason:
        lines.append(f"none: {none_reason}")
    if lines or not is_root:
        parts.append("## State Impact\n\n" + "\n".join(lines))
    return "\n\n".join(parts) + "\n"


def compose_state_content(body: str, status: str, prov: list[str], neg: list[str],
                          hwm: str | None, reconciled_at: str, is_root: bool) -> str:
    if is_root:
        parts = [body.strip()] if body.strip() else []
        parts.append("## Reconciliation\n\n"
                     f"- high_water_mark: {hwm or 'none'}\n"
                     f"- reconciled_at: {reconciled_at}")
        return "\n\n".join(parts) + "\n"
    parts = [f"Status: {status}", "## Current\n\n" + body.strip()]
    parts.append("## Negative knowledge\n\n" + ("\n".join(f"- {n}" for n in neg)
                                                if neg else "None yet."))
    parts.append("## Provenance\n\n" + "\n".join(f"- {p}" for p in prov))
    return "\n\n".join(parts) + "\n"


def _solo_graph(slug: str, title: str, content: str, created_at: str) -> tuple[Node, Graph]:
    node = Node(node_id=node_id_for(slug), slug=slug, title=title, content=content,
                parent_ids=[], created_at=created_at)
    return node, Graph(nodes={node.node_id: node}, by_slug={slug: node})


def validate_node_content(kind: str, slug: str, title: str, content: str, created_at: str,
                          record: Graph, state: Graph, is_root: bool) -> Report:
    """Run the real checker over a single candidate node, before it is written —
    a bad impact target or dangling provenance slug fails at authoring time."""
    report = Report()
    node, solo = _solo_graph(slug, title, content, created_at)
    if kind == "record":
        check_impacts(solo, state, node if is_root else None, report)
    else:
        check_state_nodes(record, solo, node if is_root else None, report)
        if is_root:
            check_hwm(record, solo, None, node, report)
    return report


def _report_and_raise(report: Report, what: str) -> None:
    for finding in report.warnings():  # stderr: stdout is the new node's slug
        print(f"warning   {finding}", file=sys.stderr)
    violations = report.violations()
    if violations:
        detail = "\n".join(f"  VIOLATION {f}" for f in violations)
        raise LocalGraphError(f"{what} would violate the protocol:\n{detail}")


def cmd_new(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    kind = args.kind
    if kind == "state" and not args.reconcile:
        raise LocalGraphError(
            "refusing to write a state node: only hypergraph-reconcile may write state "
            "(SPEC I3). Declare a `## State Impact` on a record node instead; pass "
            "--reconcile only from inside a reconcile pass.")

    existing = {k: load_local_nodes(graph_dir, k, missing_ok=True) for k in GRAPH_KINDS}
    record = local_graph(existing["record"], "record")
    state = local_graph(existing["state"], "state")
    taken = set(existing["record"]) | set(existing["state"])

    parents = list(args.parent or [])
    if not parents and not args.root:
        raise LocalGraphError(
            f"a {kind} node needs at least one causal --parent (or --root for the graph root)")
    if parents and args.root:
        raise LocalGraphError("--root nodes are parentless; drop --parent or --root")
    for parent in parents:
        if parent not in existing[kind]:
            raise LocalGraphError(f"parent `{parent}` is not a {kind} node under {graph_dir}")
    if args.root and existing[kind]:
        roots = [s for s, n in existing[kind].items() if not n.parents]
        if roots:
            raise LocalGraphError(f"the {kind} graph already has a root: {', '.join(roots)}")

    slug = args.slug or mint_slug(taken)
    if not SLUG_RE.fullmatch(slug):
        raise LocalGraphError(f"--slug {slug!r} is not `adjective-noun-####`")
    if slug in taken:
        raise LocalGraphError(f"slug `{slug}` already exists in this project")

    created_at = args.created_at or utc_now()
    if parse_ts(created_at) is None:
        raise LocalGraphError(f"--created-at {created_at!r} is not ISO-8601")
    body = read_body(args.body)

    if kind == "record":
        # anchored to line starts: prose may legitimately mention `## State Impact`
        for heading in ("## State Impact", "## Repo"):
            if heading != "## Repo" or args.repo_auto:
                if re.search(rf"^{re.escape(heading)}\s*$", body, re.M | re.I):
                    raise LocalGraphError(
                        f"--body already contains a `{heading}` heading — the CLI "
                        "generates that section")
        if args.impact and args.none:
            raise LocalGraphError("pass either --impact lines or --none, not both (SPEC I2)")
        if not args.impact and not args.none and not args.root:
            raise LocalGraphError(
                "a record node must declare `## State Impact`: --impact \"<slug> — <delta>\", "
                "--impact \"NEW <kebab-name> — <delta>\", or --none \"<reason>\" (SPEC I2)")
        content = compose_record_content(body, list(args.impact or []), args.none,
                                         git_repo_context() if args.repo_auto else None,
                                         args.root)
    else:
        if not args.root and not args.prov:
            raise LocalGraphError("a state node needs --prov \"<record-slug> — <why>\" (SPEC I4)")
        if not args.root and args.status not in STATUSES:
            raise LocalGraphError(
                f"--status must be one of {', '.join(sorted(STATUSES))} (SPEC I6)")
        if not args.root:
            # the CLI wraps --body in the full template; a pre-scaffolded body would
            # nest a second Status/## Current inside the first, invisibly to `check`
            if STATUS_RE.match(next((ln for ln in body.splitlines() if ln.strip()), "")):
                raise LocalGraphError(
                    "--body already starts with a `Status:` line — pass only the "
                    "`## Current` content; the CLI generates the template around it")
            for heading in ("## Current", "## Negative knowledge", "## Provenance"):
                if re.search(rf"^{re.escape(heading)}\s*$", body, re.M | re.I):
                    raise LocalGraphError(
                        f"--body already contains a `{heading}` heading — the CLI "
                        "generates that section")
        content = compose_state_content(body, args.status or "", list(args.prov or []),
                                        list(args.neg or []), args.hwm, created_at, args.root)

    _report_and_raise(
        validate_node_content(kind, slug, args.title, content, created_at,
                              record, state, args.root),
        f"new {kind} node `{slug}`")

    meta = {
        "node_id": node_id_for(slug),
        "slug": slug,
        "title": args.title,
        "created_at": created_at,
        "parents": parents,
        "summary": args.summary or "",
    }
    directory = graph_kind_dir(graph_dir, kind)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{slug}.md"
    target.write_text(render_node_file(meta, content))
    print(f"{slug}  ({kind})  {target}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    existing = {k: load_local_nodes(graph_dir, k, missing_ok=True) for k in GRAPH_KINDS}
    kinds = [k for k in GRAPH_KINDS if args.slug in existing[k]]
    if not kinds:
        raise LocalGraphError(f"`{args.slug}` is not a node under {graph_dir}")
    kind = kinds[0]
    node = existing[kind][args.slug]

    if args.print_sha:  # the read half of op 7's compare-and-swap
        print(node.sha256)
        return 0
    if kind == "record":
        raise LocalGraphError(
            f"`{args.slug}` is a record node: the record graph is append-only. "
            "Corrections are new child nodes, not edits (SPEC conventions).")
    if not args.reconcile:
        raise LocalGraphError(
            "refusing to write a state node: only hypergraph-reconcile may write state "
            "(SPEC I3). Pass --reconcile only from inside a reconcile pass.")
    if node.sha256 != args.expect:
        raise LocalGraphError(
            f"stale write refused (optimistic lock, INTERFACE op 7): --expect "
            f"{args.expect} but `{args.slug}` is now {node.sha256}. Re-read the node, "
            "re-fold your delta onto the current content, and retry.")

    content = read_body(args.body)
    if not content.endswith("\n"):
        content += "\n"
    record = local_graph(existing["record"], "record")
    state = local_graph(existing["state"], "state")
    is_root = not node.parents
    _report_and_raise(
        validate_node_content("state", node.slug, args.title or node.title, content,
                              node.created_at, record, state, is_root),
        f"update to state node `{args.slug}`")

    meta = dict(node.meta)
    if args.title:
        meta["title"] = args.title
    if args.summary is not None:
        meta["summary"] = args.summary
    node.path.write_text(render_node_file(meta, content))
    print(f"updated {node.path} ({node.sha256[:12]} → {body_sha256(content)[:12]})")
    return 0


# -------------------------------------------------------------- flywheel mirror

def push_plan(graph_dir: Path) -> dict:
    """Diff local files against their `flywheel:` frontmatter → an ordered op list.

    This tool never calls MCP; the skill layer executes the plan and feeds the
    returned ids back via `push --record-result` (backend/local-adapter.md)."""
    ops: list[dict] = []
    violations: list[str] = []
    for kind in GRAPH_KINDS:
        nodes = load_local_nodes(graph_dir, kind, missing_ok=True)
        local_graph(nodes, kind)  # validates parent references before planning writes
        for node in topo_order(nodes):  # parents first: creates are dependency-ordered
            flywheel = node.meta.get("flywheel") or {}
            payload = {
                "graph": kind,
                "slug": node.slug,
                "title": node.title,
                "content": node.content,
                "summary": str(node.meta.get("summary") or ""),
                "content_sha256": node.sha256,
            }
            if not flywheel.get("node_id"):
                parent_fw = []
                for parent in node.parents:
                    pfw = (nodes[parent].meta.get("flywheel") or {}).get("node_id")
                    parent_fw.append(pfw)
                ops.append({**payload, "op": "create", "parent_slugs": node.parents,
                            "parent_flywheel_ids": parent_fw,
                            "created_at": node.created_at})
            elif flywheel.get("content_sha256") != node.sha256:
                if kind == "record":
                    violations.append(
                        f"{node.slug}: record node body changed since it was pushed — the "
                        "record graph is append-only; do not mirror this edit")
                ops.append({**payload, "op": "update",
                            "flywheel_node_id": flywheel.get("node_id"),
                            "flywheel_slug": flywheel.get("slug"),
                            "base_revision": flywheel.get("revision")})
    return {"version": EXPORT_VERSION, "graph_dir": str(graph_dir),
            "generated_at": utc_now(), "ops": ops, "violations": violations}


def _load_export_nodes(path: Path) -> dict[str, dict]:
    """Export JSON → {node_id: raw node dict}, tolerant of the same shapes load_graph eats."""
    data = json.loads(Path(path).read_text())
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    out: dict[str, dict] = {}
    for raw in raw_nodes:
        if isinstance(raw, dict):
            nid = str(raw.get("node_id") or raw.get("id") or "")
            if nid:
                out[nid] = raw
    return out


def verify_mirror(graph_dir: Path, against: Path,
                  exempt_ids: set[str] | None = None) -> Report:
    """Read-only drift check: a fresh mirror export vs the local node files.

    Drift = missing nodes on either side, body-hash or summary mismatches, local
    edits not yet pushed, or revision skew vs `flywheel:` frontmatter. Mirror-only
    structure is exempt by design: the slug-legend node (LEGEND_TITLE) and any
    `exempt_ids` (the config's `mirror_roots`, minted when an adopted project
    mirrors its post-epoch nodes under fresh roots)."""
    report = Report()
    exempt_ids = exempt_ids or set()
    remote = _load_export_nodes(against)
    matched: set[str] = set()
    for kind in GRAPH_KINDS:
        for node in load_local_nodes(graph_dir, kind, missing_ok=True).values():
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
            if body_sha256(str(raw.get("content") or "")) != node.sha256:
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
                or str(raw.get("title") or "") == LEGEND_TITLE:
            continue
        report.add("violation", "mirror", str(raw.get("slug_name") or raw.get("slug") or nid),
                   "mirror node has no local counterpart")
    return report


def legend_content(graph_dir: Path) -> str:
    """Body for the mirror-only slug-legend node, regenerated on every push.

    Never written into any mirrored node (byte-identity is preserved); the skill
    layer commits it as its own node under the mirror's record root."""
    rows = []
    for kind in GRAPH_KINDS:
        for node in load_local_nodes(graph_dir, kind, missing_ok=True).values():
            fw = node.meta.get("flywheel") or {}
            if fw.get("slug") and str(fw["slug"]) != node.slug:
                rows.append(f"| {kind} | {node.slug} | {fw['slug']} |")
    lines = [
        "Mirror-only legend, regenerated on every push. This mirror is a one-way",
        "projection of committed node files; Flywheel mints its own slug on create, so",
        "provenance slugs, [rec: …] citations, impact targets and the high-water mark",
        "written locally may not resolve natively here. Read them through this table.",
        "",
        "For an adopted project this table is also the archive→mirror map: an imported",
        "node keeps its archive slug as its local slug (`origin.slug` in the repo).",
        "",
        "| graph | local slug (authoritative) | mirror slug |",
        "| --- | --- | --- |",
    ]
    lines += sorted(rows) or ["| — | (no diverged slugs) | — |"]
    return "\n".join(lines) + "\n"


def lineage_content(graph_dir: Path, config: dict) -> str:
    """Body for the mirror record root of a forked (adopted) project.

    Names the frozen archive the history came from, and states what did and did
    not travel. Rendered from the config `archive:` block plus a count of the node
    files carrying `origin:`."""
    archive = config.get("archive") or {}
    if not archive:
        raise LocalGraphError(
            "push --lineage needs an `archive:` block in .hypergraph/config.yml "
            "(backend, roots: [slug, node_id, title], artifacts)")
    roots = archive.get("roots") or []
    if not roots:
        raise LocalGraphError("config `archive:` block declares no `roots:`")
    imported = 0
    for kind in GRAPH_KINDS:
        for node in load_local_nodes(graph_dir, kind, missing_ok=True).values():
            if node.meta.get("origin"):
                imported += 1
    if not imported:
        imported = archive.get("imported") or 0
    lines = [
        "This graph continues history that began on another Flywheel graph. That",
        "earlier graph still exists and is frozen: this project never writes to it.",
        "",
        "| archive root | node_id | title |",
        "| --- | --- | --- |",
    ]
    for root in roots:
        if not isinstance(root, dict):
            raise LocalGraphError(f"config `archive.roots` entry is not a mapping: {root!r}")
        title = str(root.get("title") or "—").replace("|", r"\|")
        lines.append(f"| {root.get('slug') or '—'} | {root.get('node_id') or '—'} | "
                     f"{title} |")
    lines += [
        "",
        f"{imported} node(s) were imported verbatim and are re-published here with their",
        "original topology. Each carries its archive identity in `origin:` in the repo.",
        "Flywheel mints a fresh slug on create, so archive slugs do not resolve here —",
        "read them through the slug legend, which doubles as the archive→mirror map.",
        "",
        "Artifacts did not survive the import: the local backend has no artifact",
        "operation. They remain on the archive roots above.",
    ]
    return "\n".join(lines) + "\n"


def apply_push_results(graph_dir: Path, results: object) -> int:
    """Fold Flywheel's returned ids/revisions back into each node's frontmatter."""
    if isinstance(results, dict):
        results = results.get("results", results.get("ops", []))
    if not isinstance(results, list):
        raise LocalGraphError("results file must be a list, or an object with a `results` list")
    nodes = {}
    for kind in GRAPH_KINDS:
        for slug, node in load_local_nodes(graph_dir, kind, missing_ok=True).items():
            nodes[slug] = node
    applied = 0
    for entry in results:
        if not isinstance(entry, dict):
            raise LocalGraphError(f"unexpected result entry: {entry!r}")
        slug = str(entry.get("slug") or entry.get("local_slug") or "")
        node = nodes.get(slug)
        if node is None:
            raise LocalGraphError(f"result names `{slug}`, which is not a local node")
        source = entry.get("flywheel") if isinstance(entry.get("flywheel"), dict) else entry
        fw = dict(node.meta.get("flywheel") or {})
        for key, aliases in (("node_id", ("node_id", "flywheel_node_id")),
                             ("slug", ("slug_name", "flywheel_slug")),
                             ("revision", ("revision", "committed_revision"))):
            for alias in aliases:
                if source.get(alias) is not None:
                    fw[key] = source[alias]
                    break
        if not fw.get("node_id"):
            raise LocalGraphError(f"result for `{slug}` carries no Flywheel node_id")
        fw["pushed_at"] = str(entry.get("pushed_at") or utc_now())
        fw["content_sha256"] = str(entry.get("content_sha256") or node.sha256)
        meta = dict(node.meta)
        meta["flywheel"] = fw
        node.path.write_text(render_node_file(meta, node.content))
        applied += 1
    return applied


def skills_data_root() -> Path:
    """Where the shipped skills live: `hypergraph_protocol_data/` next to the module
    (installed wheel) or the repo root (running tools/hypergraph.py directly)."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "hypergraph_protocol_data", here.parent):
        if (candidate / "skills").is_dir():
            return candidate
    raise LocalGraphError(
        "cannot locate the packaged skills (no hypergraph_protocol_data/ beside the "
        "module and no skills/ in the parent directory)")


def cmd_skills(args: argparse.Namespace) -> int:
    root = skills_data_root()
    if args.target:
        target = Path(args.target)
    elif args.user:
        target = Path.home() / ".claude" / "skills"
    else:
        target = Path.cwd() / ".claude" / "skills"
    target.mkdir(parents=True, exist_ok=True)
    installed = []
    for src in sorted((root / "skills").glob("hypergraph-*")):
        if not src.is_dir():
            continue
        dst = target / src.name
        if dst.is_symlink():  # e.g. a dev install.sh link — don't write through it
            dst.unlink()
        # symlinked references/ entries are materialized as real files on copy,
        # so the installed skill is self-contained
        shutil.copytree(src, dst, dirs_exist_ok=True)
        installed.append(src.name)
    if not installed:
        raise LocalGraphError(f"no hypergraph-* skills found under {root / 'skills'}")
    for name in installed:
        print(f"installed {target / name}")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    if args.record_result:
        count = apply_push_results(graph_dir, json.loads(Path(args.record_result).read_text()))
        print(f"push: stamped Flywheel identity onto {count} node file(s)")
        return 0
    if args.verify:
        if not args.against:
            raise LocalGraphError("push --verify needs --against <flywheel-export.json>")
        exempt = {str(v.get("node_id"))
                  for v in (config.get("mirror_roots") or {}).values()
                  if isinstance(v, dict) and v.get("node_id")}
        report = verify_mirror(graph_dir, args.against, exempt)
        for f in report.violations():
            print(f"DRIFT {f}")
        print(f"\npush --verify: {len(report.violations())} drift finding(s)")
        return 1 if report.violations() else 0
    if args.legend:
        text = legend_content(graph_dir)
        if args.output:
            Path(args.output).write_text(text)
            print(f"wrote {args.output}")
        else:
            print(text, end="")
        return 0
    if args.lineage:
        text = lineage_content(graph_dir, config)
        if args.output:
            Path(args.output).write_text(text)
            print(f"wrote {args.output}")
        else:
            print(text, end="")
        return 0
    plan = push_plan(graph_dir)
    text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text)
        print(f"wrote {args.output}")
    else:
        print(text, end="")
    creates = sum(1 for o in plan["ops"] if o["op"] == "create")
    print(f"push plan: {creates} create(s), {len(plan['ops']) - creates} update(s)",
          file=sys.stderr)
    if creates > PUSH_CREATE_WARN:
        print(f"WARNING {creates} creates is one mirror write each — expect rate limits "
              f"(429 backoff) and record results in batches so a partial run stays "
              f"resumable. To mirror less history, split the adoption epoch later so "
              f"fewer nodes are imported (SPEC: Adoption epochs).", file=sys.stderr)
    for violation in plan["violations"]:
        print(f"VIOLATION {violation}", file=sys.stderr)
    return 1 if plan["violations"] else 0


# Self-contained page: no network requests, no JS dependencies. All SVG styling is
# via attributes (not CSS classes) so the "Download SVG" export is standalone.
# --- BEGIN GENERATED VIZ TEMPLATE ---
# Generated from tools/viz/ by tools/bundle_viz.py — do not edit in place.
# Edit the sources and re-run the bundler.
VIZ_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — hypergraph</title>
<style>
  * { box-sizing: border-box; margin: 0; }
  html, body { height: 100%; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         display: flex; flex-direction: column; overflow: hidden;
         background: var(--page); color: var(--ink); }
  body[data-theme=light] { color-scheme: light;
    --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --border:rgba(11,11,11,.10); --accent:#2a78d6; --code:#f0efec; }
  body[data-theme=dark] { color-scheme: dark;
    --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --border:rgba(255,255,255,.10); --accent:#3987e5; --code:#262624; }
  header { display:flex; align-items:center; gap:6px; padding:8px 14px; flex:none;
           background:var(--surface); }
  header h1 { font-size:14px; font-weight:650; white-space:nowrap; margin-right:auto; }
  header h1 span { color:var(--muted); font-weight:500; }
  /* live indicator: present only when `viz --live` built the page */
  #live { display:flex; align-items:center; gap:6px; font-size:11px;
          color:var(--ink2); padding:3px 9px; border-radius:999px;
          border:1px solid var(--grid); margin-right:4px; white-space:nowrap; }
  #live[hidden] { display:none; }
  #live i { width:7px; height:7px; border-radius:50%; background:var(--muted); }
  #live[data-tone=ok] i { background:#0ca30c; }
  #live[data-tone=new] i { background:var(--accent); }
  #live[data-tone=warn] i { background:#fab219; }
  .iconbtn { display:flex; align-items:center; justify-content:center; width:30px;
             height:30px; border:0; border-radius:8px; background:transparent;
             color:var(--ink2); cursor:pointer; padding:0; }
  .iconbtn:hover { background:var(--page); color:var(--ink); }
  .iconbtn svg { width:16px; height:16px; fill:none; stroke:currentColor;
                 stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
  body[data-theme=light] #themeBtn .moon { display:none; }
  body[data-theme=dark] #themeBtn .sun { display:none; }
  #exportWrap { position:relative; }
  #exportMenu { position:absolute; right:0; top:34px; z-index:10; min-width:150px;
                background:var(--surface); border:1px solid var(--grid);
                border-radius:8px; padding:4px; box-shadow:0 4px 14px var(--border); }
  #exportMenu[hidden] { display:none; }
  #exportMenu button { display:block; width:100%; text-align:left; border:0;
                       background:transparent; color:var(--ink2); font:inherit;
                       font-size:12.5px; padding:6px 10px; border-radius:6px;
                       cursor:pointer; white-space:nowrap; }
  #exportMenu button:hover { background:var(--page); color:var(--ink); }
  main { flex:1; display:flex; min-height:0; background:var(--surface); }
  #canvas { flex:1; position:relative; min-width:0; background:var(--page);
            border-top-right-radius:10px; overflow:hidden; }
  #svg { position:absolute; inset:0; width:100%; height:100%; display:block;
         cursor:grab; }
  #svg.dragging { cursor:grabbing; }
  #divider { width:7px; flex:none; cursor:col-resize; background:var(--surface);
             display:flex; align-items:center; justify-content:center; }
  #divider svg { width:14px; height:14px; flex:none; color:var(--muted);
                 fill:none; stroke:currentColor; stroke-width:2;
                 stroke-linecap:round; stroke-linejoin:round; pointer-events:none; }
  #divider.collapsed svg { transform:scaleX(-1); }
  #side { width:400px; flex:none; display:flex; flex-direction:column; min-width:0;
          background:var(--surface); overflow:hidden; }
  #controls { flex:none; padding:12px 18px; border-bottom:1px solid var(--grid); }
  #search { width:100%; font:inherit; font-size:12.5px; padding:5px 10px;
            border-radius:8px; border:1px solid var(--grid); background:var(--page);
            color:var(--ink); outline:none; }
  #search:focus { border-color:var(--accent); }
  #presets { display:flex; gap:6px; margin-top:10px; }
  #presets button { flex:1; border:1px solid var(--grid); background:transparent;
                    color:var(--ink2); font:inherit; font-size:12px; padding:4px 0;
                    border-radius:999px; cursor:pointer; white-space:nowrap; }
  #presets button:hover { color:var(--ink); border-color:var(--muted); }
  #presets button.active { background:var(--page); color:var(--ink);
                           font-weight:600; border-color:var(--muted); }
  #toggles { margin-top:12px; display:flex; flex-direction:column; gap:8px; }
  .seg { display:flex; align-items:center; gap:8px; }
  .seg[hidden] { display:none; }  /* layout-specific controls — see syncControls */
  .seg .lbl { font-size:10.5px; text-transform:uppercase; letter-spacing:.05em;
              color:var(--muted); width:48px; flex:none; }
  .seg .opts { display:flex; flex:1; background:var(--page);
               border:1px solid var(--grid); border-radius:8px; padding:2px; }
  .seg .opts button { flex:1; border:0; background:transparent; color:var(--ink2);
                      font:inherit; font-size:12px; padding:3px 0; border-radius:6px;
                      cursor:pointer; }
  .seg .opts button.active { background:var(--surface); color:var(--ink);
                             font-weight:600; box-shadow:0 0 0 1px var(--border); }
  .checks { display:flex; flex-wrap:wrap; gap:4px 14px; margin-top:2px; }
  .checks label { display:inline-flex; align-items:center; gap:6px; font-size:12px;
                  color:var(--ink2); cursor:pointer; white-space:nowrap; }
  .checks label.off { opacity:.45; }
  .checks input { accent-color:var(--accent); margin:0; }
  #panel { flex:1; overflow-y:auto; padding:16px 18px;
           font-size:13px; line-height:1.55; }
  #panel h2 { font-size:14.5px; line-height:1.35; margin-bottom:6px; }
  #panel h3 { font-size:11px; text-transform:uppercase; letter-spacing:.06em;
              color:var(--muted); margin:18px 0 6px; }
  #panel .chips { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 4px; }
  .chip { display:inline-flex; align-items:center; gap:5px; font-size:11px;
          padding:2px 8px; border-radius:999px; border:1px solid var(--grid);
          color:var(--ink2); white-space:nowrap; }
  .chip .dot { width:7px; height:7px; border-radius:50%; flex:none; }
  .slugchip { font-family:ui-monospace, SFMono-Regular, Menlo, monospace;
              font-size:11px; color:var(--muted); }
  #panel .meta { color:var(--muted); font-size:11.5px; margin-bottom:2px; }
  #panel ul.links { list-style:none; padding:0; }
  #panel ul.links li { padding:4px 0; border-bottom:1px solid var(--grid); }
  #panel ul.links li:last-child { border-bottom:0; }
  #panel ul.links .note { color:var(--muted); font-size:11.5px; display:block; }
  a.slug { color:var(--accent); text-decoration:none; cursor:pointer;
           font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:12px;
           border-bottom:1px dotted var(--accent); }
  .content { margin-top:4px; }
  .content h4 { font-size:12px; margin:14px 0 4px; color:var(--ink); }
  .content p { margin:6px 0; color:var(--ink2); }
  .content ul { margin:4px 0 8px 18px; color:var(--ink2); }
  .content li { margin:3px 0; }
  .content code { font-family:ui-monospace, SFMono-Regular, Menlo, monospace;
                  font-size:11.5px; background:var(--code); padding:1px 4px;
                  border-radius:4px; }
  button.act { font:inherit; font-size:12px; margin-top:8px; padding:4px 12px;
               border-radius:8px; border:1px solid var(--grid); cursor:pointer;
               background:var(--page); color:var(--ink2); }
  button.act:hover { color:var(--ink); border-color:var(--muted); }
  .legend-swatch { display:inline-block; width:22px; height:0; border-top-width:2px;
                   border-top-style:solid; vertical-align:middle; margin-right:8px; }
  .hint { color:var(--muted); font-size:11.5px; margin-top:16px; }
  .stats td { padding:1px 10px 1px 0; color:var(--ink2); font-size:12px; }
  .stats td:first-child { color:var(--muted); }
  @media print {
    header, #side, #divider { display:none !important; }
    body { background:#fff; }
    #canvas { position:fixed; inset:0; border-radius:0; }
  }
</style>
</head>
<body>
<header>
  <h1>__TITLE__ <span>· hypergraph</span></h1>
  <div id="live" hidden title="This page is polling a sibling data file"><i></i><span>live</span></div>
  <button class="iconbtn" id="fitBtn" title="Fit graph to window">
    <svg viewBox="0 0 24 24"><path d="M9 3H5a2 2 0 0 0-2 2v4M15 3h4a2 2 0 0 1 2 2v4M9 21H5a2 2 0 0 1-2-2v-4M15 21h4a2 2 0 0 0 2-2v-4"/></svg>
  </button>
  <button class="iconbtn" id="themeBtn" title="Toggle light/dark">
    <svg class="sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
    <svg class="moon" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>
  </button>
  <div id="exportWrap">
    <button class="iconbtn" id="exportBtn" title="Export">
      <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
    </button>
    <div id="exportMenu" hidden>
      <button id="svgBtn">Download SVG</button>
      <button id="printBtn">Print / PDF</button>
    </div>
  </div>
</header>
<main>
  <div id="canvas"><svg id="svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
  <div id="divider" title="Drag to resize · click to collapse">
    <svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>
  </div>
  <aside id="side">
    <div id="controls">
      <input id="search" type="search" placeholder="Filter: slug, title, content…">
      <div id="presets">
        <button data-preset="timeline" title="What happened, in order">Timeline</button>
        <button data-preset="frontier" title="What is true now, and what is open">Frontier</button>
        <button data-preset="provenance" title="Which record work each state claim rests on">Provenance</button>
        <button data-preset="clusters" title="Which work belongs to the same claim">Clusters</button>
      </div>
      <div id="toggles">
        <div class="seg" data-key="graphs">
          <span class="lbl">Graphs</span>
          <div class="opts">
            <button data-val="record">Record</button>
            <button data-val="state">State</button>
            <button data-val="both">Both</button>
          </div>
        </div>
        <div class="seg" data-key="style">
          <span class="lbl">Nodes</span>
          <div class="opts">
            <button data-val="cards">Cards</button>
            <button data-val="circles">Circles</button>
          </div>
        </div>
        <div class="seg" data-key="layout">
          <span class="lbl">Layout</span>
          <div class="opts">
            <button data-val="timeline" title="Record graph as git-log lanes">Lanes</button>
            <button data-val="board" title="State graph as a status board">Board</button>
            <button data-val="layered">Layered</button>
            <button data-val="force">Force</button>
          </div>
        </div>
        <div class="seg" data-key="xaxis" hidden>
          <span class="lbl">X axis</span>
          <div class="opts">
            <button data-val="rank" title="One step per node — even spacing">Rank</button>
            <button data-val="time" title="Real dates, long idle gaps compressed">Time</button>
          </div>
        </div>
        <div class="seg" data-key="board" hidden>
          <span class="lbl">Board</span>
          <div class="opts">
            <button data-val="status" title="Columns by status, frontier first">Status</button>
            <button data-val="tree" title="Architecture tree, as in STATE.md">Tree</button>
          </div>
        </div>
        <div class="seg" data-key="window" hidden>
          <span class="lbl">Window</span>
          <div class="opts">
            <button data-val="all">All</button>
            <button data-val="250">250</button>
            <button data-val="100">100</button>
            <button data-val="50">50</button>
          </div>
        </div>
        <div class="seg" data-key="links" hidden>
          <span class="lbl">Links</span>
          <div class="opts">
            <button data-val="focus" title="Only the selected or hovered node's links">Focus</button>
            <button data-val="all" title="All of them, bundled into ribbons per claim">All</button>
            <button data-val="none" title="None">None</button>
          </div>
        </div>
        <div class="checks">
          <label><input type="checkbox" data-key="tree">Parent edges</label>
          <label><input type="checkbox" data-key="impact">Impact links</label>
          <label><input type="checkbox" data-key="prov">Provenance links</label>
          <label><input type="checkbox" data-key="blobs">Hyperedge blobs</label>
        </div>
      </div>
    </div>
    <div id="panel"></div>
  </aside>
</main>
<script>
// One inline block, wrapped so the page leaks nothing into the global scope.
// Parts are concatenated by tools/bundle_viz.py; see tools/viz/manifest.json.
(function () {
"use strict";
const DATA = __VIZ_DATA__;

const THEMES = {
  light: { surface:"#fcfcfb", page:"#f9f9f7", ink:"#0b0b0b", ink2:"#52514e",
    muted:"#898781", grid:"#e1e0d9", axis:"#c3c2b7", border:"rgba(11,11,11,0.10)",
    status:{ working:"#0ca30c", open:"#2a78d6", broken:"#d03b3b",
             blocked:"#fab219", superseded:"#898781" },
    prov:"#2a78d6", impact:"#eb6834", hwm:"#4a3aa7", unrec:"#fab219",
    cat:["#2a78d6","#eb6834","#0ca30c","#4a3aa7","#c22f7a","#0b8f8f",
         "#a8790a","#5f7a2a"] },
  dark: { surface:"#1a1a19", page:"#0d0d0d", ink:"#ffffff", ink2:"#c3c2b7",
    muted:"#898781", grid:"#2c2c2a", axis:"#383835", border:"rgba(255,255,255,0.10)",
    status:{ working:"#0ca30c", open:"#3987e5", broken:"#d03b3b",
             blocked:"#fab219", superseded:"#898781" },
    prov:"#3987e5", impact:"#d95926", hwm:"#9085e9", unrec:"#fab219",
    cat:["#3987e5","#f0784a","#33bb33","#9085e9","#e05a9b","#33b8b8",
         "#d9a521","#8fae4a"] },
};
const SVGNS = "http://www.w3.org/2000/svg";
const NW = 236, NH = 62;
const R = 16, BPAD = 18;  // circle style: circle radius, blob hull padding
// Timeline chips: deliberately small, because 39 of them sit side by side along
// one time axis. The full title is one click away in the panel.
const CW = 158, CH = 26, LANE_H = 42, RANK_STEP = CW + 16;
const BW = 232, BH = 78, BCOL = BW + 26, BROW = BH + 12;  // frontier board cards
// Nothing may fit below this. Shrinking past it trades "you can see everything"
// for "you can read nothing" — the view scrolls instead.
const MIN_FIT = 0.45, MAX_FIT = 1.25;
const PUCK_R = 30;  // a collapsed hyperedge, drawn as one body
// Level of detail. Secondary lines go first, then all node text: below these a
// card is a coloured box, which is still a useful shape at a glance.
const DETAIL_MIN_ZOOM = 0.58, TEXT_MIN_ZOOM = 0.34;
// How many of the most recent record nodes each time window keeps.
const WINDOWS = { all: Infinity, "250": 250, "100": 100, "50": 50 };
const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";
const SLUG_JS = /\b[a-z][a-z0-9]*-[a-z][a-z0-9]*-[0-9]{4}\b/g;

const bySlug = {};
DATA.record.nodes.forEach(n => bySlug[n.slug] = { graph: "record", node: n });
DATA.state.nodes.forEach(n => bySlug[n.slug] = { graph: "state", node: n });

// Display state: one unified view driven by toggles. The four views below are
// named after the job they do; any custom mix of toggles is equally valid.
const show = {
  graphs: "record",   // "record" | "state" | "both"
  style:  "circles",  // "cards" | "circles"
  layout: "force",    // "timeline" | "board" | "layered" | "force"
  xaxis:  "rank",     // timeline only: "rank" (even) | "time" (real dates)
  board:  "status",   // board only: "status" columns | "tree" architecture
  window: "all",      // record graph: "all" or the most recent N by chrono
  links:  "focus",    // cross-graph links: "focus" | "all" | "none"
  tree:   true,       // intra-graph parent edges
  impact: false,      // include impact links among the cross-graph ones
  prov:   false,      // include provenance links among them (needs graphs both)
  blobs:  true,       // hyperedge blobs (needs the record graph visible)
};
const recVis = () => show.graphs !== "state";
const stVis  = () => show.graphs !== "record";
// Two layouts are about one graph each and say so: picking Lanes means you want
// the record graph, picking Board means you want the state graph.
const LAYOUT_GRAPH = { timeline: "record", board: "state" };
// Which segmented controls apply to the current layout; the rest stay hidden
// rather than dimmed, so the panel only ever offers real choices.
const SEG_FOR_LAYOUT = { xaxis: ["timeline"], board: ["board"] };
function segHidden(key) {
  if (key === "links") return show.graphs !== "both";
  // A time window only means something when there is enough history to hide.
  if (key === "window") return !recVis() || DATA.record.nodes.length <= 60;
  const only = SEG_FOR_LAYOUT[key];
  return !!only && only.indexOf(show.layout) < 0;
}
// Pan/zoom + node positions are cached per layout signature; edge/blob toggles
// deliberately excluded so flipping a checkbox never resets pan or drag state.
const layoutKey = () => [show.layout, show.graphs, show.style, show.xaxis,
                         show.board, show.window,
                         [...collapsed].sort().join(",")].join(":");

// Hyperedges collapsed to a single puck. Held here rather than in `show` because
// it is a set of slugs, and because it belongs to the graph rather than to the
// display mode — collapsing survives a change of view.
const collapsed = new Set();
const PUCK = "puck:";
const puckKey = state => PUCK + state;
const isPuck = slug => slug.startsWith(PUCK);
const puckState = slug => slug.slice(PUCK.length);

// A puck stands in for its whole hyperedge, so it answers to the state node's
// text: search finds it, and the panel opens the claim itself.
function registerPucks() {
  hyperedges().list.forEach(h => {
    const st = bySlug[h.state];
    if (!st) return;
    bySlug[puckKey(h.state)] = { graph: "puck", state: h.state, node: {
      slug: puckKey(h.state), title: st.node.title, content: st.node.content,
      parents: [], members: h.members.length } };
  });
}

// Four views, each named after its job. Timeline = what happened, in order.
// Frontier = what is true now, and what is open. Provenance = which record work
// each state claim rests on. Clusters = which work belongs to the same claim.
const PRESETS = {
  timeline:   { graphs:"record", style:"cards",   layout:"timeline",
                xaxis:"rank", board:"status", links:"focus", window:"all",
                tree:true, impact:false, prov:false, blobs:false },
  frontier:   { graphs:"state",  style:"cards",   layout:"board",
                xaxis:"rank", board:"status", links:"focus", window:"all",
                tree:false, impact:false, prov:false, blobs:false },
  provenance: { graphs:"both",   style:"cards",   layout:"layered",
                xaxis:"rank", board:"status", links:"focus", window:"all",
                tree:true, impact:true,  prov:true,  blobs:false },
  clusters:   { graphs:"record", style:"circles", layout:"force",
                xaxis:"rank", board:"status", links:"focus", window:"all",
                tree:true, impact:false, prov:false, blobs:true },
};
// Pre-rename deep links keep working: #record #state #combo #combination #hyper.
const VIEW_ALIASES = { record:"timeline", state:"frontier", combo:"provenance",
                       combination:"provenance", hyper:"clusters" };
// Node shape follows the layout, not only the Nodes toggle: the timeline draws
// compact chips and the board draws status cards, because those two layouts exist
// precisely to show what a generic card cannot.
function styleFor(entry) {
  if (entry.graph === "puck") return "puck";
  if (show.layout === "timeline" && entry.graph === "record") return "chip";
  if (show.layout === "board" && entry.graph === "state") return "board";
  return show.style === "circles" ? "circle" : "card";
}
function dimsFor(entry) {
  switch (styleFor(entry)) {
    case "puck":   return { w: PUCK_R * 2, h: PUCK_R * 2 };
    case "chip":   return { w: CW, h: CH };
    case "board":  return { w: BW, h: BH };
    case "circle": return { w: 2 * R, h: 2 * R };
    default:       return { w: NW, h: NH };
  }
}
function dimsOf(slug) { return dimsFor(bySlug[slug]); }

function activePreset() {
  for (const name in PRESETS) {
    const p = PRESETS[name];
    if (Object.keys(show).every(k => show[k] === p[k])) return name;
  }
  return null;
}

let theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
let selected = null, query = "";
const tf = {}, positions = {}, fitDone = {};
function posFor() {
  const k = layoutKey();
  if (!positions[k]) positions[k] = computeLayout();
  return positions[k];
}
function tfFor() {
  const k = layoutKey();
  return tf[k] || (tf[k] = { x: 0, y: 0, k: 1 });
}
let nodeEls = {}, edgeEls = [], edges = [];

const svg = document.getElementById("svg");
const panel = document.getElementById("panel");

function el(name, attrs, text) {
  const e = document.createElementNS(SVGNS, name);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  return e;
}
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function trunc(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function T() { return THEMES[theme]; }

// ------------------------------------------------------------------ layout
// Hyperedges: one per state node targeted by >=1 impact link, in DATA.state
// order (stable color assignment). memberOf maps record slug -> [state slug].
let _hyper = null;
function hyperedges() {
  if (_hyper) return _hyper;
  const byState = {};
  DATA.links.forEach(l => {
    if (l.kind === "impact")
      (byState[l.state] = byState[l.state] || new Set()).add(l.record);
  });
  const list = [], memberOf = {}, index = {};
  DATA.state.nodes.forEach(n => {
    const set = byState[n.slug];
    if (!set) return;
    const members = DATA.record.nodes.filter(r => set.has(r.slug)).map(r => r.slug);
    if (!members.length) return;
    members.forEach(m => (memberOf[m] = memberOf[m] || []).push(n.slug));
    const h = { state: n.slug, members, ci: list.length };
    list.push(h);
    index[n.slug] = h;
  });
  _hyper = { list, memberOf, index };
  return _hyper;
}

// FNV-1a hash of a slug -> [0,1). Deterministic jitter source so the force
// layout is identical on every load (no randomness anywhere in this page).
function hashSlug(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h / 4294967296;
}

// ---------------------------------------------------------------- quadtree
// Barnes-Hut. The pairwise repulsion loop is the only thing on this page that
// scales badly: at 500 nodes it is 240 ticks x 125,000 pairs = 30 million
// distance computations before the first paint. A quadtree collapses every
// distant clump of nodes into one body, which turns the tick from O(n^2) into
// O(n log n) and leaves the near field — the part that actually shapes the
// drawing — computed exactly.
//
// Deterministic, like everything else here: the tree is built in a fixed order
// and walked with an explicit stack, so the same input gives the same forces.

const QT_THETA = 0.9;      // cell size / distance below this: treat as one body
const QT_MAX_DEPTH = 20;   // coincident points would subdivide forever otherwise

function qtCell(x, y, size) {
  return { x, y, size, mass: 0, sx: 0, sy: 0, cx: 0, cy: 0,
           slug: null, px: 0, py: 0, kids: null };
}

function qtPlace(c, slug, x, y, depth) {
  const h = c.size / 2;
  const i = (x >= c.x + h ? 1 : 0) + (y >= c.y + h ? 2 : 0);
  const kid = c.kids[i] ||
    (c.kids[i] = qtCell(c.x + ((i & 1) ? h : 0), c.y + ((i & 2) ? h : 0), h));
  qtInsert(kid, slug, x, y, depth + 1);
}

function qtInsert(c, slug, x, y, depth) {
  c.mass += 1; c.sx += x; c.sy += y;
  c.cx = c.sx / c.mass; c.cy = c.sy / c.mass;
  if (c.mass === 1) { c.slug = slug; c.px = x; c.py = y; return; }
  if (depth >= QT_MAX_DEPTH) return;   // give up subdividing; the cell lumps them
  if (!c.kids) {
    c.kids = [null, null, null, null];
    if (c.slug !== null) { qtPlace(c, c.slug, c.px, c.py, depth); c.slug = null; }
  }
  qtPlace(c, slug, x, y, depth);
}

function quadtree(slugs, pos) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const s of slugs) {
    const p = pos[s];
    if (!p) continue;
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  if (!isFinite(minX)) return null;
  const size = Math.max(maxX - minX, maxY - minY, 1) * 1.05;
  const root = qtCell(minX, minY, size);
  for (const s of slugs) if (pos[s]) qtInsert(root, s, pos[s].x, pos[s].y, 0);
  return root;
}

// Repulsion on one node, accumulated into `f`. Same law as the exact loop —
// min(cap, strength / d^2) — so tuning carries over unchanged; a lumped cell
// simply contributes its own mass times that.
function qtRepulsion(root, slug, x, y, strength, cap, f) {
  if (!root) return;
  const stack = [root];
  while (stack.length) {
    const c = stack.pop();
    if (!c || !c.mass) continue;
    const single = c.kids === null && c.mass === 1;
    if (single && c.slug === slug) continue;
    let dx = x - c.cx, dy = y - c.cy, d2 = dx * dx + dy * dy;
    if (d2 < 1e-4) {  // coincident: deterministic symmetry break, as before
      const ang = hashSlug(slug + (c.slug || "cell")) * 6.283185307;
      dx = Math.cos(ang); dy = Math.sin(ang); d2 = 1;
    }
    if (!single && c.kids && c.size * c.size >= QT_THETA * QT_THETA * d2) {
      for (let i = 0; i < 4; i++) if (c.kids[i]) stack.push(c.kids[i]);
      continue;
    }
    const d = Math.sqrt(d2);
    const rep = Math.min(cap, strength / d2) * (single ? 1 : c.mass);
    f.x += (dx / d) * rep;
    f.y += (dy / d) * rep;
  }
}

// ------------------------------------------------------------ spatial hash
// A uniform grid over the same points. Cheaper than a tree when the query is
// "what is near this box?" rather than "what is the aggregate force here?" —
// which is what card de-overlap and blob avoidance both ask.
function gridHash(items, cellSize) {
  const buckets = new Map();
  const key = (i, j) => i + "," + j;
  items.forEach(it => {
    const i0 = Math.floor(it.minX / cellSize), i1 = Math.floor(it.maxX / cellSize);
    const j0 = Math.floor(it.minY / cellSize), j1 = Math.floor(it.maxY / cellSize);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const k = key(i, j);
      const bucket = buckets.get(k);
      if (bucket) bucket.push(it); else buckets.set(k, [it]);
    }
  });
  return {
    cellSize,
    near(minX, minY, maxX, maxY) {
      const out = new Set();
      const i0 = Math.floor(minX / cellSize), i1 = Math.floor(maxX / cellSize);
      const j0 = Math.floor(minY / cellSize), j1 = Math.floor(maxY / cellSize);
      for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
        const bucket = buckets.get(key(i, j));
        if (bucket) bucket.forEach(it => out.add(it));
      }
      return out;
    },
  };
}

// ---------------------------------------------------------------- timeline
// The record graph is a timeline with a few concurrent threads, not a DAG to be
// ranked: on this repo it is 29 layers deep and 3 wide, which a layered layout
// renders as a 1:15 ribbon. Here time runs along x and `git log` lanes stack
// along y, so the same 39 nodes read as a wide strip at full size.
//
// Lanes come from the payload (hypergraph.py: lane_layout), so they are computed
// once, deterministically, from the real parent relation.

const MIN_STEP = Math.round(RANK_STEP * 0.35);   // "time" mode: idle gaps compress
const MAX_STEP = RANK_STEP * 3;                  // …and busy days still separate

function recordChrono() {
  return DATA.record.nodes.slice().sort((a, b) => a.chrono - b.chrono);
}

// x per record node. "rank" gives every node the same slice of width; "time"
// spaces them by real elapsed time with both ends clamped, so a three-week idle
// gap does not push the next month off screen and a busy hour is still legible.
function timelineX(nodes) {
  const x = {};
  if (show.xaxis === "rank") {
    nodes.forEach(n => x[n.slug] = n.chrono * RANK_STEP);
    return x;
  }
  const ms = nodes.map(n => Date.parse(n.created_at || "") || 0);
  const gaps = [];
  for (let i = 1; i < ms.length; i++) gaps.push(Math.max(0, ms[i] - ms[i - 1]));
  const sorted = gaps.slice().sort((a, b) => a - b);
  const median = sorted.length ? sorted[sorted.length >> 1] : 0;
  const perMs = RANK_STEP / Math.max(1, median);   // median gap ≈ one rank step
  let at = 0;
  nodes.forEach((n, i) => {
    if (i) at += Math.min(MAX_STEP, Math.max(MIN_STEP, (ms[i] - ms[i - 1]) * perMs));
    x[n.slug] = Math.round(at);
  });
  return x;
}

function layoutTimeline(pos) {
  const nodes = recordChrono();
  const x = timelineX(nodes);
  nodes.forEach(n => pos[n.slug] = { x: x[n.slug], y: n.lane * LANE_H });
  if (stVis()) {  // state visible alongside: a plain column past the strip
    const right = Math.max(0, ...nodes.map(n => x[n.slug])) + CW / 2 + 120 + NW / 2;
    DATA.state.nodes.forEach(n => pos[n.slug] = { x: right, y: n.seq * (NH + 22) });
  }
  return pos;
}

// Furniture drawn behind the chips: lane rules, a date gutter, and the
// high-water mark. Everything is derived from `pos`, so dragging a chip does not
// invalidate it.
function timelineFurniture(pos) {
  const nodes = recordChrono().filter(n => pos[n.slug]);
  if (!nodes.length) return null;
  const xs = nodes.map(n => pos[n.slug].x);
  const x0 = Math.min(...xs) - CW / 2 - 24, x1 = Math.max(...xs) + CW / 2 + 24;
  const laneCount = Math.max(...nodes.map(n => n.lane)) + 1;

  const ticks = [];           // one label per new calendar day, at its first node
  let lastDay = null;
  nodes.forEach(n => {
    const day = (n.created_at || "").slice(0, 10);
    if (!day || day === lastDay) return;
    lastDay = day;
    ticks.push({ x: pos[n.slug].x, day, label: day.slice(5) });
  });

  const hwm = DATA.reconciliation.high_water_mark;
  const hwmX = hwm && pos[hwm] ? pos[hwm].x + CW / 2 + 8 : null;
  return { x0, x1, laneCount, ticks, hwmX,
           top: -LANE_H, bottom: (laneCount - 1) * LANE_H + LANE_H };
}

// ------------------------------------------------------------------- board
// The state graph is a status board, not a graph. Twelve nodes at depth 2 drawn
// as a tree is a flat bar in an empty screen — and it is the view that carries
// the frontier, which is the first thing an arriving reader needs.
//
// Columns run broken | blocked | open | working | superseded: the three frontier
// statuses first, because "what is broken or waiting" outranks "what is fine".
// An empty column is kept and labelled 0 — "nothing is broken" is a real answer.

const BOARD_COLUMNS = ["broken", "blocked", "open", "working", "superseded"];
// Positions are card *centres*, so the first row must clear the header band.
const BOARD_HEAD = 0;                    // header text baseline
const BOARD_TOP = BH / 2 + 18;           // first card's centre
const TREE_INDENT = 34;
// An empty column collapses to a rail instead of vanishing. "Nothing is broken"
// still gets said, and the five statuses stop costing 1290px of width when only
// two of them hold anything.
const RAIL_W = 52, RAIL_GAP = 12;

function boardCards() {
  return DATA.state.nodes.filter(n => !n.is_root);
}
function boardRoot() {
  return DATA.state.nodes.find(n => n.is_root) || null;
}

// Freshest first inside a column: `last_record_at` is the newest record node
// cited as this claim's provenance, so the column reads newest work downward.
function boardColumnOrder(a, b) {
  const at = a.last_record_at || "", bt = b.last_record_at || "";
  if (at !== bt) return at < bt ? 1 : -1;
  return a.seq - b.seq;
}

function boardGroups() {
  const groups = {};
  BOARD_COLUMNS.forEach(s => groups[s] = []);
  boardCards().forEach(n => (groups[n.status] || (groups[n.status] = [])).push(n));
  BOARD_COLUMNS.forEach(s => groups[s].sort(boardColumnOrder));
  return groups;
}

// Column geometry: x and width per status, wide when populated, a rail when not.
function boardColumns() {
  const groups = boardGroups();
  let x = 0;
  return BOARD_COLUMNS.map(status => {
    const count = groups[status].length;
    const w = count ? BW : RAIL_W;
    const col = { status, count, nodes: groups[status], x, w, rail: !count };
    x += w + (count ? BCOL - BW : RAIL_GAP);
    return col;
  });
}

function layoutBoard(pos) {
  const root = boardRoot();
  if (show.board === "tree") {
    // Mirrors STATE.md's Architecture section: pre-order DFS (`seq`) with the
    // graph depth (`layer`) as indentation.
    DATA.state.nodes.forEach(n => pos[n.slug] = {
      x: n.layer * TREE_INDENT + BW / 2,
      y: n.seq * (BH + 10),
    });
  } else {
    const cols = boardColumns();
    cols.forEach(col => col.nodes.forEach((n, row) => pos[n.slug] = {
      x: col.x + BW / 2,
      y: BOARD_TOP + row * BROW,
    }));
    const last = cols[cols.length - 1];
    if (root) pos[root.slug] = {   // the root is a caption, not a column item
      x: (cols[0].x + last.x + last.w) / 2,
      y: BOARD_HEAD - 26 - BH / 2,
    };
  }
  if (recVis()) {  // record visible alongside: a chronological column to the left
    const left = -BCOL - NW / 2 - 40;
    recordChrono().forEach(n => pos[n.slug] = { x: left, y: n.chrono * (NH + 16) });
  }
  return pos;
}

// Column headers, drawn only in status mode. Counts come from the same grouping
// the layout used, so a header can never disagree with its column.
function boardFurniture() {
  if (show.board !== "status") return null;
  const columns = boardColumns();
  const rows = Math.max(1, ...columns.map(c => c.count));
  return { columns, headerY: BOARD_HEAD,
           height: BOARD_TOP + (rows - 1) * BROW + BH / 2 + 14 };
}

// x offset of the state column in the layered two-column arrangement; also
// anchors the column header texts.
function comboStateX() { return show.style === "cards" ? NW + 430 : 300; }

// Order for the state column: the mean chronological position of the record
// work each claim rests on. This is the barycentre sweep `layered_layout` runs
// within one graph, applied *across* the two — a claim built from early work
// sits beside early work, which is the cheapest way to cut crossings without
// hiding a single link.
//
// Claims with no provenance keep their architecture order, pinned to the top so
// the state root stays where a reader expects it.
function stateColumnOrder() {
  const chrono = {};
  DATA.record.nodes.forEach(n => chrono[n.slug] = n.chrono);
  const acc = {};
  DATA.links.forEach(l => {
    if (chrono[l.record] == null) return;
    (acc[l.state] = acc[l.state] || []).push(chrono[l.record]);
  });
  const bary = n => {
    if (n.is_root) return -2;           // the root is an anchor, not a claim
    const xs = acc[n.slug];
    if (!xs || !xs.length) return -1;   // unlinked: keep it above the rest
    return xs.reduce((a, b) => a + b, 0) / xs.length;
  };
  return DATA.state.nodes.slice()
    .sort((a, b) => bary(a) - bary(b) || a.seq - b.seq);
}

// The record graph outgrows the screen long before it outgrows the format: at 500
// nodes the timeline is 87,000px wide. A window keeps the most recent N by
// chronological rank and drops the rest from the layout entirely, so the world
// shrinks rather than merely being scrolled past.
function windowedOut(pos) {
  const keep = WINDOWS[show.window];
  if (!isFinite(keep)) return;
  const cutoff = DATA.record.nodes.length - keep;
  if (cutoff <= 0) return;
  DATA.record.nodes.forEach(n => { if (n.chrono < cutoff) delete pos[n.slug]; });
}

// A collapsed hyperedge is replaced by one puck at the centre of its members.
// A member cited by another, still-expanded claim stays visible — it belongs to
// that one too, and hiding it would misreport the other blob.
function collapseOut(pos) {
  if (!collapsed.size) return;
  const H = hyperedges();
  collapsed.forEach(state => {
    const h = H.index[state];
    if (!h) return;
    let x = 0, y = 0, n = 0;
    h.members.forEach(m => { const p = pos[m]; if (p) { x += p.x; y += p.y; n++; } });
    if (!n) return;
    pos[puckKey(state)] = { x: x / n, y: y / n };
  });
  collapsed.forEach(state => {
    const h = H.index[state];
    if (!h) return;
    h.members.forEach(m => {
      const owners = H.memberOf[m] || [];
      if (owners.every(st => collapsed.has(st))) delete pos[m];
    });
  });
}

function computeLayout() {
  const pos = finishLayout(rawLayout());
  return pos;
}

function finishLayout(pos) {
  windowedOut(pos);
  collapseOut(pos);
  return pos;
}

function rawLayout() {
  const pos = {};
  const cards = show.style === "cards";
  if (show.layout === "timeline") {
    return layoutTimeline(pos);
  } else if (show.layout === "board") {
    return layoutBoard(pos);
  } else if (show.layout === "layered") {
    if (show.graphs === "both") {  // two chronological columns
      const sx = comboStateX();
      const rStep = cards ? NH + 30 : 44, sStep = cards ? NH + 46 : 44;
      // The record column runs in real time order, so "further down" means
      // "later" and the state column's barycentre is measured against something
      // a reader can actually see.
      DATA.record.nodes.forEach(n => pos[n.slug] = { x: 0, y: n.chrono * rStep });
      stateColumnOrder().forEach((n, i) => pos[n.slug] = { x: sx, y: i * sStep });
    } else {                       // single graph: centered layer grid
      const g = show.graphs;
      const dx = cards ? NW + 70 : 76, dy = cards ? NH + 78 : 84;
      const perLayer = {};
      DATA[g].nodes.forEach(n => (perLayer[n.layer] = perLayer[n.layer] || []).push(n));
      DATA[g].nodes.forEach(n => {
        const width = perLayer[n.layer].length;
        pos[n.slug] = { x: (n.order - (width - 1) / 2) * dx, y: n.layer * dy };
      });
    }
  } else {                         // force: two-level cluster sim, deterministic
    layoutForce(pos);
    if (cards) {  // sim runs in circle metric; stretch, then separate any
      for (const s in pos) { pos[s].x *= 3.2; pos[s].y *= 1.8; }
      separateCards(pos);
    }
  }
  return pos;
}

// Push overlapping cards apart. This used to be 40 passes over every pair, which
// at 500 nodes is 5 million comparisons per pass. A card can only overlap another
// within one card's distance, so a uniform grid keyed on card size answers "which
// cards are near this one?" directly and the pass becomes linear in practice.
// Slug order stays the iteration order, so the result is unchanged in kind and
// still deterministic.
function separateCards(pos) {
  const slugs = Object.keys(pos);   // insertion order: deterministic
  const mw = NW + 24, mh = NH + 24;
  for (let pass = 0; pass < 40; pass++) {
    const grid = gridHash(slugs.map(s => ({
      slug: s, minX: pos[s].x - mw / 2, maxX: pos[s].x + mw / 2,
      minY: pos[s].y - mh / 2, maxY: pos[s].y + mh / 2,
    })), Math.max(mw, mh));
    let any = false;
    for (const slug of slugs) {
      const a = pos[slug];
      for (const other of grid.near(a.x - mw, a.y - mh, a.x + mw, a.y + mh)) {
        if (other.slug <= slug) continue;   // each pair once, in slug order
        const b = pos[other.slug];
        const ox = mw - Math.abs(a.x - b.x), oy = mh - Math.abs(a.y - b.y);
        if (ox <= 0 || oy <= 0) continue;   // cards clear of each other
        any = true;
        if (ox * mh < oy * mw) {            // push apart along the cheaper axis
          const s = (a.x <= b.x ? -1 : 1) * ox / 2;
          a.x += s; b.x -= s;
        } else {
          const s = (a.y <= b.y ? -1 : 1) * oy / 2;
          a.y += s; b.y -= s;
        }
      }
    }
    if (!any) break;
  }
}

// ------------------------------------------------------------------- force
// The Clusters view asks one question: which record work belongs to the same
// state claim? A single flat force sim answers it badly — every node repels
// every other equally, so twelve hyperedges settle into one overlapping pile and
// the blobs on top of them become mush.
//
// So the layout runs at two levels. First the *hyperedges* are laid out as a
// coarse graph of twelve bodies, each with a radius set by its member count,
// pushed apart until they no longer overlap and pulled together when they share
// members. Only then do nodes settle, each held near the centre of the
// hyperedge(s) it belongs to. Group separation is decided by the level that
// knows about groups, which is what makes it hold.

const CLUSTER_GAP = 34;        // clear space demanded between two hyperedges
const CLUSTER_TICKS = 260, NODE_TICKS = 240;
// Below this the exact pairwise loop is cheaper than building a tree per tick,
// and it stays as the reference the approximation is tested against.
const BH_MIN_NODES = 120;

// FNV-1a -> [0,1): the page's only source of jitter, and it is a pure
// function of the slug — so every load lays out identically.
function hashSlug(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h / 4294967296;
}

// Radius a hyperedge needs to hold its members without crowding them.
function clusterRadius(h) {
  return 40 + 26 * Math.sqrt(Math.max(1, h.members.length));
}

// Coarse layout over the hyperedges themselves. Seeded on a ring ordered by
// size (biggest first) so the result is reproducible and the large clusters,
// which have the least freedom, claim their space first.
function clusterCentres() {
  const list = hyperedges().list;
  if (!list.length) return {};
  const order = list.slice().sort((a, b) => b.members.length - a.members.length ||
                                            (a.state < b.state ? -1 : 1));
  const radius = {}, centre = {};
  order.forEach((h, i) => {
    radius[h.state] = clusterRadius(h);
    const angle = (i / order.length) * 6.283185307 + hashSlug(h.state) * 0.4;
    const ring = 60 + 46 * Math.sqrt(order.length) * (0.7 + 0.3 * (i / order.length));
    centre[h.state] = { x: Math.cos(angle) * ring, y: Math.sin(angle) * ring };
  });

  // Shared members pull two hyperedges together; overlap pushes them apart.
  const shared = [];
  for (let i = 0; i < order.length; i++) {
    const mi = new Set(order[i].members);
    for (let j = i + 1; j < order.length; j++) {
      const n = order[j].members.reduce((c, m) => c + (mi.has(m) ? 1 : 0), 0);
      if (n) shared.push([order[i].state, order[j].state, n]);
    }
  }

  for (let t = 0; t < CLUSTER_TICKS; t++) {
    const alpha = 1 - t / CLUSTER_TICKS;
    shared.forEach(([a, b, n]) => {
      const pa = centre[a], pb = centre[b];
      const dx = pb.x - pa.x, dy = pb.y - pa.y;
      const d = Math.hypot(dx, dy) || 1;
      const rest = radius[a] + radius[b] + CLUSTER_GAP;
      const pull = Math.min(0.06, 0.012 * n) * (d - rest) / d * alpha;
      pa.x += dx * pull; pa.y += dy * pull;
      pb.x -= dx * pull; pb.y -= dy * pull;
    });
    for (let i = 0; i < order.length; i++) {
      for (let j = i + 1; j < order.length; j++) {
        const a = order[i].state, b = order[j].state;
        const pa = centre[a], pb = centre[b];
        let dx = pb.x - pa.x, dy = pb.y - pa.y;
        let d = Math.hypot(dx, dy);
        if (d < 1e-3) {  // coincident: deterministic symmetry break
          const ang = hashSlug(a + b) * 6.283185307;
          dx = Math.cos(ang); dy = Math.sin(ang); d = 1;
        }
        const want = radius[a] + radius[b] + CLUSTER_GAP;
        if (d >= want) continue;
        const push = ((want - d) / d) * 0.5;
        pa.x -= dx * push; pa.y -= dy * push;
        pb.x += dx * push; pb.y += dy * push;
      }
    }
    order.forEach(h => {  // mild centering keeps the whole board near the origin
      centre[h.state].x *= 1 - 0.004 * alpha;
      centre[h.state].y *= 1 - 0.004 * alpha;
    });
  }
  return { centre, radius };
}

// Where a node wants to sit: the centre of its hyperedge, or the mean of them
// when it belongs to several — a node cited by two claims belongs between them.
function nodeHomes(centres) {
  const H = hyperedges(), homes = {};
  DATA.record.nodes.forEach(n => {
    const owners = (H.memberOf[n.slug] || []).filter(st => centres.centre[st]);
    if (!owners.length) return;
    let x = 0, y = 0;
    owners.forEach(st => { x += centres.centre[st].x; y += centres.centre[st].y; });
    homes[n.slug] = { x: x / owners.length, y: y / owners.length,
                      // a node shared by two clusters is held less tightly by
                      // either, so it can sit in the overlap rather than fight
                      weight: owners.length > 1 ? 0.10 : 0.22 };
  });
  return homes;
}

const REPULSION = 20000, REPULSION_CAP = 30;

function simTick(pos, nodes, springs, homes, alpha) {
  const f = {};
  nodes.forEach(s => f[s] = { x: 0, y: 0 });
  // Repulsion through a Barnes-Hut tree: exact near, lumped far. Below the
  // crossover the tree costs more than it saves, so small graphs keep the plain
  // pairwise loop — which is also the reference the tree is checked against.
  if (nodes.length >= BH_MIN_NODES) {
    const tree = quadtree(nodes, pos);
    nodes.forEach(s => qtRepulsion(tree, s, pos[s].x, pos[s].y,
                                   REPULSION, REPULSION_CAP, f[s]));
  } else {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = pos[nodes[i]], b = pos[nodes[j]];
        let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
        if (d2 < 1e-4) {  // coincident: deterministic symmetry break
          const ang = hashSlug(nodes[i] + nodes[j]) * 6.283185307;
          dx = Math.cos(ang); dy = Math.sin(ang); d2 = 1;
        }
        const d = Math.sqrt(d2), rep = Math.min(REPULSION_CAP, REPULSION / d2);
        const ux = dx / d, uy = dy / d;
        f[nodes[i]].x += ux * rep; f[nodes[i]].y += uy * rep;
        f[nodes[j]].x -= ux * rep; f[nodes[j]].y -= uy * rep;
      }
    }
  }
  springs.forEach(sp => {                           // [from, to, k, rest]
    const a = pos[sp[0]], b = pos[sp[1]];
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const k = sp[2] * (d - sp[3]) / d;
    f[sp[0]].x += dx * k; f[sp[0]].y += dy * k;
    f[sp[1]].x -= dx * k; f[sp[1]].y -= dy * k;
  });
  nodes.forEach(s => {                              // home pull + integrate
    const home = homes[s];
    if (home) {
      f[s].x += (home.x - pos[s].x) * home.weight;
      f[s].y += (home.y - pos[s].y) * home.weight;
    } else {
      f[s].x -= pos[s].x * 0.005;
      f[s].y -= pos[s].y * 0.005;
    }
    pos[s].x += f[s].x * alpha;
    pos[s].y += f[s].y * alpha;
  });
}

// Springs come from graph *structure* (parent edges + cross-links), never from
// the edge display toggles, so the layout is stable under checkbox flips.
// Node iteration order is DATA array order (record then state): deterministic.
function runSim(pos, homes) {
  const nodes = [];
  const springs = [];
  // Parent edges pull only weakly here: in this view the grouping is the
  // message, and a strong causal chain would drag members out of their blob.
  const tree = g => DATA[g].nodes.forEach(n => {
    if (!pos[n.slug]) return;
    nodes.push(n.slug);
    n.parents.forEach(p => { if (pos[p]) springs.push([p, n.slug, 0.012, 120]); });
  });
  if (recVis()) tree("record");
  if (stVis()) tree("state");
  if (recVis() && stVis()) DATA.links.forEach(l => {
    if (pos[l.record] && pos[l.state])
      springs.push([l.record, l.state, 0.012, 170]);
  });
  let alpha = 1.0;
  for (let t = 0; t < NODE_TICKS; t++) {
    simTick(pos, nodes, springs, homes || {}, alpha);
    alpha *= 0.985;
  }
}

// Seed members on a ring inside their cluster, in a deterministic order, so the
// sim starts already grouped and only has to relax rather than to discover.
function seedClustered(pos, centres, homes) {
  const H = hyperedges();
  const seen = {};
  H.list.forEach(h => {
    const c = centres.centre[h.state];
    if (!c) return;
    const r = centres.radius[h.state] * 0.72, n = Math.max(1, h.members.length);
    h.members.forEach((m, i) => {
      if (seen[m] || !bySlug[m]) return;
      seen[m] = true;
      // Sunflower packing: even area coverage, so a big cluster stays compact
      // instead of stringing its members around one wide ring.
      const a = i * 2.399963229728653 + hashSlug(h.state) * 6.283185307;
      const rad = r * Math.sqrt((i + 0.5) / n);
      pos[m] = { x: c.x + Math.cos(a) * rad, y: c.y + Math.sin(a) * rad };
    });
  });
  let loose = 0;
  DATA.record.nodes.forEach(n => {   // nodes no claim ever cited, on the outside
    if (pos[n.slug] || !recVis()) return;
    const a = (loose++ / 8) * 6.283185307;
    const ring = 40 + 30 * Math.sqrt(DATA.record.nodes.length);
    pos[n.slug] = { x: Math.cos(a) * ring * 1.9, y: Math.sin(a) * ring * 1.9 };
  });
  if (stVis()) DATA.state.nodes.forEach(n => {  // a state node sits in its blob
    const c = centres.centre[n.slug];
    pos[n.slug] = c ? { x: c.x, y: c.y - centres.radius[n.slug] * 0.25 }
                    : { x: (hashSlug(n.slug) - 0.5) * 300, y: -420 };
    if (c) homes[n.slug] = { x: c.x, y: c.y, weight: 0.18 };
  });
}

function layoutForce(pos) {
  const centres = clusterCentres();
  if (!centres.centre) {   // no hyperedges: plain seeded sim
    let maxOrder = 0;
    if (recVis()) DATA.record.nodes.forEach(n => {
      maxOrder = Math.max(maxOrder, n.order);
      pos[n.slug] = { x: n.order * 80 + (hashSlug(n.slug) - 0.5) * 8,
                      y: n.layer * 80 + (hashSlug(n.slug + "y") - 0.5) * 8 };
    });
    if (stVis()) DATA.state.nodes.forEach(n => pos[n.slug] = {
      x: (maxOrder + 3) * 80 + n.order * 80 + (hashSlug(n.slug) - 0.5) * 8,
      y: n.layer * 80 + (hashSlug(n.slug + "y") - 0.5) * 8 });
    runSim(pos, {});
    return pos;
  }
  const homes = nodeHomes(centres);
  seedClustered(pos, centres, homes);
  if (!recVis()) for (const s in pos) if (bySlug[s].graph === "record") delete pos[s];
  runSim(pos, homes);
  return pos;
}

// ------------------------------------------------------------------- blobs
// Organic outlines around a set of nodes: the geometry behind a hyperedge.
//
// The signed-distance-field half of this file is ported from the excaligraph
// project (src/geometry/blob.ts, MIT licence) and condensed for the browser.
// The algorithm, its parameter names and its commentary are that project's; the
// bugs in the transcription are ours. No URL here on purpose — this page must
// stay self-contained, and a test asserts it fetches nothing.
//
// A hyperedge joins many nodes at once, so an arrow will not do — we fill a blob
// that contains every member. A convex hull will not do either: the hull of
// three far-apart nodes swallows everything between them, member or not. So:
//
//   1. every member contributes its own signed distance, pushed out by `padding`;
//   2. a band of half-width `corridor` runs along a minimum spanning tree of the
//      member centres, so far-apart members stay one connected blob;
//   3. the pieces join with a *smooth* minimum, so two close members bulge into
//      one body instead of showing a seam;
//   4. every non-member is subtracted, so the boundary bends around a node that
//      happens to sit in the way.
//
// Then the zero contour comes out by marching squares, gets simplified, and is
// drawn as a closed curve. It is plain arithmetic on a fixed grid: same input,
// same points, every time — which is the rule this page is held to anyway.

// Tuned for this page's scale (nodes are 32px circles or ~160-240px cards).
const BLOB = { padding: 15, corridor: 10, smoothing: 18, clearance: 11,
               resolution: 5, tolerance: 1.4, maxPoints: 220 };
const BLOB_MAX_SAMPLES = 60000;   // per blob; coarsen rather than stall
// Total grid samples one render may spend across *all* blobs. 12 blobs still get
// the full 60k each; 59 blobs get 12k each and coarsen instead of taking seven
// seconds. Sampling was 98% of the first paint at 500 nodes.
const BLOB_SAMPLE_BUDGET = 720000;
// A tile of the sampling grid. Everything further than its own influence radius
// from a tile cannot change the field inside it, so each tile samples a pruned
// set — see traceContour.
const BLOB_TILE = 24;
// Below this zoom the field's detail is invisible anyway, so the cheap hull is
// the honest choice; it is also what a drag uses, to keep the frame rate.
const BLOB_FIELD_MIN_ZOOM = 0.3;

// ------------------------------------------------------- fast fallback: hull
// Andrew's monotone chain; deterministic sort. Colinear inputs collapse to
// the two extreme points (capsule fallback in blobPath).
function convexHull(pts) {
  const p = pts.slice().sort((a, b) => a.x - b.x || a.y - b.y);
  if (p.length < 3) return p;
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const half = seq => {
    const out = [];
    for (const pt of seq) {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], pt) <= 0)
        out.pop();
      out.push(pt);
    }
    out.pop();
    return out;
  };
  return half(p).concat(half(p.slice().reverse()));
}

// A member contributes its whole box to the hull, so the outline wraps chips,
// cards and circles alike — the shape depends on the layout, not on one toggle.
function memberOutline(slug, pos) {
  const p = pos[slug];
  if (!p) return [];
  if (styleFor(bySlug[slug]) === "circle") return [p];
  const d = dimsOf(slug);
  return [{ x: p.x - d.w / 2, y: p.y - d.h / 2 }, { x: p.x + d.w / 2, y: p.y - d.h / 2 },
          { x: p.x - d.w / 2, y: p.y + d.h / 2 }, { x: p.x + d.w / 2, y: p.y + d.h / 2 }];
}

function blobPath(members, pos) {
  const circles = show.style === "circles";
  const RB = circles ? R + BPAD : BPAD;
  const pts = members.flatMap(s => memberOutline(s, pos));
  if (!pts.length) return null;
  if (pts.length === 1) {
    const p = pts[0];
    return `M ${p.x - RB} ${p.y} a ${RB} ${RB} 0 1 0 ${2 * RB} 0` +
           ` a ${RB} ${RB} 0 1 0 ${-2 * RB} 0 Z`;
  }
  const hull = convexHull(pts);
  if (hull.length < 3) {  // 2 members, or all colinear: capsule
    const a = hull[0], b = hull[hull.length - 1];
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const nx = -dy / d * RB, ny = dx / d * RB;
    return `M ${a.x + nx} ${a.y + ny}` +
           ` A ${RB} ${RB} 0 0 1 ${a.x - nx} ${a.y - ny}` +
           ` L ${b.x - nx} ${b.y - ny}` +
           ` A ${RB} ${RB} 0 0 1 ${b.x + nx} ${b.y + ny} Z`;
  }
  let cx = 0, cy = 0;
  hull.forEach(p => { cx += p.x; cy += p.y; });
  cx /= hull.length; cy /= hull.length;
  const ex = hull.map(p => {  // pad: push vertices out radially from centroid
    const dx = p.x - cx, dy = p.y - cy;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    return { x: p.x + dx / d * RB, y: p.y + dy / d * RB };
  });
  return closedCurve(ex.map(p => [p.x, p.y]));
}

// Closed Catmull-Rom through the loop, as cubic Beziers.
function closedCurve(loop) {
  const n = loop.length;
  if (n < 3) return null;
  let d = `M ${loop[0][0]} ${loop[0][1]}`;
  for (let i = 0; i < n; i++) {
    const p0 = loop[(i + n - 1) % n], p1 = loop[i];
    const p2 = loop[(i + 1) % n], p3 = loop[(i + 2) % n];
    d += ` C ${p1[0] + (p2[0] - p0[0]) / 6} ${p1[1] + (p2[1] - p0[1]) / 6},` +
         ` ${p2[0] - (p3[0] - p1[0]) / 6} ${p2[1] - (p3[1] - p1[1]) / 6},` +
         ` ${p2[0]} ${p2[1]}`;
  }
  return d + " Z";
}

// ------------------------------------------------- signed distance functions
// Each returns 0 on the outline, negative inside and positive outside, in px.
// Subtracting a constant grows the shape by that much and rounds its corners,
// which is exactly what `padding` should do.
function sdRectangle(px, py, b) {
  const dx = Math.abs(px - (b.x + b.width / 2)) - b.width / 2;
  const dy = Math.abs(py - (b.y + b.height / 2)) - b.height / 2;
  return Math.hypot(Math.max(dx, 0), Math.max(dy, 0)) + Math.min(Math.max(dx, dy), 0);
}

// Exact for a circle. For a stretched ellipse it reads a little short along the
// long axis, which errs toward a tighter blob, never a looser one.
function sdEllipse(px, py, b) {
  const hw = Math.max(b.width / 2, 1e-6), hh = Math.max(b.height / 2, 1e-6);
  const norm = Math.hypot((px - (b.x + hw)) / hw, (py - (b.y + hh)) / hh);
  return (norm - 1) * Math.min(hw, hh);
}

function sdShape(s, px, py) {
  return s.shape === "ellipse" ? sdEllipse(px, py, s.box) : sdRectangle(px, py, s.box);
}

// Distance to a line segment. The corridor band is this, minus its half-width.
function sdSegment(px, py, a, b) {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const wx = px - a[0], wy = py - a[1];
  const len2 = vx * vx + vy * vy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, (wx * vx + wy * vy) / len2));
  return Math.hypot(wx - vx * t, wy - vy * t);
}

// A minimum that rounds off the corner where two shapes meet, so their union
// reads as one body. `k` is the width of the blend, in px.
function smoothMin(a, b, k) {
  if (k <= 0) return Math.min(a, b);
  const h = Math.max(0, Math.min(1, 0.5 + (0.5 * (b - a)) / k));
  return b * (1 - h) + a * h - k * h * (1 - h);
}
function smoothMax(a, b, k) { return -smoothMin(-a, -b, k); }

// ------------------------------------------------------------------- corridors
// A minimum spanning tree over the member centres (Prim, O(n^2) in members).
// This is what keeps a blob in one piece: without it, two members further apart
// than the padding would each get their own island.
function spanningSegments(centres) {
  const segs = [];
  if (centres.length < 2) return segs;
  const reached = [0];
  const remaining = new Set(centres.map((_, i) => i).slice(1));
  while (remaining.size) {
    let bestFrom = -1, bestTo = -1, best = Infinity;
    for (const from of reached) for (const to of remaining) {
      const a = centres[from], b = centres[to];
      const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (d < best) { best = d; bestFrom = from; bestTo = to; }
    }
    segs.push([centres[bestFrom], centres[bestTo]]);
    reached.push(bestTo);
    remaining.delete(bestTo);
  }
  return segs;
}

const MAX_DETOURS = 3;   // how often one corridor may bend to get out of the way

function boxCorners(b) {
  return [[b.x, b.y], [b.x + b.width, b.y],
          [b.x + b.width, b.y + b.height], [b.x, b.y + b.height]];
}
function boxCentre(b) { return [b.x + b.width / 2, b.y + b.height / 2]; }

function closestOnSegment(p, a, b) {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const len2 = vx * vx + vy * vy;
  if (len2 === 0) return a;
  const t = Math.max(0, Math.min(1,
    ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / len2));
  return [a[0] + vx * t, a[1] + vy * t];
}

// How far along `dir` a waypoint must go to leave `shape` behind: past its
// furthest corner, plus the margin.
function offsetPastShape(from, dir, shape, margin) {
  let furthest = 0;
  for (const c of boxCorners(shape.box))
    furthest = Math.max(furthest,
      (c[0] - from[0]) * dir[0] + (c[1] - from[1]) * dir[1]);
  return furthest + margin;
}

// A corridor drawn straight through a node the blob must dodge gets cut in half
// by the subtraction, and the blob falls into two pieces. So bend it: take the
// obstacle it passes closest to, step sideways past that obstacle's furthest
// corner on whichever side is nearer, and route through that waypoint.
function routeCorridor(a, b, obstacles, margin, depth) {
  depth = depth || 0;
  if (depth >= MAX_DETOURS || !obstacles.length) return [a, b];
  let blocker = null, blockedAt = a, leastSlack = 0;
  for (const s of obstacles) {
    const near = closestOnSegment(boxCentre(s.box), a, b);
    const slack = sdShape(s, near[0], near[1]) - margin;
    if (slack < leastSlack) { leastSlack = slack; blocker = s; blockedAt = near; }
  }
  if (!blocker) return [a, b];
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const sideways = [-dy / len, dx / len], other = [dy / len, -dx / len];
  const forward = offsetPastShape(blockedAt, sideways, blocker, margin);
  const backward = offsetPastShape(blockedAt, other, blocker, margin);
  const dir = forward <= backward ? sideways : other;
  const off = Math.min(forward, backward);
  const way = [blockedAt[0] + dir[0] * off, blockedAt[1] + dir[1] * off];
  const first = routeCorridor(a, way, obstacles, margin, depth + 1);
  const second = routeCorridor(way, b, obstacles, margin, depth + 1);
  return first.slice(0, -1).concat(second);
}

function corridorSegments(members, obstacles, margin) {
  const out = [];
  const centres = members.map(m => boxCentre(m.box));
  for (const [from, to] of spanningSegments(centres)) {
    const path = routeCorridor(from, to, obstacles, margin);
    for (let i = 0; i < path.length - 1; i++) out.push([path[i], path[i + 1]]);
  }
  return out;
}

// Distance from a point to a box, 0 inside.
function boxGap(b, x0, y0, x1, y1) {
  const dx = Math.max(b.x - x1, x0 - (b.x + b.width), 0);
  const dy = Math.max(b.y - y1, y0 - (b.y + b.height), 0);
  return Math.hypot(dx, dy);
}

// The subset of members, corridors and obstacles that can affect a tile.
function prunePieces(pieces, x0, y0, x1, y1) {
  const memberReach = BLOB.padding + BLOB.smoothing;
  const linkReach = BLOB.corridor + BLOB.smoothing;
  const avoidReach = BLOB.clearance + BLOB.smoothing;
  let members = pieces.members.filter(m => boxGap(m.box, x0, y0, x1, y1) <= memberReach);
  if (!members.length) {
    // Every member is far: the field is positive here whichever one we seed
    // with, but the smooth minimum needs one, so take the nearest.
    let best = pieces.members[0], bestGap = Infinity;
    pieces.members.forEach(m => {
      const g = boxGap(m.box, x0, y0, x1, y1);
      if (g < bestGap) { bestGap = g; best = m; }
    });
    members = [best];
  }
  const links = pieces.links.filter(([a, b]) => {
    const box = { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]),
                  width: Math.abs(a[0] - b[0]), height: Math.abs(a[1] - b[1]) };
    return boxGap(box, x0, y0, x1, y1) <= linkReach;
  });
  const avoid = pieces.avoid.filter(s => boxGap(s.box, x0, y0, x1, y1) <= avoidReach);
  return [members, links, avoid];
}

// The scalar field whose zero contour is the blob boundary.
function makeField(members, links, avoid) {
  // Subtraction uses a tighter blend than the union: too soft and an avoided
  // node dents the boundary from much further away than its clearance.
  const cut = BLOB.smoothing / 2;
  const first = members[0], rest = members.slice(1);
  return (px, py) => {
    // Seeded with the first member, not with infinity: a smooth minimum blends
    // its two arguments, and infinity would poison the blend.
    let d = sdShape(first, px, py) - BLOB.padding;
    for (const m of rest)
      d = smoothMin(d, sdShape(m, px, py) - BLOB.padding, BLOB.smoothing);
    for (const [a, b] of links)
      d = smoothMin(d, sdSegment(px, py, a, b) - BLOB.corridor, BLOB.smoothing);
    for (const s of avoid)
      d = smoothMax(d, -(sdShape(s, px, py) - BLOB.clearance), cut);
    return d;
  };
}

// --------------------------------------------------------- marching squares
// Each contour point sits on one grid edge and is named by that edge ("h3,7"),
// not by its coordinates, so two neighbouring cells agree on it exactly and
// joining segments into loops is bookkeeping rather than guesswork.
function traceContour(pieces, bounds, resolution) {
  const cols = Math.max(2, Math.ceil((bounds.maxX - bounds.minX) / resolution) + 1);
  const rows = Math.max(2, Math.ceil((bounds.maxY - bounds.minY) / resolution) + 1);
  const values = new Float64Array(cols * rows);
  // Sample tile by tile against a pruned field. A member more than
  // padding + smoothing away from the tile can only ever return a large positive
  // distance, so it never wins the smooth minimum inside it; an avoided shape
  // beyond clearance + smoothing likewise cannot dent the boundary there. This
  // is exact, not an approximation — those terms are provably inert.
  for (let tj = 0; tj < rows; tj += BLOB_TILE) {
    for (let ti = 0; ti < cols; ti += BLOB_TILE) {
      const x0 = bounds.minX + ti * resolution, y0 = bounds.minY + tj * resolution;
      const iEnd = Math.min(cols, ti + BLOB_TILE), jEnd = Math.min(rows, tj + BLOB_TILE);
      const x1 = bounds.minX + (iEnd - 1) * resolution;
      const y1 = bounds.minY + (jEnd - 1) * resolution;
      const field = makeField(...prunePieces(pieces, x0, y0, x1, y1));
      for (let j = tj; j < jEnd; j++)
        for (let i = ti; i < iEnd; i++)
          values[j * cols + i] = field(bounds.minX + i * resolution,
                                       bounds.minY + j * resolution);
    }
  }

  const at = (i, j) => values[j * cols + i];
  const inside = (i, j) => at(i, j) < 0;
  const crossH = (i, j) => {
    const v0 = at(i, j), v1 = at(i + 1, j);
    const t = v0 === v1 ? 0.5 : v0 / (v0 - v1);
    return [bounds.minX + (i + t) * resolution, bounds.minY + j * resolution];
  };
  const crossV = (i, j) => {
    const v0 = at(i, j), v1 = at(i, j + 1);
    const t = v0 === v1 ? 0.5 : v0 / (v0 - v1);
    return [bounds.minX + i * resolution, bounds.minY + (j + t) * resolution];
  };

  const points = new Map(), segments = [];
  const link = (a, pa, b, pb) => {
    points.set(a, pa); points.set(b, pb); segments.push([a, b]);
  };
  for (let j = 0; j < rows - 1; j++) {
    for (let i = 0; i < cols - 1; i++) {
      const code = (inside(i, j) ? 1 : 0) | (inside(i + 1, j) ? 2 : 0) |
                   (inside(i + 1, j + 1) ? 4 : 0) | (inside(i, j + 1) ? 8 : 0);
      if (code === 0 || code === 15) continue;
      const topId = `h${i},${j}`, bottomId = `h${i},${j + 1}`;
      const leftId = `v${i},${j}`, rightId = `v${i + 1},${j}`;
      switch (code) {
        case 1: case 14: link(topId, crossH(i, j), leftId, crossV(i, j)); break;
        case 2: case 13: link(topId, crossH(i, j), rightId, crossV(i + 1, j)); break;
        case 3: case 12: link(leftId, crossV(i, j), rightId, crossV(i + 1, j)); break;
        case 4: case 11: link(rightId, crossV(i + 1, j), bottomId, crossH(i, j + 1)); break;
        case 6: case 9:  link(topId, crossH(i, j), bottomId, crossH(i, j + 1)); break;
        case 7: case 8:  link(leftId, crossV(i, j), bottomId, crossH(i, j + 1)); break;
        // Ambiguous: opposite corners inside. The centre value decides, which is
        // the standard fix and keeps the contour closed.
        case 5: case 10: {
          const centre = (at(i, j) + at(i + 1, j) + at(i + 1, j + 1) + at(i, j + 1)) / 4;
          if (centre < 0 ? code === 5 : code === 10) {
            link(topId, crossH(i, j), rightId, crossV(i + 1, j));
            link(leftId, crossV(i, j), bottomId, crossH(i, j + 1));
          } else {
            link(topId, crossH(i, j), leftId, crossV(i, j));
            link(rightId, crossV(i + 1, j), bottomId, crossH(i, j + 1));
          }
          break;
        }
      }
    }
  }

  // Every contour point lies on a grid edge shared by two cells, so exactly two
  // segments meet there: walking from any segment traces a whole loop.
  const adjacency = new Map();
  segments.forEach(([a, b], index) => {
    for (const id of [a, b]) {
      const list = adjacency.get(id);
      if (list) list.push(index); else adjacency.set(id, [index]);
    }
  });
  const used = new Set(), loops = [];
  for (let start = 0; start < segments.length; start++) {
    if (used.has(start)) continue;
    const ids = [segments[start][0]];
    let current = start, currentId = ids[0];
    for (;;) {
      used.add(current);
      const seg = segments[current];
      const nextId = seg[0] === currentId ? seg[1] : seg[0];
      if (nextId === ids[0]) break;
      ids.push(nextId);
      const next = (adjacency.get(nextId) || []).find(i => !used.has(i));
      if (next === undefined) break;   // contour ran off the grid; keep what we have
      current = next; currentId = nextId;
    }
    if (ids.length >= 3) loops.push(ids.map(id => points.get(id)));
  }
  return loops;
}

// ------------------------------------------------------------ simplification
function perpendicularDistance(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  return Math.abs(dx * (a[1] - p[1]) - dy * (a[0] - p[0])) / len;
}

// Ramer-Douglas-Peucker, iterative so a long contour cannot blow the stack.
function douglasPeucker(points, tolerance) {
  if (points.length < 3) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = 1; keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop();
    let worst = -1, worstD = tolerance;
    for (let i = first + 1; i < last; i++) {
      const d = perpendicularDistance(points[i], points[first], points[last]);
      if (d > worstD) { worstD = d; worst = i; }
    }
    if (worst !== -1) { keep[worst] = 1; stack.push([first, worst], [worst, last]); }
  }
  return points.filter((_, i) => keep[i] === 1);
}

function signedArea(loop) {
  let sum = 0;
  for (let i = 0, j = loop.length - 1; i < loop.length; j = i++)
    sum += (loop[j][0] - loop[i][0]) * (loop[j][1] + loop[i][1]);
  return sum / 2;
}

function containsPoint(loop, p) {
  let inside = false;
  for (let i = 0, j = loop.length - 1; i < loop.length; j = i++) {
    const [xi, yi] = loop[i], [xj, yj] = loop[j];
    if ((yi > p[1]) !== (yj > p[1]) &&
        p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// The tracing order depends on which cell the walk started in, and that decides
// which points simplification keeps. Anchoring the start to a geometric feature
// (leftmost point, ties on y) makes the output depend on the shape alone.
function rotateToExtreme(loop) {
  let best = 0;
  for (let i = 1; i < loop.length; i++)
    if (loop[i][0] < loop[best][0] ||
        (loop[i][0] === loop[best][0] && loop[i][1] < loop[best][1])) best = i;
  return loop.slice(best).concat(loop.slice(0, best));
}

function finishLoop(loop) {
  const anchored = rotateToExtreme(loop);
  const open = anchored.concat([anchored[0]]);
  let simplified = douglasPeucker(open, BLOB.tolerance);
  let attempt = BLOB.tolerance;      // coarsen rather than emit hundreds of points
  while (simplified.length > BLOB.maxPoints && attempt < 512) {
    attempt *= 1.6;
    simplified = douglasPeucker(open, attempt);
  }
  return simplified.slice(0, -1);
}

// --------------------------------------------------------------- entry point
// A smooth minimum is not associative, so folding members in a different order
// would move the boundary by a fraction of a pixel. A hyperedge is a *set*, so
// order it canonically first and the blob depends on the set alone.
function blobShapes(slugs, pos) {
  const out = [];
  slugs.forEach(s => {
    const p = pos[s];
    if (!p) return;
    const d = dimsOf(s), circle = styleFor(bySlug[s]) === "circle";
    out.push({ shape: circle ? "ellipse" : "rectangle",
               box: { x: p.x - d.w / 2, y: p.y - d.h / 2, width: d.w, height: d.h } });
  });
  return out.sort((a, b) => a.box.x - b.box.x || a.box.y - b.box.y ||
                            a.box.width - b.box.width || a.box.height - b.box.height);
}

// Closed outlines around `members`, largest first, in world coordinates.
// Normally there is exactly one. There can be more when an avoided node cuts a
// blob in two; loops *inside* another loop are holes and get dropped.
function blobOutline(members, avoid, sampleCap) {
  if (!members.length) return [];
  const links = corridorSegments(members, avoid, BLOB.clearance + BLOB.corridor);
  // The field is positive everywhere outside this margin, which keeps the
  // contour off the edge of the grid and so keeps every loop closed.
  const margin = BLOB.padding + BLOB.corridor + BLOB.smoothing + BLOB.resolution * 3;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const { box } of members) {
    minX = Math.min(minX, box.x); minY = Math.min(minY, box.y);
    maxX = Math.max(maxX, box.x + box.width); maxY = Math.max(maxY, box.y + box.height);
  }
  for (const seg of links) for (const [x, y] of seg) {
    minX = Math.min(minX, x); minY = Math.min(minY, y);
    maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
  }
  const bounds = { minX: minX - margin, minY: minY - margin,
                   maxX: maxX + margin, maxY: maxY + margin };

  // Only shapes reaching into the grid can bend the boundary; the rest have
  // zero influence there, so dropping them changes nothing.
  const reach = BLOB.clearance + BLOB.smoothing;
  const near = avoid.filter(({ box }) =>
    box.x - reach <= bounds.maxX && box.x + box.width + reach >= bounds.minX &&
    box.y - reach <= bounds.maxY && box.y + box.height + reach >= bounds.minY);

  let resolution = BLOB.resolution;
  const cap = Math.max(4000, Math.min(BLOB_MAX_SAMPLES, sampleCap || BLOB_MAX_SAMPLES));
  const samples = ((bounds.maxX - bounds.minX) / resolution + 1) *
                  ((bounds.maxY - bounds.minY) / resolution + 1);
  if (samples > cap) resolution *= Math.sqrt(samples / cap);

  const loops = traceContour({ members, links, avoid: near }, bounds, resolution);
  // Even-odd nesting: a loop inside an odd number of others is a hole.
  return loops
    .filter((loop, i) => loops.reduce(
      (depth, other, j) => depth + (j !== i && containsPoint(other, loop[0]) ? 1 : 0),
      0) % 2 === 0)
    .map(finishLoop)
    .filter(loop => loop.length >= 4)
    .sort((a, b) => Math.abs(signedArea(b)) - Math.abs(signedArea(a)));
}

// Non-members the blob has to bend around: every other node in the layout.
// Read from `pos`, not from the drawn elements — the blob layer is built before
// the node layer, so `nodeEls` still holds the *previous* render at this point
// (and nothing at all on the first one, which silently disabled avoidance).
//
// At 500 nodes and 59 blobs, handing every blob all 499 non-members and letting
// blobOutline filter them is 30,000 box tests per render before any sampling
// starts. A spatial hash over the node boxes, built once per render, answers
// "which non-members reach into this blob's span?" directly.
let _avoidGrid = null, _avoidGridKey = "";
function avoidGrid(pos) {
  const key = Object.keys(pos).length + ":" + layoutKey();
  if (_avoidGrid && _avoidGridKey === key) return _avoidGrid;
  const items = [];
  for (const slug in pos) {
    if (!bySlug[slug]) continue;
    const p = pos[slug], d = dimsOf(slug);
    items.push({ slug, minX: p.x - d.w / 2, maxX: p.x + d.w / 2,
                 minY: p.y - d.h / 2, maxY: p.y + d.h / 2 });
  }
  _avoidGridKey = key;
  _avoidGrid = gridHash(items, Math.max(NW, BW, 120));
  return _avoidGrid;
}

function blobAvoidShapes(memberSet, pos) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  memberSet.forEach(slug => {
    const p = pos[slug];
    if (!p) return;
    const d = dimsOf(slug);
    minX = Math.min(minX, p.x - d.w / 2); maxX = Math.max(maxX, p.x + d.w / 2);
    minY = Math.min(minY, p.y - d.h / 2); maxY = Math.max(maxY, p.y + d.h / 2);
  });
  if (!isFinite(minX)) return [];
  const reach = BLOB.padding + BLOB.corridor + BLOB.smoothing + BLOB.clearance + 40;
  const others = [];
  avoidGrid(pos).near(minX - reach, minY - reach, maxX + reach, maxY + reach)
    .forEach(it => { if (!memberSet.has(it.slug)) others.push(it.slug); });
  return blobShapes(others, pos);
}

// True when the distance field is worth computing: the cheap hull is used while
// dragging and when zoomed too far out for the detail to show.
let blobDragging = false;
function blobFieldMode() {
  return !blobDragging && tfFor().k >= BLOB_FIELD_MIN_ZOOM;
}

// Cached per hyperedge so a re-render (theme flip, dim pass) does not recompute
// the field. Keyed by the positions the field was built from.
const blobCache = new Map();
function blobGeometry(h, pos) {
  const key = h.state + "|" + h.members.map(s => {
    const p = pos[s];
    return p ? Math.round(p.x) + "," + Math.round(p.y) : "-";
  }).join(";");
  const hit = blobCache.get(h.state);
  if (hit && hit.key === key) return hit.value;
  const memberSet = new Set(h.members);
  const share = BLOB_SAMPLE_BUDGET / Math.max(1, hyperedges().list.length);
  const value = blobOutline(blobShapes(h.members, pos),
                            blobAvoidShapes(memberSet, pos), share);
  blobCache.set(h.state, { key, value });
  return value;
}

// The path for one hyperedge: field loops when they are worth it, hull if not.
function blobPathFor(h, pos) {
  if (!blobFieldMode()) return blobPath(h.members, pos);
  const loops = blobGeometry(h, pos);
  if (!loops.length) return blobPath(h.members, pos);
  return loops.map(closedCurve).filter(Boolean).join(" ") || blobPath(h.members, pos);
}

// -------------------------------------------------------------- blob labels
// Placed *on* the outline rather than pushed up off it (excaligraph's
// top | centre | bottom idea): each label takes the first anchor that does not
// collide with one already placed, so a dense cluster spreads its labels around
// its own boundary instead of drifting into a stack above the canvas.
function outlineAnchors(loops, members, pos) {
  if (loops && loops.length) {
    const loop = loops[0];
    let minY = Infinity, maxY = -Infinity, sumX = 0;
    loop.forEach(p => { minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]); sumX += p[0]; });
    const near = (target, sign) => {
      let x = 0, n = 0;
      loop.forEach(p => { if (Math.abs(p[1] - target) < 6) { x += p[0]; n++; } });
      return { x: n ? x / n : sumX / loop.length, y: target + sign * 12 };
    };
    return [near(minY, -1), near(maxY, 1),
            { x: sumX / loop.length, y: (minY + maxY) / 2 }];
  }
  const pts = members.flatMap(s => memberOutline(s, pos));
  if (!pts.length) return [{ x: 0, y: 0 }];
  let cx = 0, top = 1e9, bottom = -1e9;
  pts.forEach(p => { cx += p.x; top = Math.min(top, p.y); bottom = Math.max(bottom, p.y); });
  cx /= pts.length;
  return [{ x: cx, y: top - BPAD - 8 }, { x: cx, y: bottom + BPAD + 14 },
          { x: cx, y: (top + bottom) / 2 }];
}

function blobLabelPositions(pos) {
  const placed = [], out = {};
  hyperedges().list.forEach(h => {
    const loops = blobFieldMode() ? blobGeometry(h, pos) : null;
    const anchors = outlineAnchors(loops, h.members, pos);
    const w = h.state.length * 6.3;
    const clear = c => !placed.some(p =>
      Math.abs(c.x - p.x) < (w + p.w) / 2 + 8 && Math.abs(c.y - p.y) < 13);
    let chosen = anchors.find(clear);
    if (!chosen) {  // every anchor taken: step up from the first until clear
      chosen = { x: anchors[0].x, y: anchors[0].y };
      while (!clear(chosen)) chosen.y -= 14;   // strictly decreases, so it ends
    }
    placed.push({ x: chosen.x, y: chosen.y, w });
    out[h.state] = chosen;
  });
  return out;
}

// Which edges exist is decided by the display toggles; how they are drawn is
// decided separately by node style + layout in edgePath.
//
// Cross-graph links are kept in their own layer, rebuilt on demand, because
// there are 176 of them over 51 nodes on this repo alone and drawing them all
// at once is the hairball the Provenance view used to be. `show.links` decides
// how many exist at all; the impact/prov checkboxes decide which kinds.
function edgesFor() {
  const out = [];
  const sided = show.graphs === "both" && show.layout === "layered";
  const tree = (g, side) => DATA[g].nodes.forEach(n =>
    n.parents.forEach(p => out.push({ kind:"tree", from:p, to:n.slug, side })));
  if (show.tree) {
    if (recVis()) tree("record", sided ? "left" : null);
    if (stVis()) tree("state", sided ? "right" : null);
  }
  return out;
}

function crossLinksFor() {
  if (show.graphs !== "both" || show.links === "none") return [];
  const focus = show.links === "focus" ? (hovered || selected) : null;
  if (show.links === "focus" && !focus) return [];
  return DATA.links.filter(l => {
    if (l.kind === "impact" ? !show.impact : !show.prov) return false;
    return !focus || l.record === focus || l.state === focus;
  }).map(l => ({
    kind: l.kind, label: l.label, state: l.state,
    from: l.kind === "impact" ? l.record : l.state,
    to:   l.kind === "impact" ? l.state : l.record,
  }));
}

// Point on the border of the w x h box centered at a, along a -> b.
function trimToRect(a, b, d) {
  const dx = b.x - a.x, dy = b.y - a.y;
  if (!dx && !dy) return { x: a.x, y: a.y };
  const tx = dx ? (d.w / 2) / Math.abs(dx) : Infinity;
  const ty = dy ? (d.h / 2) / Math.abs(dy) : Infinity;
  const t = Math.min(tx, ty);
  return { x: a.x + dx * t, y: a.y + dy * t };
}

// Timeline edges read like `git log --graph`: out of the parent's right edge,
// into the child's left edge, with the bend held near the child so a lane change
// is visible as a hook rather than a long diagonal.
function timelineEdgePath(a, b, da, db) {
  const x1 = a.x + da.w / 2, x2 = b.x - db.w / 2;
  if (x2 <= x1) {  // same column or backwards: a shallow arc under the lanes
    const my = Math.max(a.y, b.y) + LANE_H * 0.55;
    return `M ${a.x} ${a.y + da.h / 2} C ${a.x} ${my}, ${b.x} ${my}, ${b.x} ${b.y + db.h / 2}`;
  }
  const bend = Math.min(28, (x2 - x1) / 2);
  return `M ${x1} ${a.y} C ${x1 + bend} ${a.y}, ${x2 - bend} ${b.y}, ${x2} ${b.y}`;
}

function edgePath(e, pos) {
  const a = pos[e.from], b = pos[e.to];
  if (!a || !b) return null;
  const da = dimsOf(e.from), db = dimsOf(e.to);
  if (show.layout === "timeline" && e.kind === "tree"
      && bySlug[e.from].graph === "record" && bySlug[e.to].graph === "record")
    return timelineEdgePath(a, b, da, db);
  if (show.style === "circles" && styleFor(bySlug[e.from]) === "circle") {
    const dx = b.x - a.x, dy = b.y - a.y;  // straight, trimmed to the perimeters
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / d, uy = dy / d;
    return `M ${a.x + ux * R} ${a.y + uy * R} L ${b.x - ux * R} ${b.y - uy * R}`;
  }
  if (show.layout === "force" || show.layout === "board") {
    const p1 = trimToRect(a, b, da), p2 = trimToRect(b, a, db);
    return `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
  }
  if (e.kind === "tree" && !e.side) {
    const y1 = a.y + da.h / 2, y2 = b.y - db.h / 2, ym = (y1 + y2) / 2;
    return `M ${a.x} ${y1} C ${a.x} ${ym}, ${b.x} ${ym}, ${b.x} ${y2}`;
  }
  if (e.kind === "tree") {
    const dir = e.side === "left" ? -1 : 1;
    const x = a.x + dir * da.w / 2, x2 = b.x + dir * db.w / 2;
    const off = 26 + 0.055 * Math.abs(b.y - a.y);
    return `M ${x} ${a.y} C ${x + dir * off} ${a.y}, ${x2 + dir * off} ${b.y}, ${x2} ${b.y}`;
  }
  const fromState = bySlug[e.from].graph === "state";
  const x1 = a.x + (fromState ? -da.w / 2 : da.w / 2);
  const x2 = b.x + (bySlug[e.to].graph === "state" ? -db.w / 2 : db.w / 2);
  const cx = (x1 + x2) / 2;
  return `M ${x1} ${a.y} C ${cx} ${a.y}, ${cx} ${b.y}, ${x2} ${b.y}`;
}

const SPINE_SPREAD = 96;   // width of the staggered spine, in world px

// Seat each claim on the spine, ordered by its position in the state column, so
// neighbouring claims get neighbouring seats and their ribbons do not cross.
let _spineRank = null;
function stateSpineRank() {
  if (_spineRank) return _spineRank;
  const order = DATA.state.nodes.slice().sort((a, b) => {
    const pa = posFor()[a.slug], pb = posFor()[b.slug];
    return (pa ? pa.y : 0) - (pb ? pb.y : 0);
  });
  _spineRank = { count: order.length };
  order.forEach((n, i) => _spineRank[n.slug] = i);
  return _spineRank;
}

// In `all` mode every cross-link belonging to one state node is routed through a
// shared waist on a vertical spine at mid-x, so 176 separate lines read as a
// dozen ribbons — you can see *which claim* a bundle serves, which is the thing
// the hairball hid. Straight-through beziers are kept for the focused view,
// where there are only a few lines and precision beats grouping.
function bundledCrossPath(e, pos) {
  const a = pos[e.from], b = pos[e.to];
  if (!a || !b) return null;
  const da = dimsOf(e.from), db = dimsOf(e.to);
  const fromState = bySlug[e.from].graph === "state";
  const x1 = a.x + (fromState ? -da.w / 2 : da.w / 2);
  const x2 = b.x + (bySlug[e.to].graph === "state" ? -db.w / 2 : db.w / 2);
  const st = pos[e.state];
  if (!st) return edgePath(e, pos);
  // Stagger each claim's waist along the spine, or every bundle would pinch at
  // the same x and the ribbons would be indistinguishable exactly where they
  // are densest.
  const rank = stateSpineRank();
  const seat = rank[e.state] || 0, seats = Math.max(1, rank.count - 1);
  const wx = (x1 + x2) / 2 + (seat / seats - 0.5) * SPINE_SPREAD;
  const wy = st.y;                                 // the waist, shared per claim
  return `M ${x1} ${a.y} C ${(x1 + wx) / 2} ${a.y}, ${wx} ${(a.y + wy) / 2}, ${wx} ${wy}` +
         ` C ${wx} ${(wy + b.y) / 2}, ${(wx + x2) / 2} ${b.y}, ${x2} ${b.y}`;
}

function crossPath(e, pos) {
  return show.links === "all" ? bundledCrossPath(e, pos) : edgePath(e, pos);
}

// ------------------------------------------------------------------ render
function markerDefs() {
  const defs = el("defs");
  const kinds = { tree: T().axis, prov: T().prov, imp: T().impact };
  for (const id in kinds) {
    const m = el("marker", { id: "arrow-" + id, viewBox: "0 0 10 10",
      refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
    m.appendChild(el("path", { d: "M 0 1 L 9 5 L 0 9 z", fill: kinds[id] }));
    defs.appendChild(m);
  }
  return defs;
}

function accentFor(entry) {
  const { graph, node } = entry;
  if (graph === "state")
    return node.is_root ? T().ink2 : (T().status[node.status] || T().muted);
  if (node.is_hwm) return T().hwm;
  if (node.unreconciled) return T().unrec;
  return node.is_root ? T().ink2 : T().axis;
}

function nodeXf(p, entry) {
  const shape = styleFor(entry);
  if (shape === "circle" || shape === "puck") return `translate(${p.x},${p.y})`;
  const d = dimsFor(entry);
  return `translate(${p.x - d.w / 2},${p.y - d.h / 2})`;
}

function drawNode(entry, pos) {
  const { graph, node } = entry;
  const p = pos[node.slug];
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  const frontier = graph === "state" && node.frontier;
  // card rect must stay firstChild (updateDim restyles it)
  g.appendChild(el("rect", { x: .5, y: .5, width: NW - 1, height: NH - 1, rx: 9,
    fill: T().surface, stroke: frontier ? accentFor(entry) : T().border,
    "stroke-width": frontier ? 1.4 : 1 }));
  g.appendChild(el("rect", { x: 3, y: 7, width: 4, height: NH - 14, rx: 2,
    fill: accentFor(entry) }));
  g.appendChild(el("text", { x: 16, y: 21, "font-family": FONT, "font-size": 12.5,
    "font-weight": node.is_root ? 700 : 600, fill: T().ink }, trunc(node.title, 32)));
  g.appendChild(el("text", { class: "detail", x: 16, y: 36.5, "font-family": MONO,
    "font-size": 10.5, fill: T().muted }, node.slug));
  let x = 16;
  const meta = (text, color, bold) => {
    const t = el("text", { class: "detail", x, y: 52, "font-family": FONT,
      "font-size": 10.5, fill: color, "font-weight": bold ? 650 : 400 }, text);
    g.appendChild(t);
    x += text.length * 6.3 + 13;
  };
  if (graph === "state") {
    if (node.is_root) meta("state root", T().ink2, true);
    else {
      g.appendChild(el("circle", { cx: x + 3.5, cy: 48.5, r: 3.5,
        fill: T().status[node.status] || T().muted }));
      x += 12;
      meta(node.status || "?", T().ink2);
      if (frontier) meta("frontier", T().ink2, true);
    }
  } else {
    meta((node.created_at || "").slice(0, 10), T().muted);
    if (node.is_root) meta("record root", T().ink2, true);
    if (node.is_hwm) meta("HWM", T().hwm, true);
    if (node.unreconciled) meta("unreconciled", T().unrec, true);
    if (node.impact_none != null) meta("no impact", T().muted);
    else if (node.impacts.length)
      meta(node.impacts.length + " impact" + (node.impacts.length > 1 ? "s" : ""), T().ink2);
  }
  const tip = el("title");
  tip.textContent = node.title + " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// Circle style: nodes as plain circles (record or state). The circle must stay
// firstChild (updateDim restyles it); <title> hover tooltip appended last.
function drawCircleNode(entry, pos) {
  const { node } = entry;
  const p = pos[node.slug];
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  const heavy = node.is_root || node.is_hwm || node.unreconciled || node.frontier;
  g.appendChild(el("circle", { r: R, fill: T().surface, stroke: accentFor(entry),
    "stroke-width": heavy ? 2.2 : 1.4 }));
  // The circle style used to be unlabelled by design, which made the Clusters
  // view unreadable: you could see the grouping and not what was grouped. The
  // label is drawn always and shown by zoom (applyTf), so panning stays cheap.
  g.appendChild(el("text", { class: "nodelabel", x: 0, y: R + 13,
    "font-family": FONT, "font-size": 10.5, "text-anchor": "middle",
    fill: T().ink2, "pointer-events": "none" }, trunc(node.title, 20)));
  const tip = el("title");
  tip.textContent = node.title + " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// Timeline chip: one line of title at full reading size, plus a status pip.
// Everything else about the node is one click away, which is the trade that
// keeps 39 of these legible side by side.
function drawChipNode(entry, pos) {
  const { node } = entry;
  const p = pos[node.slug];
  const accent = accentFor(entry);
  const marked = node.is_root || node.is_hwm || node.unreconciled;
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  g.appendChild(el("rect", { x: .5, y: .5, width: CW - 1, height: CH - 1, rx: 6,
    fill: T().surface, stroke: marked ? accent : T().border,
    "stroke-width": marked ? 1.4 : 1 }));
  g.appendChild(el("rect", { x: 0, y: 0, width: 3.5, height: CH, rx: 1.75,
    fill: accent }));
  g.appendChild(el("text", { x: 10, y: CH / 2 + 4, "font-family": FONT,
    "font-size": 11.5, "font-weight": node.is_root || node.is_hwm ? 650 : 500,
    fill: T().ink }, trunc(node.title, 24)));
  const tip = el("title");
  tip.textContent = (node.created_at || "").slice(0, 10) + " · " + node.title +
                    " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// Frontier board card: title, slug, status dot, how much record work stands
// behind the claim, and when the newest of it landed.
function drawBoardCard(entry, pos) {
  const { node } = entry;
  const p = pos[node.slug];
  const accent = accentFor(entry);
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: nodeXf(p, entry) });
  g.appendChild(el("rect", { x: .5, y: .5, width: BW - 1, height: BH - 1, rx: 10,
    fill: T().surface, stroke: node.frontier ? accent : T().border,
    "stroke-width": node.frontier ? 1.6 : 1 }));
  g.appendChild(el("rect", { x: 0, y: 0, width: 4, height: BH, rx: 2, fill: accent }));
  g.appendChild(el("text", { x: 15, y: 22, "font-family": FONT, "font-size": 13,
    "font-weight": node.is_root ? 700 : 620, fill: T().ink },
    trunc(node.title, 26)));
  g.appendChild(el("text", { class: "detail", x: 15, y: 39, "font-family": MONO,
    "font-size": 10.5, fill: T().muted }, node.slug));
  if (node.is_root) {
    g.appendChild(el("text", { x: 15, y: 60, "font-family": FONT, "font-size": 11,
      fill: T().ink2, "font-weight": 650 }, "state root"));
  } else {
    g.appendChild(el("circle", { cx: 18.5, cy: 56.5, r: 3.5, fill: accent }));
    g.appendChild(el("text", { x: 27, y: 60, "font-family": FONT, "font-size": 11,
      fill: T().ink2 }, node.status || "?"));
    const facts = [];
    if (node.prov_count) facts.push(node.prov_count + " prov");
    if (node.last_record_at) facts.push((node.last_record_at || "").slice(0, 10));
    if (facts.length)
      g.appendChild(el("text", { x: BW - 13, y: 60, "font-family": FONT,
        "font-size": 10.5, fill: T().muted, "text-anchor": "end" },
        facts.join(" · ")));
  }
  const tip = el("title");
  tip.textContent = node.title + " (" + node.slug + ")";
  g.appendChild(tip);
  return g;
}

// A collapsed hyperedge: one body carrying the claim's colour and its size.
// Clicking it opens the claim, where the button to expand it again lives.
function drawPuck(entry, pos) {
  const h = hyperedges().index[entry.state];
  const color = T().cat[(h ? h.ci : 0) % T().cat.length];
  const p = pos[entry.node.slug];
  const g = el("g", { class: "node", "data-slug": entry.node.slug,
                      cursor: "pointer", transform: nodeXf(p, entry) });
  g.appendChild(el("circle", { r: PUCK_R, fill: color, "fill-opacity": 0.18,
    stroke: color, "stroke-width": 2 }));
  g.appendChild(el("text", { x: 0, y: 4, "font-family": FONT, "font-size": 14,
    "font-weight": 700, "text-anchor": "middle", fill: color,
    "pointer-events": "none" }, String(entry.node.members)));
  g.appendChild(el("text", { class: "nodelabel", x: 0, y: PUCK_R + 14,
    "font-family": MONO, "font-size": 10.5, "text-anchor": "middle",
    fill: color, "pointer-events": "none" }, entry.state));
  const tip = el("title");
  tip.textContent = entry.node.title + " — " + entry.node.members +
                    " record nodes, collapsed";
  g.appendChild(tip);
  return g;
}

function drawAnyNode(entry, pos) {
  switch (styleFor(entry)) {
    case "puck":   return drawPuck(entry, pos);
    case "chip":   return drawChipNode(entry, pos);
    case "board":  return drawBoardCard(entry, pos);
    case "circle": return drawCircleNode(entry, pos);
    default:       return drawNode(entry, pos);
  }
}

// --------------------------------------------------------------- furniture
// Layout-specific scenery: the lane ruler and date gutter of the timeline, the
// column headers of the board. Drawn behind everything and never interactive.
function drawTimelineFurniture(pos) {
  const f = timelineFurniture(pos);
  if (!f) return null;
  const layer = el("g", { id: "furniture", "pointer-events": "none" });
  for (let i = 0; i < f.laneCount; i++) {  // one rule per lane, faint
    const y = i * LANE_H;
    layer.appendChild(el("line", { x1: f.x0, y1: y, x2: f.x1, y2: y,
      stroke: T().grid, "stroke-width": 1 }));
    layer.appendChild(el("text", { x: f.x0 - 10, y: y + 4, "font-family": MONO,
      "font-size": 10, fill: T().muted, "text-anchor": "end" }, "lane " + i));
  }
  const gutter = f.top - 6;
  f.ticks.forEach(t => {
    layer.appendChild(el("line", { x1: t.x, y1: gutter + 4, x2: t.x, y2: f.bottom,
      stroke: T().grid, "stroke-width": 1, "stroke-dasharray": "2 5" }));
    layer.appendChild(el("text", { x: t.x, y: gutter, "font-family": MONO,
      "font-size": 10, fill: T().muted, "text-anchor": "middle" }, t.label));
  });
  if (f.hwmX != null) {  // everything right of the rule is not yet reconciled
    layer.appendChild(el("rect", { x: f.hwmX, y: f.top - 2,
      width: Math.max(0, f.x1 - f.hwmX), height: f.bottom - f.top + 2,
      fill: T().unrec, opacity: 0.07 }));
    layer.appendChild(el("line", { x1: f.hwmX, y1: f.top - 2, x2: f.hwmX,
      y2: f.bottom, stroke: T().hwm, "stroke-width": 1.4, opacity: 0.7 }));
    layer.appendChild(el("text", { x: f.hwmX + 6, y: f.bottom + 12,
      "font-family": FONT, "font-size": 10.5, fill: T().hwm },
      "high-water mark →  unreconciled"));
  }
  return layer;
}

function drawBoardFurniture() {
  const f = boardFurniture();
  if (!f) return null;
  const layer = el("g", { id: "furniture", "pointer-events": "none" });
  const top = f.headerY - 18;
  f.columns.forEach(c => {
    layer.appendChild(el("rect", { x: c.x - 10, y: top,
      width: c.w + 20, height: f.height - top + 12, rx: 12,
      fill: T().grid, opacity: 0.35 }));
    const dot = el("circle", { r: 4, fill: T().status[c.status] || T().muted });
    const text = el("text", { "font-family": FONT, "font-size": 11.5,
      "font-weight": 700, fill: T().ink2, "letter-spacing": "0.06em" },
      c.status.toUpperCase() + "  " + c.count);
    if (c.rail) {  // collapsed: the header turns and runs down the rail
      dot.setAttribute("cx", c.x + c.w / 2);
      dot.setAttribute("cy", f.headerY - 4);
      text.setAttribute("x", c.x + c.w / 2 + 4);
      text.setAttribute("y", f.headerY + 12);
      text.setAttribute("text-anchor", "start");
      text.setAttribute("transform",
        `rotate(90 ${c.x + c.w / 2 + 4} ${f.headerY + 12})`);
    } else {
      dot.setAttribute("cx", c.x + 5);
      dot.setAttribute("cy", f.headerY - 4);
      text.setAttribute("x", c.x + 15);
      text.setAttribute("y", f.headerY);
    }
    layer.appendChild(dot);
    layer.appendChild(text);
  });
  return layer;
}

let blobEls = {};
function drawBlobs(pos) {
  const layer = el("g", { id: "blobs" });
  blobEls = {};
  const lps = blobLabelPositions(pos);
  const hs = hyperedges().list.slice()
    .sort((a, b) => b.members.length - a.members.length);  // big first, small on top
  hs.forEach(h => {
    // A collapsed claim is represented by its puck; drawing its blob as well —
    // around whatever members another claim still keeps on screen — would be two
    // contradictory pictures of the same thing.
    if (collapsed.has(h.state)) return;
    const d = blobPathFor(h, pos);
    if (!d) return;
    const color = T().cat[h.ci % T().cat.length];
    const path = el("path", { d, fill: color,
      "fill-opacity": theme === "dark" ? 0.18 : 0.14,
      stroke: color, "stroke-opacity": 0.45, "stroke-width": 1.2,
      "data-state": h.state, "pointer-events": "none" });
    const tip = el("title");
    tip.textContent = bySlug[h.state].node.title + " (" + h.state + ")";
    path.appendChild(tip);
    const lp = lps[h.state];
    const label = el("text", { x: lp.x, y: lp.y, class: "bloblabel",
      "data-slug": h.state, cursor: "pointer", "font-family": MONO,
      "font-size": 10.5, "text-anchor": "middle", fill: color }, h.state);
    layer.appendChild(path);
    layer.appendChild(label);
    blobEls[h.state] = { path, label };
  });
  return layer;
}

function updateBlobs(slug) {
  const pos = posFor(), H = hyperedges();
  (H.memberOf[slug] || []).forEach(st => {
    const be = blobEls[st];
    if (be) be.path.setAttribute("d", blobPathFor(H.index[st], pos));
  });
  const lps = blobLabelPositions(pos);  // placement involves every label
  for (const st in blobEls) {
    blobEls[st].label.setAttribute("x", lps[st].x);
    blobEls[st].label.setAttribute("y", lps[st].y);
  }
}

// Redraw only the blob layer — after a drag ends (the field replaces the hull
// used while dragging) or after zooming across the field threshold.
function redrawBlobs() {
  const world = document.getElementById("world");
  const old = document.getElementById("blobs");
  if (!world || !old) return;
  const fresh = drawBlobs(posFor());
  world.replaceChild(fresh, old);
  updateDim();
}

function renderAll() {
  const pos = posFor();
  svg.textContent = "";
  svg.appendChild(markerDefs());
  const world = el("g", { id: "world" });
  svg.appendChild(world);
  blobEls = {};
  const furniture = show.layout === "timeline" ? drawTimelineFurniture(pos)
                  : show.layout === "board" ? drawBoardFurniture() : null;
  if (furniture) world.appendChild(furniture);                    // behind everything
  if (show.blobs && recVis()) world.appendChild(drawBlobs(pos));
  const edgeLayer = el("g", { id: "edges" });
  const nodeLayer = el("g", { id: "nodes" });
  world.appendChild(edgeLayer);
  world.appendChild(el("g", { id: "crosslinks" }));
  world.appendChild(nodeLayer);

  if (show.layout === "layered" && show.graphs === "both") {
    const head = (text, x, anchor) => nodeLayer.appendChild(el("text", { x, y: -64,
      "font-family": FONT, "font-size": 12, "font-weight": 700, fill: T().muted,
      "letter-spacing": "0.08em", "text-anchor": anchor }, text));
    head("RECORD — " + DATA.record.nodes.length + " nodes (append-only log)", 0, "middle");
    head("STATE — " + DATA.state.nodes.length + " nodes (distilled now)",
         comboStateX(), "middle");
  }

  edges = edgesFor();
  edgeEls = [];
  const quiet = show.style === "circles";  // tree edges stay understated there
  edges.forEach(e => {
    const d = edgePath(e, pos);
    if (!d) { edgeEls.push(null); return; }
    const style = e.kind === "tree"
      ? (quiet ? { stroke: T().axis, marker: null, dash: null, op: 0.55, w: 1 }
               : { stroke: T().axis, marker: "arrow-tree", dash: null, op: 0.9, w: 1.4 })
      : e.kind === "impact"
        ? { stroke: T().impact, marker: "arrow-imp", dash: "6 4", op: 0.8, w: 1.6 }
        : { stroke: T().prov, marker: "arrow-prov", dash: null, op: 0.65, w: 1.6 };
    const path = el("path", { d, fill: "none", stroke: style.stroke,
      "stroke-width": style.w, opacity: style.op });
    if (style.marker) path.setAttribute("marker-end", `url(#${style.marker})`);
    path.dataset.op = style.op;
    if (style.dash) path.setAttribute("stroke-dasharray", style.dash);
    if (e.label) {
      const tip = el("title");
      tip.textContent = e.kind + ": " + e.label;
      path.appendChild(tip);
    }
    edgeLayer.appendChild(path);
    edgeEls.push(path);
  });

  nodeEls = {};
  const draw = g => DATA[g].nodes.forEach(n => {
    if (!pos[n.slug]) return;
    const gEl = drawAnyNode(bySlug[n.slug], pos);
    nodeLayer.appendChild(gEl);
    nodeEls[n.slug] = gEl;
  });
  if (recVis()) draw("record");
  if (stVis()) draw("state");
  collapsed.forEach(state => {           // one puck per collapsed hyperedge
    const slug = puckKey(state);
    if (!pos[slug] || !bySlug[slug]) return;
    const gEl = drawAnyNode(bySlug[slug], pos);
    nodeLayer.appendChild(gEl);
    nodeEls[slug] = gEl;
  });

  renderCrossLinks();
  applyTf();
  updateDim();
}

// The cross-link layer is rebuilt rather than dimmed, because in `focus` mode
// the answer is usually "draw nothing at all" and the cheapest way to draw
// nothing is to build nothing.
let crossEdges = [], crossEls = [];
function renderCrossLinks() {
  const layer = document.getElementById("crosslinks");
  if (!layer) return;
  layer.textContent = "";
  _spineRank = null;          // positions may have changed; reseat the spine
  const pos = posFor();
  crossEdges = crossLinksFor();
  crossEls = [];
  const bundled = show.links === "all";
  crossEdges.forEach(e => {
    const d = crossPath(e, pos);
    if (!d) { crossEls.push(null); return; }
    const style = e.kind === "impact"
      ? { stroke: T().impact, marker: "arrow-imp", dash: "6 4", op: bundled ? 0.5 : 0.85 }
      : { stroke: T().prov, marker: "arrow-prov", dash: null, op: bundled ? 0.4 : 0.75 };
    const path = el("path", { d, fill: "none", stroke: style.stroke,
      "stroke-width": bundled ? 1.1 : 1.8, opacity: style.op });
    // Bundled ribbons carry no arrowheads: 176 of them turn into visual noise,
    // and the direction is already given by which column each end sits in.
    if (!bundled) path.setAttribute("marker-end", `url(#${style.marker})`);
    if (style.dash) path.setAttribute("stroke-dasharray", style.dash);
    path.dataset.op = style.op;
    if (e.label) {
      const tip = el("title");
      tip.textContent = e.kind + ": " + e.label;
      path.appendChild(tip);
    }
    layer.appendChild(path);
    crossEls.push(path);
  });
}

// Below this zoom a 10.5px label is under 7px on screen — noise, not text.
const LABEL_MIN_ZOOM = 0.62;

// Level of detail. Text that cannot be read costs layout and paint time for
// nothing, so it is switched off by zoom rather than drawn small: secondary
// lines first, then all node text, leaving a coloured box that still reads as a
// shape at a glance.
function applyLod(k) {
  const set = (sel, on) =>
    svg.querySelectorAll(sel).forEach(e => e.style.display = on ? "" : "none");
  set("text.nodelabel", k >= LABEL_MIN_ZOOM);
  set("#nodes text.detail", k >= DETAIL_MIN_ZOOM);
  const nodes = document.getElementById("nodes");
  if (nodes) nodes.style.setProperty("--lod-text", k >= TEXT_MIN_ZOOM ? "1" : "0");
  set("#nodes text:not(.nodelabel):not(.detail)", k >= TEXT_MIN_ZOOM);
}

function applyTf() {
  const t = tfFor();
  const world = document.getElementById("world");
  if (world) world.setAttribute("transform", `translate(${t.x},${t.y}) scale(${t.k})`);
  applyLod(t.k);
}

// ------------------------------------------------------- dim / select / search
function neighborhood(slug) {
  const rel = new Set([slug]);
  edges.forEach(e => {
    if (e.from === slug) rel.add(e.to);
    if (e.to === slug) rel.add(e.from);
  });
  // Cross-graph neighbours come from the data, not from what is currently
  // drawn: in `focus` mode nothing is drawn until something is selected, and
  // the selection is what decides the neighbourhood in the first place.
  if (show.graphs === "both") DATA.links.forEach(l => {
    if (l.record === slug) rel.add(l.state);
    if (l.state === slug) rel.add(l.record);
  });
  if (show.blobs && recVis()) {  // union in hyperedge co-members / members
    const H = hyperedges();
    (H.memberOf[slug] || []).forEach(st =>
      H.index[st].members.forEach(m => rel.add(m)));
    if (H.index[slug]) H.index[slug].members.forEach(m => rel.add(m));
  }
  return rel;
}

function matches(node) {
  if (!query) return true;
  return (node.slug + " " + node.title + " " + node.content).toLowerCase().includes(query);
}

function updateDim() {
  const rel = selected ? neighborhood(selected) : null;
  const vis = {};
  for (const slug in nodeEls) {
    const entry = bySlug[slug];
    const m = matches(entry.node);
    const op = !m ? 0.12 : (rel && !rel.has(slug)) ? 0.3 : 1;
    vis[slug] = op === 1;
    nodeEls[slug].setAttribute("opacity", op);
    const box = nodeEls[slug].firstChild;  // the shape stays firstChild in every draw*
    const shape = styleFor(entry);
    const n = entry.node;
    if (shape === "puck") {
      box.setAttribute("stroke-width", slug === selected ? 3.2 : 2);
    } else if (shape === "circle") {
      const heavy = n.is_root || n.is_hwm || n.unreconciled || n.frontier;
      box.setAttribute("stroke", slug === selected ? T().ink : accentFor(entry));
      box.setAttribute("stroke-width", slug === selected ? 2.4 : heavy ? 2.2 : 1.4);
    } else {
      // Marked = something the reader should not miss: the frontier on a state
      // node, the root / high-water mark / unreconciled tail on a record node.
      const marked = shape === "chip"
        ? (n.is_root || n.is_hwm || n.unreconciled)
        : (entry.graph === "state" && n.frontier);
      const heavy = shape === "board" ? 1.6 : 1.4;
      box.setAttribute("stroke", slug === selected ? T().ink
        : marked ? accentFor(entry) : T().border);
      box.setAttribute("stroke-width", slug === selected ? heavy + 0.4
        : marked ? heavy : 1);
    }
  }
  for (const st in blobEls) {  // dim via a separate opacity attr; base attrs
    const h = hyperedges().index[st];  // stay untouched for the SVG export
    let on = true;
    if (selected) on = selected === st || h.members.includes(selected);
    else if (query) on = matches(bySlug[st].node) ||
      h.members.some(m => matches(bySlug[m].node));
    blobEls[st].path.setAttribute("opacity", on ? 1 : 0.12);
    blobEls[st].label.setAttribute("opacity", on ? 1 : 0.12);
  }
  const dimEdges = (list, els) => list.forEach((e, i) => {
    const pathEl = els[i];
    if (!pathEl) return;
    const on = vis[e.from] !== false && vis[e.to] !== false &&
      (!rel || e.from === selected || e.to === selected);
    pathEl.setAttribute("opacity", on ? pathEl.dataset.op : 0.08);
  });
  dimEdges(edges, edgeEls);
  dimEdges(crossEdges, crossEls);
}

// Hovering a node is enough to reveal its cross-graph links in `focus` mode —
// selecting is for reading the panel, hovering is for "what does this touch?".
let hovered = null;
function setHovered(slug) {
  if (hovered === slug) return;
  hovered = slug;
  if (show.links === "focus" && show.graphs === "both") {
    renderCrossLinks();
    updateDim();
  }
}

function select(slug) {
  selected = slug;
  renderCrossLinks();
  updateDim();
  renderPanel();
}
function deselect() { selected = null; renderCrossLinks(); updateDim(); renderPanel(); }

function jumpTo(slug) {
  const entry = bySlug[slug];
  if (!entry) return;
  const visible = entry.graph === "record" ? recVis() : stVis();
  if (!visible) {
    show.graphs = "both";
    syncControls();
    renderAll();
    fitDone[layoutKey()] = true;  // jumpTo centers on the target itself
  }
  select(slug);
  const p = posFor()[slug];
  if (!p) return;
  const t = tfFor(), r = svg.getBoundingClientRect();
  t.x = r.width / 2 - p.x * t.k;
  t.y = r.height / 2 - p.y * t.k;
  applyTf();
}

// ------------------------------------------------------------------- panel
function slugLink(slug) {
  return bySlug[slug]
    ? `<a class="slug" data-slug="${slug}">${slug}</a>`
    : `<span class="slugchip">${slug}</span>`;
}

function mdlite(content) {
  const inline = s => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(SLUG_JS, m => bySlug[m] ? slugLink(m) : m);
  const out = [];
  let list = null, para = [];
  const flushPara = () => {
    if (para.length) { out.push("<p>" + inline(para.join(" ")) + "</p>"); para = []; }
  };
  const flushList = () => {
    if (list) { out.push("<ul>" + list.join("") + "</ul>"); list = null; }
  };
  content.split("\n").forEach(line => {
    const t2 = line.trim();
    if (t2.startsWith("## ")) { flushPara(); flushList();
      out.push("<h4>" + inline(t2.slice(3)) + "</h4>"); }
    else if (t2.startsWith("- ")) { flushPara();
      (list = list || []).push("<li>" + inline(t2.slice(2)) + "</li>"); }
    else if (!t2) { flushPara(); flushList(); }
    else { flushList(); para.push(t2); }
  });
  flushPara(); flushList();
  return out.join("");
}

function chip(label, color) {
  const dot = color ? `<span class="dot" style="background:${color}"></span>` : "";
  return `<span class="chip">${dot}${esc(label)}</span>`;
}

function linkList(items) {
  if (!items.length) return '<p class="meta">none</p>';
  return '<ul class="links">' + items.map(i =>
    `<li>${slugLink(i.slug)} <span class="note">${esc(i.note || "")}</span></li>`
  ).join("") + "</ul>";
}

function renderPanel() {
  if (!selected || !bySlug[selected]) { panel.innerHTML = legendHTML(); bindPanel(); return; }
  const { graph, node } = bySlug[selected];
  let chips = "";
  if (graph === "state") {
    if (node.is_root) chips += chip("state root");
    else chips += chip(node.status || "?", T().status[node.status]);
    if (node.frontier) chips += chip("frontier");
  } else {
    if (node.is_root) chips += chip("record root");
    if (node.is_hwm) chips += chip("high-water mark", T().hwm);
    if (node.unreconciled) chips += chip("unreconciled", T().unrec);
    if (node.impact_none != null) chips += chip("impact: none");
  }
  let html = `
    <div class="meta">${graph} graph · created ${esc((node.created_at || "").slice(0, 16).replace("T", " "))}</div>
    <h2>${esc(node.title)}</h2>
    <div class="slugchip">${esc(node.slug)}</div>
    <div class="chips">${chips}</div>`;
  if (graph === "record") {
    if (node.impact_none != null)
      html += `<h3>State impact</h3><p class="meta">none: ${esc(node.impact_none)}</p>`;
    else if (node.impacts.length)
      html += "<h3>Declares impact on</h3>" + linkList(node.impacts.map(i => ({
        slug: i.resolved || i.target,
        note: (i.new ? "NEW · " : "") + i.delta })));
    const citedBy = DATA.links.filter(l => l.record === node.slug && l.kind === "provenance");
    html += "<h3>Cited as provenance by</h3>" +
      linkList(citedBy.map(l => ({ slug: l.state, note: l.label })));
  } else if (!node.is_root) {
    // A claim with an impact set can be folded to one puck. At 500 nodes that is
    // the difference between reading the shape of the work and reading a wall.
    const h = hyperedges().index[node.slug];
    if (h) {
      const on = collapsed.has(node.slug);
      html += `<h3>Cluster</h3><p class="meta">${h.members.length} record node` +
        `${h.members.length > 1 ? "s" : ""} declare impact on this claim.</p>` +
        `<button class="act" data-collapse="${node.slug}">` +
        `${on ? "Expand" : "Collapse to one puck"}</button>`;
    }
    const prov = DATA.links.filter(l => l.state === node.slug && l.kind === "provenance");
    html += "<h3>Derived from (provenance)</h3>" +
      linkList(prov.map(l => ({ slug: l.record, note: l.label })));
    const impacts = DATA.links.filter(l => l.state === node.slug && l.kind === "impact");
    html += "<h3>Impact declarations targeting this</h3>" +
      linkList(impacts.map(l => ({ slug: l.record, note: l.label })));
  }
  html += `<h3>Content</h3><div class="content">${mdlite(node.content)}</div>`;
  panel.innerHTML = html;
  bindPanel();
}

function legendHTML() {
  const S = T().status;
  const frontier = DATA.state.nodes.filter(n => n.frontier).length;
  const unrec = DATA.record.nodes.filter(n => n.unreconciled).length;
  const swatch = (color, dashed) =>
    `<span class="legend-swatch" style="border-top-color:${color};border-top-style:${dashed ? "dashed" : "solid"}"></span>`;
  return `
    <h2>__TITLE__</h2>
    <div class="meta">Two-graph hypergraph — click any node for details.</div>
    <h3>Reconciliation</h3>
    <table class="stats">
      <tr><td>record nodes</td><td>${DATA.record.nodes.length}</td></tr>
      <tr><td>state nodes</td><td>${DATA.state.nodes.length}</td></tr>
      <tr><td>cross-graph links</td><td>${DATA.links.length}</td></tr>
      <tr><td>frontier</td><td>${frontier}</td></tr>
      <tr><td>unreconciled</td><td>${unrec}</td></tr>
      <tr><td>high-water mark</td><td>${DATA.reconciliation.high_water_mark ? slugLink(DATA.reconciliation.high_water_mark) : "—"}</td></tr>
      <tr><td>reconciled at</td><td>${esc((DATA.reconciliation.reconciled_at || "—").slice(0, 16).replace("T", " "))}</td></tr>
    </table>
    <h3>State status</h3>
    <div class="chips">
      ${chip("working", S.working)}${chip("open", S.open)}${chip("broken", S.broken)}
      ${chip("blocked", S.blocked)}${chip("superseded", S.superseded)}
    </div>
    <div class="meta" style="margin-top:6px">frontier = open ∪ broken ∪ blocked (colored border)</div>
    <h3>Record markers</h3>
    <div class="chips">${chip("high-water mark", T().hwm)}${chip("unreconciled", T().unrec)}</div>
    <h3>Edges</h3>
    <table class="stats">
      <tr><td>${swatch(T().axis)}</td><td>parent → child (within one graph)</td></tr>
      <tr><td>${swatch(T().prov)}</td><td>provenance: state node derives from record node</td></tr>
      <tr><td>${swatch(T().impact, true)}</td><td>declared State Impact: record → state target</td></tr>
    </table>
    ${show.blobs && recVis() ? `<h3>Hyperedge blobs</h3>
    <div class="meta">Each translucent blob is a hyperedge: one state node wrapping
    all the record work that declares impact on it; overlapping blobs share record
    nodes. Click a blob's label to open that state node.</div>` : ""}
    <p class="hint">The four view chips each answer one question — Timeline: what
    happened, in order · Frontier: what is true now · Provenance: what each state
    claim rests on · Clusters: which work belongs to the same claim. The toggles
    below them mix graphs, node style, layout, and edge types freely.
    Scroll to zoom · drag background to pan · drag nodes to rearrange ·
    click a node for full content · Esc to deselect · drag the divider to resize
    this panel. Use the export menu for SVG/PDF.</p>`;
}

function bindPanel() {
  panel.querySelectorAll("a.slug").forEach(a =>
    a.addEventListener("click", () => jumpTo(a.dataset.slug)));
  panel.querySelectorAll("button[data-collapse]").forEach(b =>
    b.addEventListener("click", () => toggleCollapse(b.dataset.collapse)));
}

function toggleCollapse(state) {
  if (collapsed.has(state)) collapsed.delete(state); else collapsed.add(state);
  rerender();
  renderPanel();
}

// -------------------------------------------------------------- interaction
let drag = null;
svg.addEventListener("pointerdown", e => {
  const lbl = e.target.closest ? e.target.closest(".bloblabel") : null;
  const nodeG = e.target.closest ? e.target.closest(".node") : null;
  if (nodeG) {
    const slug = nodeG.dataset.slug;
    const p = posFor()[slug];
    drag = { type: "node", slug, sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y, moved: false };
  } else {
    drag = { type: "pan", sx: e.clientX, sy: e.clientY,
             ox: tfFor().x, oy: tfFor().y, moved: false,
             blob: lbl ? lbl.dataset.slug : null };
  }
  svg.setPointerCapture(e.pointerId);
  svg.classList.add("dragging");
});
svg.addEventListener("pointermove", e => {
  if (!drag) return;
  const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
  if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
  if (!drag.moved) return;
  if (drag.type === "pan") {
    const t = tfFor();
    t.x = drag.ox + dx;
    t.y = drag.oy + dy;
    applyTf();
  } else {
    const pos = posFor(), p = pos[drag.slug];
    p.x = drag.ox + dx / tfFor().k;
    p.y = drag.oy + dy / tfFor().k;
    nodeEls[drag.slug].setAttribute("transform", nodeXf(p, bySlug[drag.slug]));
    edges.forEach((eg, i) => {
      if (!edgeEls[i]) return;
      if (eg.from === drag.slug || eg.to === drag.slug)
        edgeEls[i].setAttribute("d", edgePath(eg, pos));
    });
    crossEdges.forEach((eg, i) => {
      if (!crossEls[i]) return;
      // A bundled ribbon moves when its *claim* moves, not only its own ends.
      if (eg.from === drag.slug || eg.to === drag.slug || eg.state === drag.slug)
        crossEls[i].setAttribute("d", crossPath(eg, pos));
    });
    // The distance field is too costly per frame; drag on the cheap hull and
    // put the real outline back on pointerup.
    if (show.blobs && recVis()) { blobDragging = true; updateBlobs(drag.slug); }
  }
});
svg.addEventListener("pointerup", e => {
  svg.classList.remove("dragging");
  if (!drag) return;
  if (!drag.moved) {
    if (drag.type === "node")
      select(isPuck(drag.slug) ? puckState(drag.slug) : drag.slug);
    else if (drag.blob) select(drag.blob);
    else deselect();
  }
  const wasDragging = blobDragging;
  drag = null;
  blobDragging = false;
  if (wasDragging && show.blobs && recVis()) redrawBlobs();
});
svg.addEventListener("wheel", e => {
  e.preventDefault();
  const t = tfFor(), r = svg.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const before = blobFieldMode();
  const k2 = Math.min(2.5, Math.max(0.1, t.k * Math.exp(-e.deltaY * 0.0016)));
  t.x = mx - (mx - t.x) * (k2 / t.k);
  t.y = my - (my - t.y) * (k2 / t.k);
  t.k = k2;
  applyTf();
  // Crossing the field threshold swaps hull for outline (and back).
  if (show.blobs && recVis() && blobFieldMode() !== before) redrawBlobs();
}, { passive: false });
// Hover reveals a node's cross-graph links without committing the panel to it.
svg.addEventListener("pointerover", e => {
  const g = e.target.closest ? e.target.closest(".node") : null;
  setHovered(g ? g.dataset.slug : null);
});
svg.addEventListener("pointerout", e => {
  const g = e.target.closest ? e.target.closest(".node") : null;
  if (g && !g.contains(e.relatedTarget)) setHovered(null);
});
document.addEventListener("keydown", e => { if (e.key === "Escape") deselect(); });

document.getElementById("search").addEventListener("input", e => {
  query = e.target.value.trim().toLowerCase();
  updateDim();
});

// The layout's own scenery is content, not decoration: an empty `broken` column
// is a real answer, and cropping it because it holds no cards would be a lie.
function furnitureBounds(pos) {
  if (show.layout === "timeline") {
    const f = timelineFurniture(pos);
    return f && { minX: f.x0 - 58, maxX: f.x1,
                  minY: f.top - 20, maxY: f.bottom + 18 };
  }
  if (show.layout === "board") {
    const f = boardFurniture();
    if (!f) return null;
    const last = f.columns[f.columns.length - 1];
    return { minX: f.columns[0].x - 12, maxX: last.x + last.w + 12,
             minY: f.headerY - 24, maxY: f.height + 30 };
  }
  if (show.layout === "layered" && show.graphs === "both")
    return { minX: 1e9, maxX: -1e9, minY: -64, maxY: -1e9 };  // column headers
  return null;
}

function worldBounds() {
  const pos = posFor();
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  for (const slug in pos) {
    if (!nodeEls[slug]) continue;
    const entry = bySlug[slug], d = dimsFor(entry);
    const circle = styleFor(entry) === "circle";
    const hx = circle ? R + BPAD + 20 : d.w / 2;
    const hy = circle ? R + BPAD + 20 : d.h / 2;
    minX = Math.min(minX, pos[slug].x - hx);
    maxX = Math.max(maxX, pos[slug].x + hx);
    minY = Math.min(minY, pos[slug].y - hy);
    maxY = Math.max(maxY, pos[slug].y + hy);
  }
  const f = furnitureBounds(pos);
  if (f) {
    minX = Math.min(minX, f.minX); maxX = Math.max(maxX, f.maxX);
    minY = Math.min(minY, f.minY); maxY = Math.max(maxY, f.maxY);
  }
  return { minX, minY, maxX, maxY };
}

// Which axis a layout is fitted on, and how far it may be enlarged.
//
// Fitting both axes of a long strip is what produced the 0.18 zoom this overhaul
// exists to kill. A timeline is short and endless: fit its height, keep the type
// at design size, and scroll through history. Columns and board lanes are the
// same argument turned ninety degrees — fit the width, scroll down the list.
function fitPlan() {
  if (show.layout === "timeline") return { axis: "y", max: 1 };
  if (show.layout === "board") return { axis: "x", max: 1 };
  if (show.layout === "layered" && show.graphs === "both")
    return { axis: "x", max: MAX_FIT };
  return { axis: "both", max: MAX_FIT };
}

// Fit, but never below MIN_FIT. Below that the labels stop being text and the
// view is worthless; scrolling a legible strip beats seeing an illegible whole.
// When the content overflows the axis, anchor at its start rather than centering
// on its middle — for a timeline that means "start at the beginning".
function fit() {
  const { minX, minY, maxX, maxY } = worldBounds();
  if (minX > maxX) return;
  const plan = fitPlan();
  const r = svg.getBoundingClientRect(), pad = 40;
  const kx = (r.width - pad * 2) / (maxX - minX);
  const ky = (r.height - pad * 2) / (maxY - minY);
  const raw = plan.axis === "x" ? kx : plan.axis === "y" ? ky : Math.min(kx, ky);
  const t = tfFor();
  t.k = Math.max(MIN_FIT, Math.min(plan.max, raw));
  const fitsX = (maxX - minX) * t.k <= r.width - pad * 2;
  const fitsY = (maxY - minY) * t.k <= r.height - pad * 2;
  t.x = fitsX ? (r.width - (maxX + minX) * t.k) / 2 : pad - minX * t.k;
  t.y = fitsY ? (r.height - (maxY + minY) * t.k) / 2 : pad - minY * t.k;
  applyTf();
}

// ---------------------------------------------------------------- controls
function syncControls() {
  const active = activePreset();
  document.querySelectorAll("#presets button").forEach(b =>
    b.classList.toggle("active", b.dataset.preset === active));
  document.querySelectorAll("#toggles .seg").forEach(seg => {
    const key = seg.dataset.key;
    seg.querySelectorAll("button").forEach(b =>
      b.classList.toggle("active", b.dataset.val === show[key]));
    // Context-specific controls are hidden, not dimmed: the panel should only
    // ever offer choices that mean something for what is on screen.
    seg.hidden = segHidden(key);
  });
  const both = show.graphs === "both";
  document.querySelectorAll("#toggles .checks input").forEach(cb => {
    const key = cb.dataset.key;
    cb.checked = show[key];
    const off = (key === "impact" || key === "prov") ? !both
      : key === "blobs" ? !recVis() : false;
    cb.disabled = off;
    cb.closest("label").classList.toggle("off", off);
  });
}

// Lanes is about the record graph and Board about the state graph, so picking
// one implies its graph rather than silently rendering an empty canvas.
function setLayout(next) {
  show.layout = next;
  const needs = LAYOUT_GRAPH[next];
  if (needs && show.graphs !== "both" && show.graphs !== needs) show.graphs = needs;
}

// Fit once per arrangement, manual afterward.
function rerender() {
  renderAll();
  const k = layoutKey();
  if (!fitDone[k]) { fit(); fitDone[k] = true; }
}

function applyPreset(name) {
  Object.assign(show, PRESETS[name]);
  syncControls();
  rerender();
}

document.getElementById("controls").addEventListener("click", e => {
  const chip = e.target.closest("#presets button");
  if (chip) { applyPreset(chip.dataset.preset); return; }
  const segBtn = e.target.closest(".seg button");
  if (segBtn) {
    const key = segBtn.closest(".seg").dataset.key;
    if (show[key] !== segBtn.dataset.val) {
      if (key === "layout") setLayout(segBtn.dataset.val);
      else show[key] = segBtn.dataset.val;
      syncControls();
      rerender();
    }
  }
});
document.querySelectorAll("#toggles .checks input").forEach(cb =>
  cb.addEventListener("change", () => {
    show[cb.dataset.key] = cb.checked;
    syncControls();
    rerender();
  }));

// ----------------------------------------------------- resizable sidebar
const side = document.getElementById("side");
const divider = document.getElementById("divider");
let sideWidth = 400, sideCollapsed = false;
function applySide() {
  side.style.width = sideCollapsed ? "0px" : sideWidth + "px";
  divider.classList.toggle("collapsed", sideCollapsed);
}
let sideDrag = null;
divider.addEventListener("pointerdown", e => {
  sideDrag = { sx: e.clientX, moved: false };
  divider.setPointerCapture(e.pointerId);
});
divider.addEventListener("pointermove", e => {
  if (!sideDrag) return;
  if (Math.abs(e.clientX - sideDrag.sx) > 3) sideDrag.moved = true;
  if (!sideDrag.moved) return;
  const w = window.innerWidth - e.clientX - 3;
  if (w < 140) sideCollapsed = true;
  else { sideCollapsed = false; sideWidth = Math.min(640, Math.max(240, w)); }
  applySide();
});
divider.addEventListener("pointerup", () => {
  if (sideDrag && !sideDrag.moved) {  // click (incl. the chevron): toggle
    sideCollapsed = !sideCollapsed;
    applySide();
  }
  sideDrag = null;
});

document.getElementById("fitBtn").addEventListener("click", fit);
document.getElementById("themeBtn").addEventListener("click", () => {
  theme = theme === "light" ? "dark" : "light";
  document.body.dataset.theme = theme;  // also swaps the sun/moon icon via CSS
  renderAll();
  renderPanel();
});

const exportMenu = document.getElementById("exportMenu");
document.getElementById("exportBtn").addEventListener("click", e => {
  e.stopPropagation();
  exportMenu.hidden = !exportMenu.hidden;
});
document.addEventListener("click", e => {
  if (!exportMenu.hidden && !(e.target.closest && e.target.closest("#exportWrap")))
    exportMenu.hidden = true;
});
document.getElementById("printBtn").addEventListener("click", () => {
  exportMenu.hidden = true;
  fit();
  setTimeout(() => window.print(), 60);
});
document.getElementById("svgBtn").addEventListener("click", () => {
  exportMenu.hidden = true;
  let { minX, minY, maxX, maxY } = worldBounds();
  if (minX > maxX) return;
  if (show.layout === "layered" && show.graphs === "both") minY -= 80;  // headers
  const pad = 40;
  const w = maxX - minX + pad * 2, h = maxY - minY + pad * 2;
  const out = el("svg", { xmlns: SVGNS, width: w, height: h,
    viewBox: `${minX - pad} ${minY - pad} ${w} ${h}`, "font-family": FONT });
  out.appendChild(el("rect", { x: minX - pad, y: minY - pad, width: w, height: h,
    fill: T().page }));
  out.appendChild(markerDefs());
  const world = document.getElementById("world").cloneNode(true);
  world.removeAttribute("transform");
  out.appendChild(world);
  const blob = new Blob([new XMLSerializer().serializeToString(out)],
    { type: "image/svg+xml" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${DATA.project}-${activePreset() || "custom"}.svg`;
  a.click();
  URL.revokeObjectURL(a.href);
});

// -------------------------------------------------------------------- live
// `viz --live` writes a sibling JSON file and sets DATA.live. The page then
// re-reads that file on an interval and pulses whatever is new.
//
// This is the one feature that breaks the page's self-contained property, which
// is why it exists only when the flag asked for it: without DATA.live not a byte
// of network code runs, and the default output still fetches nothing.
//
// Browsers refuse cross-file fetch from file://, so a live page has to be served
// over http. Rather than fail silently, the indicator says so and polling stops.

const LIVE_MAX_FAILS = 3;
const PULSE_MS = 1800;

function liveSignature(data) {
  // Cheap and sufficient: what exists, and when the graphs were exported.
  return [data.record.nodes.length, data.state.nodes.length, data.links.length,
          data.record.exported_at, data.state.exported_at,
          data.reconciliation.high_water_mark].join("|");
}

function liveStatus(text, tone) {
  const box = document.getElementById("live");
  if (!box) return;
  box.hidden = false;
  box.dataset.tone = tone;
  box.querySelector("span").textContent = text;
}

// A ring drawn around the node and faded out with SMIL — no CSS, so it works the
// same way in the exported SVG, and no timers that could outlive a re-render.
function pulseNode(slug) {
  const g = nodeEls[slug];
  if (!g) return;
  const d = dimsOf(slug), pad = 7;
  const circle = styleFor(bySlug[slug]) === "circle";
  const ring = el("rect", {
    x: (circle ? -d.w / 2 : 0) - pad, y: (circle ? -d.h / 2 : 0) - pad,
    width: d.w + pad * 2, height: d.h + pad * 2, rx: 12,
    fill: "none", stroke: T().status.open, "stroke-width": 3,
    "pointer-events": "none",
  });
  ring.appendChild(el("animate", { attributeName: "opacity", from: 0.95, to: 0,
    dur: (PULSE_MS / 1000) + "s", fill: "freeze" }));
  g.appendChild(ring);
  setTimeout(() => ring.remove(), PULSE_MS + 200);
}

// Swap in a fresh payload. Everything derived from DATA has to be dropped, and
// the list is the point: a cache that survives a data swap is a stale drawing
// that looks live.
function adoptData(fresh) {
  const before = new Set(Object.keys(bySlug));
  DATA.record = fresh.record;
  DATA.state = fresh.state;
  DATA.links = fresh.links;
  DATA.reconciliation = fresh.reconciliation;
  for (const slug in bySlug) delete bySlug[slug];
  DATA.record.nodes.forEach(n => bySlug[n.slug] = { graph: "record", node: n });
  DATA.state.nodes.forEach(n => bySlug[n.slug] = { graph: "state", node: n });
  _hyper = null;
  _spineRank = null;
  registerPucks();
  // A claim that no longer exists cannot stay collapsed.
  [...collapsed].forEach(st => { if (!bySlug[st]) collapsed.delete(st); });
  blobCache.clear();
  for (const k in positions) delete positions[k];   // layouts depend on the data
  if (selected && !bySlug[selected]) selected = null;
  hovered = null;
  renderAll();
  renderPanel();
  const added = Object.keys(bySlug).filter(s => !before.has(s));
  added.forEach(pulseNode);
  return added.length;
}

function startLive() {
  if (!DATA.live) return;
  let signature = liveSignature(DATA), fails = 0, timer = null;
  liveStatus("live", "ok");

  const poll = () => {
    // Cache-bust with the signature we already have: no clock is read, so the
    // page stays deterministic under test.
    fetch(DATA.live.url + "?v=" + encodeURIComponent(signature), { cache: "no-store" })
      .then(r => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
      .then(fresh => {
        fails = 0;
        const next = liveSignature(fresh);
        if (next === signature) { liveStatus("live", "ok"); return; }
        signature = next;
        const added = adoptData(fresh);
        liveStatus(added ? "+" + added + " new" : "updated", "new");
      })
      .catch(err => {
        if (++fails < LIVE_MAX_FAILS) { liveStatus("live · retrying", "warn"); return; }
        clearInterval(timer);
        liveStatus("live off — serve over http", "warn");
        console.warn("[hypergraph] live polling stopped:", err.message);
      });
  };
  timer = setInterval(poll, Math.max(1000, DATA.live.interval_ms || 5000));
}

// -------------------------------------------------------------------- boot
// Deep links: #timeline | #frontier | #provenance | #clusters selects that view
// (the pre-rename hashes #record #state #combo #combination #hyper still work,
// see VIEW_ALIASES); #<slug> jumps to a node.
document.body.dataset.theme = theme;
applySide();
registerPucks();   // synthetic entries for collapsed hyperedges
const boot = decodeURIComponent(location.hash.slice(1));
const bootView = VIEW_ALIASES[boot] || boot;
applyPreset(PRESETS[bootView] ? bootView : "clusters");
if (bySlug[boot]) jumpTo(boot);
renderPanel();
startLive();   // no-op unless `viz --live` set DATA.live
})();
</script>
</body>
</html>
"""
# --- END ---


# -------------------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hypergraph.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="validate protocol invariants over graph exports")
    p_check.add_argument("--record", type=Path, required=True, help="record-graph export JSON")
    p_check.add_argument("--state", type=Path, required=True, help="state-graph export JSON")
    p_check.add_argument("--config", type=Path, help=".hypergraph/config.yml")
    p_check.set_defaults(func=cmd_check)

    p_render = sub.add_parser("render", help="render STATE.md from a state-graph export")
    p_render.add_argument("--state", type=Path, required=True, help="state-graph export JSON")
    p_render.add_argument("--config", type=Path, help=".hypergraph/config.yml")
    p_render.add_argument("-o", "--output", type=Path, help="output path (default: stdout)")
    p_render.set_defaults(func=cmd_render)

    p_viz = sub.add_parser("viz", help="emit a self-contained interactive HTML visualization")
    p_viz.add_argument("--record", type=Path, required=True, help="record-graph export JSON")
    p_viz.add_argument("--state", type=Path, required=True, help="state-graph export JSON")
    p_viz.add_argument("--config", type=Path, help=".hypergraph/config.yml")
    p_viz.add_argument("-o", "--output", type=Path, help="output path (default: stdout)")
    p_viz.add_argument("--format", choices=["html", "excaligraph"], default="html",
                       help="html: the self-contained interactive page (default). "
                            "excaligraph: a YAML graph spec for `excaligraph build`, "
                            "for hand-editable excalidraw figures (needs node, "
                            "separately installed; this tool never shells out)")
    p_viz.add_argument("--links", choices=["none", "provenance", "impact", "all"],
                       default="none",
                       help="excaligraph only: which cross-graph edges to draw. "
                            "Default none — the impact relation is already the blob "
                            "membership, and 177 edges over 51 nodes is a hairball "
                            "in a figure just as it is on the page")
    p_viz.add_argument("--live", action="store_true",
                       help="also write a sibling <output>.data.json and have the page "
                            "poll it, pulsing nodes that appeared since the last poll. "
                            "This deliberately breaks the single-file property, which "
                            "is why it is a flag: serve the directory over http, "
                            "because browsers block fetch from file://")
    p_viz.add_argument("--live-interval", type=int, default=5, metavar="SECONDS",
                       help="how often the live page re-reads the data (default: 5)")
    p_viz.add_argument("--dev", action="store_true",
                       help="assemble the page from tools/viz/ instead of the bundled "
                            "constant (repo checkout only; no rebundle needed to iterate)")
    p_viz.set_defaults(func=cmd_viz)

    # ---- local (git-native) backend: backend/local-adapter.md
    def graph_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", type=Path, help=".hypergraph/config.yml")
        p.add_argument("--graph-dir", type=Path,
                       help=f"node-file root (default: {DEFAULT_GRAPH_DIR})")

    p_export = sub.add_parser("export", help="emit record.json/state.json from local node files")
    graph_args(p_export)
    p_export.add_argument("--out-dir", type=Path,
                          help=f"where to write the exports (default: {DEFAULT_CACHE_DIR})")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="explode graph export JSON into local node files")
    graph_args(p_import)
    p_import.add_argument("--record", type=Path, help="record-graph export JSON")
    p_import.add_argument("--state", type=Path, help="state-graph export JSON")
    p_import.add_argument("--force", action="store_true", help="overwrite differing node files")
    p_import.add_argument("--fork", action="store_true",
                          help="adoption: record the source ids under `origin:` and omit "
                               "`flywheel:`, so push re-publishes the history to a mirror "
                               "this project owns")
    p_import.set_defaults(func=cmd_import)

    p_new = sub.add_parser("new", help="author a new record or state node file")
    p_new.add_argument("kind", choices=list(GRAPH_KINDS))
    graph_args(p_new)
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--body", help="markdown body file, or `-` for stdin")
    p_new.add_argument("--summary", default="")
    p_new.add_argument("--parent", action="append", metavar="SLUG",
                       help="causal parent slug (repeatable)")
    p_new.add_argument("--root", action="store_true", help="parentless graph root")
    p_new.add_argument("--slug", help="explicit slug (default: minted adjective-noun-####)")
    p_new.add_argument("--created-at", help="ISO-8601 timestamp (default: now, UTC)")
    p_new.add_argument("--impact", action="append", metavar="'SLUG — delta'",
                       help="record only: a `## State Impact` line (repeatable)")
    p_new.add_argument("--none", metavar="REASON",
                       help="record only: declare no state change (SPEC I2)")
    p_new.add_argument("--repo-auto", action="store_true",
                       help="record only: fill `## Repo` from local git")
    p_new.add_argument("--status", help="state only: working|open|broken|blocked|superseded")
    p_new.add_argument("--prov", action="append", metavar="'SLUG — why'",
                       help="state only: a `## Provenance` line (repeatable)")
    p_new.add_argument("--neg", action="append", metavar="'[scope: … | confidence: … | evidence: …] stmt'",
                       help="state only: a negative-knowledge entry (repeatable)")
    p_new.add_argument("--hwm", help="state root only: initial high_water_mark (default: none)")
    p_new.add_argument("--reconcile", action="store_true",
                       help="required for state nodes: assert this is a reconcile pass (SPEC I3)")
    p_new.set_defaults(func=cmd_new)

    p_update = sub.add_parser("update", help="replace a state node's body (reconcile only)")
    p_update.add_argument("slug")
    graph_args(p_update)
    p_update.add_argument("--body", help="new full markdown body, or `-` for stdin")
    p_update.add_argument("--title")
    p_update.add_argument("--summary")
    p_update.add_argument("--expect", help="sha256 of the body you read (optimistic lock)")
    p_update.add_argument("--print-sha", action="store_true",
                          help="print the current body sha256 and exit (the read half of the CAS)")
    p_update.add_argument("--reconcile", action="store_true",
                          help="required: assert this is a reconcile pass (SPEC I3)")
    p_update.set_defaults(func=cmd_update)

    p_skills = sub.add_parser("skills", help="manage the shipped Claude skills")
    p_skills.add_argument("action", choices=["install"],
                          help="install: copy the five hypergraph-* skills")
    p_skills.add_argument("--user", action="store_true",
                          help="install into ~/.claude/skills (default: ./.claude/skills)")
    p_skills.add_argument("--target", type=Path, metavar="DIR",
                          help="explicit destination directory")
    p_skills.set_defaults(func=cmd_skills)

    p_push = sub.add_parser("push", help="plan/record a Flywheel mirror push (no network)")
    graph_args(p_push)
    p_push.add_argument("--plan", action="store_true", help="emit the ordered push plan")
    p_push.add_argument("--record-result", type=Path, metavar="RESULTS.JSON",
                        help="fold executed-push ids back into the node frontmatter")
    p_push.add_argument("--verify", action="store_true",
                        help="read-only drift check against a fresh mirror export (exit 1 on drift)")
    p_push.add_argument("--against", type=Path, metavar="EXPORT.JSON",
                        help="the mirror export to verify against")
    p_push.add_argument("--legend", action="store_true",
                        help="emit the mirror-only slug-legend node body")
    p_push.add_argument("--lineage", action="store_true",
                        help="emit the archive-lineage body for the mirror record root "
                             "(needs an `archive:` block in the config)")
    p_push.add_argument("-o", "--output", type=Path, help="plan output path (default: stdout)")
    p_push.set_defaults(func=cmd_push)

    args = parser.parse_args(argv)
    if getattr(args, "command", None) == "push" and not (
            args.plan or args.record_result or args.verify or args.legend or args.lineage):
        parser.error("push needs --plan, --record-result, --verify, --legend, or --lineage")
    if getattr(args, "command", None) == "import" and not (args.record or args.state):
        parser.error("import needs --record and/or --state")
    if getattr(args, "command", None) == "update" and not args.print_sha:
        if not args.body:
            parser.error("update needs --body (or --print-sha)")
        if not args.expect:
            parser.error("update needs --expect <sha256> — get it with --print-sha first")
    try:
        return args.func(args)
    except LocalGraphError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
