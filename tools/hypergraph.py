#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Hypergraph protocol tooling: invariant checker + STATE.md renderer.

Consumes JSON graph exports (backend `export_graph`, e.g. flywheel_export_subgraph
saved to .hypergraph/cache/{record,state}.json). No network, no auth, deterministic.

    hypergraph.py check  --record record.json --state state.json [--config config.yml]
    hypergraph.py render --state state.json [--config config.yml] [-o STATE.md]
    hypergraph.py viz    --record record.json --state state.json [--config config.yml] [-o viz.html]

check exits 1 on any I2/I4/I5/I6/I7 violation (see SPEC.md). Warnings (I1 proxies)
and info lines never affect the exit code. viz emits a self-contained interactive
HTML file (no network, no JS dependencies) with record, state, and combined
hypergraph views; open it directly in a browser.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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

def check_impacts(record: Graph, state: Graph, record_root: Node | None, report: Report) -> None:
    """I2: every non-root record node declares parseable state impact."""
    for node in record.nodes.values():
        if record_root and node.node_id == record_root.node_id:
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


def run_check(record_path: Path, state_path: Path, config: dict | None = None) -> Report:
    config = config or {}
    report = Report()
    record = load_graph(record_path)
    state = load_graph(state_path)
    record_root = find_root(record, config.get("record_root"), report, "record")
    state_root = find_root(state, config.get("state_root"), report, "state")
    check_impacts(record, state, record_root, report)
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
        if not is_root:
            for slug in sorted(set(SLUG_RE.findall(COMMENT_RE.sub("", node.content)))):
                if slug in record.by_slug:
                    add_link(slug, node.ref, "provenance", prov_notes.get(slug, ""))
        status = None if is_root else node_status(node)
        ly, od = st_layout[node.node_id]
        state_nodes.append({
            "slug": node.ref, "title": node.title, "created_at": node.created_at,
            "parents": [id_to_slug["state"][p] for p in node.parent_ids
                        if p in id_to_slug["state"]],
            "content": node.content, "is_root": is_root,
            "status": status, "frontier": bool(status in FRONTIER),
            "layer": ly, "order": od, "seq": seq,
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


def _esc_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_viz(record_path: Path, state_path: Path, config: dict | None = None) -> str:
    record = load_graph(record_path)
    state = load_graph(state_path)
    data = build_viz_data(record, state, config)
    for path, key in ((record_path, "record"), (state_path, "state")):
        try:
            raw = json.loads(Path(path).read_text())
            if isinstance(raw, dict):
                data[key]["exported_at"] = raw.get("exported_at")
        except (OSError, json.JSONDecodeError):
            pass
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return (VIZ_TEMPLATE
            .replace("__TITLE__", _esc_html(data["project"]))
            .replace("__VIZ_DATA__", payload))


def cmd_viz(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output = render_viz(args.record, args.state, config)
    if args.output:
        Path(args.output).write_text(output)
        print(f"wrote {args.output}")
    else:
        print(output)
    return 0


# Self-contained page: no network requests, no JS dependencies. All SVG styling is
# via attributes (not CSS classes) so the "Download SVG" export is standalone.
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
  header { display:flex; align-items:center; gap:10px; padding:8px 14px; flex:none;
           background:var(--surface); border-bottom:1px solid var(--grid); }
  header h1 { font-size:14px; font-weight:650; white-space:nowrap; }
  header h1 span { color:var(--muted); font-weight:500; }
  .tabs { display:flex; background:var(--page); border:1px solid var(--grid);
          border-radius:8px; padding:2px; }
  .tabs button { border:0; background:transparent; color:var(--ink2); font:inherit;
                 font-size:12.5px; padding:4px 12px; border-radius:6px; cursor:pointer; }
  .tabs button.active { background:var(--surface); color:var(--ink); font-weight:600;
                        box-shadow:0 0 0 1px var(--border); }
  #search { flex:0 1 230px; margin-left:auto; font:inherit; font-size:12.5px;
            padding:5px 10px; border-radius:8px; border:1px solid var(--grid);
            background:var(--page); color:var(--ink); outline:none; min-width:80px; }
  #search:focus { border-color:var(--accent); }
  .btn { border:1px solid var(--grid); background:var(--surface); color:var(--ink2);
         font:inherit; font-size:12.5px; padding:4px 10px; border-radius:8px;
         cursor:pointer; white-space:nowrap; }
  .btn:hover { color:var(--ink); border-color:var(--muted); }
  main { flex:1; display:flex; min-height:0; }
  #canvas { flex:1; position:relative; min-width:0; }
  #svg { position:absolute; inset:0; width:100%; height:100%; display:block;
         cursor:grab; background:var(--page); }
  #svg.dragging { cursor:grabbing; }
  #panel { width:400px; flex:none; background:var(--surface);
           border-left:1px solid var(--grid); overflow-y:auto; padding:16px 18px;
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
  .legend-swatch { display:inline-block; width:22px; height:0; border-top-width:2px;
                   border-top-style:solid; vertical-align:middle; margin-right:8px; }
  .hint { color:var(--muted); font-size:11.5px; margin-top:16px; }
  .stats td { padding:1px 10px 1px 0; color:var(--ink2); font-size:12px; }
  .stats td:first-child { color:var(--muted); }
  @media (max-width: 900px) { #panel { width: 300px; } }
  @media print {
    header, #panel { display:none !important; }
    body { background:#fff; }
    #canvas { position:fixed; inset:0; }
  }
</style>
</head>
<body>
<header>
  <h1>__TITLE__ <span>· hypergraph</span></h1>
  <div class="tabs" id="tabs">
    <button data-view="record">Record</button>
    <button data-view="state">State</button>
    <button data-view="hyper" class="active">Hypergraph</button>
  </div>
  <input id="search" type="search" placeholder="Filter: slug, title, content…">
  <button class="btn" id="fitBtn" title="Fit graph to window">Fit</button>
  <button class="btn" id="themeBtn" title="Toggle light/dark">Theme</button>
  <button class="btn" id="svgBtn" title="Download current view as SVG">SVG</button>
  <button class="btn" id="printBtn" title="Print / save as PDF">PDF</button>
</header>
<main>
  <div id="canvas"><svg id="svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
  <aside id="panel"></aside>
</main>
<script>
"use strict";
const DATA = __VIZ_DATA__;

const THEMES = {
  light: { surface:"#fcfcfb", page:"#f9f9f7", ink:"#0b0b0b", ink2:"#52514e",
    muted:"#898781", grid:"#e1e0d9", axis:"#c3c2b7", border:"rgba(11,11,11,0.10)",
    status:{ working:"#0ca30c", open:"#2a78d6", broken:"#d03b3b",
             blocked:"#fab219", superseded:"#898781" },
    prov:"#2a78d6", impact:"#eb6834", hwm:"#4a3aa7", unrec:"#fab219" },
  dark: { surface:"#1a1a19", page:"#0d0d0d", ink:"#ffffff", ink2:"#c3c2b7",
    muted:"#898781", grid:"#2c2c2a", axis:"#383835", border:"rgba(255,255,255,0.10)",
    status:{ working:"#0ca30c", open:"#3987e5", broken:"#d03b3b",
             blocked:"#fab219", superseded:"#898781" },
    prov:"#3987e5", impact:"#d95926", hwm:"#9085e9", unrec:"#fab219" },
};
const SVGNS = "http://www.w3.org/2000/svg";
const NW = 236, NH = 62;
const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";
const SLUG_JS = /\b[a-z][a-z0-9]*-[a-z][a-z0-9]*-[0-9]{4}\b/g;

const bySlug = {};
DATA.record.nodes.forEach(n => bySlug[n.slug] = { graph: "record", node: n });
DATA.state.nodes.forEach(n => bySlug[n.slug] = { graph: "state", node: n });

let view = "hyper";
let theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
let selected = null, query = "";
const tf = { record:{x:0,y:0,k:1}, state:{x:0,y:0,k:1}, hyper:{x:0,y:0,k:1} };
const positions = { record:null, state:null, hyper:null };
const fitDone = { record:false, state:false, hyper:false };
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
function computeLayout(v) {
  const pos = {};
  if (v === "record" || v === "state") {
    const perLayer = {};
    DATA[v].nodes.forEach(n => (perLayer[n.layer] = perLayer[n.layer] || []).push(n));
    DATA[v].nodes.forEach(n => {
      const width = perLayer[n.layer].length;
      pos[n.slug] = { x: (n.order - (width - 1) / 2) * (NW + 70),
                      y: n.layer * (NH + 78) };
    });
  } else {
    const gap = 430;
    DATA.record.nodes.forEach(n => pos[n.slug] = { x: 0, y: n.seq * (NH + 30) });
    DATA.state.nodes.forEach(n => pos[n.slug] = { x: NW + gap, y: n.seq * (NH + 46) });
  }
  return pos;
}

function edgesFor(v) {
  const out = [];
  const tree = (g, side) => DATA[g].nodes.forEach(n =>
    n.parents.forEach(p => out.push({ kind:"tree", from:p, to:n.slug, side })));
  if (v === "record") tree("record", null);
  else if (v === "state") tree("state", null);
  else {
    tree("record", "left");
    tree("state", "right");
    DATA.links.forEach(l => out.push({
      kind: l.kind, label: l.label,
      from: l.kind === "impact" ? l.record : l.state,
      to:   l.kind === "impact" ? l.state : l.record,
    }));
  }
  return out;
}

function edgePath(e, pos) {
  const a = pos[e.from], b = pos[e.to];
  if (!a || !b) return null;
  if (e.kind === "tree" && !e.side) {
    const y1 = a.y + NH / 2, y2 = b.y - NH / 2, ym = (y1 + y2) / 2;
    return `M ${a.x} ${y1} C ${a.x} ${ym}, ${b.x} ${ym}, ${b.x} ${y2}`;
  }
  if (e.kind === "tree") {
    const dir = e.side === "left" ? -1 : 1;
    const x = a.x + dir * NW / 2, x2 = b.x + dir * NW / 2;
    const off = 26 + 0.055 * Math.abs(b.y - a.y);
    return `M ${x} ${a.y} C ${x + dir * off} ${a.y}, ${x2 + dir * off} ${b.y}, ${x2} ${b.y}`;
  }
  const fromState = bySlug[e.from].graph === "state";
  const x1 = a.x + (fromState ? -NW / 2 : NW / 2);
  const x2 = b.x + (bySlug[e.to].graph === "state" ? -NW / 2 : NW / 2);
  const cx = (x1 + x2) / 2;
  return `M ${x1} ${a.y} C ${cx} ${a.y}, ${cx} ${b.y}, ${x2} ${b.y}`;
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

function drawNode(entry, pos) {
  const { graph, node } = entry;
  const p = pos[node.slug];
  const g = el("g", { class: "node", "data-slug": node.slug, cursor: "pointer",
                      transform: `translate(${p.x - NW / 2},${p.y - NH / 2})` });
  const frontier = graph === "state" && node.frontier;
  g.appendChild(el("rect", { x: .5, y: .5, width: NW - 1, height: NH - 1, rx: 9,
    fill: T().surface, stroke: frontier ? accentFor(entry) : T().border,
    "stroke-width": frontier ? 1.4 : 1 }));
  g.appendChild(el("rect", { x: 3, y: 7, width: 4, height: NH - 14, rx: 2,
    fill: accentFor(entry) }));
  g.appendChild(el("text", { x: 16, y: 21, "font-family": FONT, "font-size": 12.5,
    "font-weight": node.is_root ? 700 : 600, fill: T().ink }, trunc(node.title, 32)));
  g.appendChild(el("text", { x: 16, y: 36.5, "font-family": MONO, "font-size": 10.5,
    fill: T().muted }, node.slug));
  let x = 16;
  const meta = (text, color, bold) => {
    const t = el("text", { x, y: 52, "font-family": FONT, "font-size": 10.5,
      fill: color, "font-weight": bold ? 650 : 400 }, text);
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

function renderAll() {
  if (!positions[view]) positions[view] = computeLayout(view);
  const pos = positions[view];
  svg.textContent = "";
  svg.appendChild(markerDefs());
  const world = el("g", { id: "world" });
  svg.appendChild(world);
  const edgeLayer = el("g", { id: "edges" });
  const nodeLayer = el("g", { id: "nodes" });
  world.appendChild(edgeLayer);
  world.appendChild(nodeLayer);

  if (view === "hyper") {
    const head = (text, x, anchor) => nodeLayer.appendChild(el("text", { x, y: -64,
      "font-family": FONT, "font-size": 12, "font-weight": 700, fill: T().muted,
      "letter-spacing": "0.08em", "text-anchor": anchor }, text));
    head("RECORD — " + DATA.record.nodes.length + " nodes (append-only log)", 0, "middle");
    head("STATE — " + DATA.state.nodes.length + " nodes (distilled now)",
         NW + 430, "middle");
  }

  edges = edgesFor(view);
  edgeEls = [];
  edges.forEach(e => {
    const d = edgePath(e, pos);
    if (!d) { edgeEls.push(null); return; }
    const style = e.kind === "tree"
      ? { stroke: T().axis, marker: "arrow-tree", dash: null, op: 0.9, w: 1.4 }
      : e.kind === "impact"
        ? { stroke: T().impact, marker: "arrow-imp", dash: "6 4", op: 0.8, w: 1.6 }
        : { stroke: T().prov, marker: "arrow-prov", dash: null, op: 0.65, w: 1.6 };
    const path = el("path", { d, fill: "none", stroke: style.stroke,
      "stroke-width": style.w, opacity: style.op,
      "marker-end": `url(#${style.marker})` });
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
    const gEl = drawNode(bySlug[n.slug], pos);
    nodeLayer.appendChild(gEl);
    nodeEls[n.slug] = gEl;
  });
  if (view === "record") draw("record");
  else if (view === "state") draw("state");
  else { draw("record"); draw("state"); }

  applyTf();
  updateDim();
}

function applyTf() {
  const t = tf[view];
  const world = document.getElementById("world");
  if (world) world.setAttribute("transform", `translate(${t.x},${t.y}) scale(${t.k})`);
}

// ------------------------------------------------------- dim / select / search
function neighborhood(slug) {
  const rel = new Set([slug]);
  edges.forEach(e => {
    if (e.from === slug) rel.add(e.to);
    if (e.to === slug) rel.add(e.from);
  });
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
    const box = nodeEls[slug].firstChild;
    const frontier = entry.graph === "state" && entry.node.frontier;
    box.setAttribute("stroke", slug === selected ? T().ink
      : frontier ? accentFor(entry) : T().border);
    box.setAttribute("stroke-width", slug === selected ? 1.8 : frontier ? 1.4 : 1);
  }
  edges.forEach((e, i) => {
    const pathEl = edgeEls[i];
    if (!pathEl) return;
    const on = vis[e.from] && vis[e.to] &&
      (!rel || e.from === selected || e.to === selected);
    pathEl.setAttribute("opacity", on ? pathEl.dataset.op : 0.08);
  });
}

function select(slug) { selected = slug; updateDim(); renderPanel(); }
function deselect() { selected = null; updateDim(); renderPanel(); }

function jumpTo(slug) {
  const entry = bySlug[slug];
  if (!entry) return;
  if (view !== "hyper" && view !== entry.graph) setView("hyper");
  select(slug);
  const p = positions[view][slug];
  const t = tf[view], r = svg.getBoundingClientRect();
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
    <p class="hint">Scroll to zoom · drag background to pan · drag nodes to rearrange ·
    click a node for full content · Esc to deselect. Use SVG/PDF for static exports.</p>`;
}

function bindPanel() {
  panel.querySelectorAll("a.slug").forEach(a =>
    a.addEventListener("click", () => jumpTo(a.dataset.slug)));
}

// -------------------------------------------------------------- interaction
let drag = null;
svg.addEventListener("pointerdown", e => {
  const nodeG = e.target.closest ? e.target.closest(".node") : null;
  if (nodeG) {
    const slug = nodeG.dataset.slug;
    const p = positions[view][slug];
    drag = { type: "node", slug, sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y, moved: false };
  } else {
    drag = { type: "pan", sx: e.clientX, sy: e.clientY,
             ox: tf[view].x, oy: tf[view].y, moved: false };
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
    tf[view].x = drag.ox + dx;
    tf[view].y = drag.oy + dy;
    applyTf();
  } else {
    const p = positions[view][drag.slug];
    p.x = drag.ox + dx / tf[view].k;
    p.y = drag.oy + dy / tf[view].k;
    nodeEls[drag.slug].setAttribute("transform",
      `translate(${p.x - NW / 2},${p.y - NH / 2})`);
    edges.forEach((eg, i) => {
      if (!edgeEls[i]) return;
      if (eg.from === drag.slug || eg.to === drag.slug)
        edgeEls[i].setAttribute("d", edgePath(eg, positions[view]));
    });
  }
});
svg.addEventListener("pointerup", e => {
  svg.classList.remove("dragging");
  if (!drag) return;
  if (!drag.moved) {
    if (drag.type === "node") select(drag.slug);
    else deselect();
  }
  drag = null;
});
svg.addEventListener("wheel", e => {
  e.preventDefault();
  const t = tf[view], r = svg.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const k2 = Math.min(2.5, Math.max(0.1, t.k * Math.exp(-e.deltaY * 0.0016)));
  t.x = mx - (mx - t.x) * (k2 / t.k);
  t.y = my - (my - t.y) * (k2 / t.k);
  t.k = k2;
  applyTf();
}, { passive: false });
document.addEventListener("keydown", e => { if (e.key === "Escape") deselect(); });

document.getElementById("search").addEventListener("input", e => {
  query = e.target.value.trim().toLowerCase();
  updateDim();
});

function fit() {
  const pos = positions[view];
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  for (const slug in pos) {
    if (!nodeEls[slug]) continue;
    minX = Math.min(minX, pos[slug].x - NW / 2);
    maxX = Math.max(maxX, pos[slug].x + NW / 2);
    minY = Math.min(minY, pos[slug].y - NH / 2);
    maxY = Math.max(maxY, pos[slug].y + NH / 2);
  }
  if (minX > maxX) return;
  if (view === "hyper") minY -= 60;  // column headers
  const r = svg.getBoundingClientRect(), pad = 50;
  const t = tf[view];
  t.k = Math.min(1.25, (r.width - pad * 2) / (maxX - minX),
                 (r.height - pad * 2) / (maxY - minY));
  t.x = (r.width - (maxX + minX) * t.k) / 2;
  t.y = (r.height - (maxY + minY) * t.k) / 2;
  applyTf();
}

function setView(v) {
  view = v;
  document.querySelectorAll("#tabs button").forEach(b =>
    b.classList.toggle("active", b.dataset.view === v));
  renderAll();
  if (!fitDone[v]) { fit(); fitDone[v] = true; }
}
document.querySelectorAll("#tabs button").forEach(b =>
  b.addEventListener("click", () => setView(b.dataset.view)));

document.getElementById("fitBtn").addEventListener("click", fit);
document.getElementById("themeBtn").addEventListener("click", () => {
  theme = theme === "light" ? "dark" : "light";
  document.body.dataset.theme = theme;
  renderAll();
  renderPanel();
});
document.getElementById("printBtn").addEventListener("click", () => {
  fit();
  setTimeout(() => window.print(), 60);
});
document.getElementById("svgBtn").addEventListener("click", () => {
  const pos = positions[view];
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  for (const slug in pos) {
    if (!nodeEls[slug]) continue;
    minX = Math.min(minX, pos[slug].x - NW / 2);
    maxX = Math.max(maxX, pos[slug].x + NW / 2);
    minY = Math.min(minY, pos[slug].y - NH / 2 - (view === "hyper" ? 80 : 0));
    maxY = Math.max(maxY, pos[slug].y + NH / 2);
  }
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
  a.download = `${DATA.project}-${view}.svg`;
  a.click();
  URL.revokeObjectURL(a.href);
});

// -------------------------------------------------------------------- boot
// Deep links: #record | #state | #hyper opens that view; #<slug> jumps to a node.
document.body.dataset.theme = theme;
const boot = decodeURIComponent(location.hash.slice(1));
setView(boot === "record" || boot === "state" ? boot : "hyper");
if (bySlug[boot]) jumpTo(boot);
renderPanel();
</script>
</body>
</html>
"""


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
    p_viz.set_defaults(func=cmd_viz)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
