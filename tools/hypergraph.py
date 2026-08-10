#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Hypergraph tooling: invariant checker, STATE.md renderer, local backend.

Hypergraph is a substrate for autonomous research and engineering — two graphs per
project, an append-only record of what happened and a single-writer projection of what
is true now, with every claim citing the evidence it rests on. This file is the whole
CLI for it (SPEC.md is the protocol).

Consumes JSON graph exports (backend `export_graph`, e.g. flywheel_export_subgraph
saved to .hypergraph/cache/{record,state}.json). No network, no auth, deterministic.

    hypergraph.py check  --record record.json --state state.json [--config config.yml]
    hypergraph.py render --state state.json [--config config.yml] [-o STATE.md]
    hypergraph.py viz    --record record.json --state state.json [--config config.yml] [-o viz.html]
                         [--format html|excaligraph] [--live] [--dev]

check exits 1 on any I2/I4/I5/I6/I7 violation (see SPEC.md). Warnings (I1 proxies)
and info lines never affect the exit code.

viz emits a self-contained interactive HTML file (no network, no JS dependencies)
with five views — Timeline (record graph as git-log lanes), Frontier (state graph
as a status board), Provenance (both graphs with cross-graph links), Clusters
(impact sets as distance-field blobs) and Everything (the default: all of it at
once). Open it straight from file://. A `viz: blob:` block in the config presets
the blob geometry the page's tuning sliders edit. The page is
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
    hypergraph.py new record|state --title T --body body.md [--tag NAME] ...
    hypergraph.py update SLUG --body new.md --expect <sha256> --reconcile
    hypergraph.py tags list|add|rm [NAME]
    hypergraph.py skills install [--user | --link | --target DIR]
    hypergraph.py heal [tags] [--apply] [--offline]

**These commands never touch the network.** No credential is resolved, no binary is
looked for, no network module is imported — the graphs are files, and that is the
whole storage story (SPEC: Storage).

One optional feature does reach out, and only when the config declares a `mirror:`
(backend/mirror.md). It publishes the committed node files to a hosted graph the
project owns, one-way, with the repo staying canonical:

    hypergraph.py push [--dry-run] [--batch N] [--limit N] [--verify]
    hypergraph.py sync                     # export → render → check → push
    hypergraph.py mirror doctor | roots [--mint] | pull --node-id … --out-dir …

`push` on a project with no mirror configured exits **0** as a no-op, so callers
never have to test the config first. `push --plan` stays network-free and emits the
ordered plan for anyone without the CLI binary.

`heal` is the other half of `upgrade`: where `upgrade` refreshes this project's
*copies* of shipped files (reversible with `git checkout`), `heal` repairs *graph
content* — a registry of typed repairs that carry a capability backwards into a repo
that adopted before it existed. It rewrites node files and may spend mirror writes
that cannot be un-spent, so it is **detect-only until `--apply`**, which is the one
inverted default in this file.
"""
from __future__ import annotations

# Kept in step with pyproject.toml's `version` by tests/test_packaging.py. It is
# duplicated rather than read from the installed metadata because this file also
# runs directly as a `uv run` script, where no distribution metadata exists.
__version__ = "0.0.8"

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
HWM_RE = re.compile(r"^-?\s*high_water_mark:\s*(?P<hwm>.+?)\s*$")
RECONCILED_AT_RE = re.compile(r"^-?\s*reconciled_at:\s*(?P<ts>\S+)\s*$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# git's merge driver, all three styles. `|||||||` is diff3's common-ancestor header.
CONFLICT_EDGE_RE = re.compile(r"^(?:<{7}|>{7}|\|{7})(?:\s|$)")
CONFLICT_MID_RE = re.compile(r"^={7}\s*$")


@dataclass
class Node:
    node_id: str
    slug: str
    title: str
    content: str
    parent_ids: list[str]
    created_at: str
    tags: list[str] = field(default_factory=list)

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
            # `tags` only — never a mirror export's `tag_ids`. Resolving those needs
            # the vocabulary, which is not in this file, and a half-resolved list
            # would read as "these nodes lost their tags".
            tags=[str(t) for t in (raw.get("tags") or [])
                  if isinstance(raw.get("tags"), list)],
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


def find_root(graph: Graph, configured: dict | None, report: Report, label: str,
              *, config_given: bool = False) -> Node | None:
    """The graph's root: configured if declared, otherwise inferred if unambiguous.

    Inference is legitimate — a freshly initialised graph has exactly one
    parentless node — but it must not be *silent* when a config was supplied and
    simply does not name the root. A stub config that declares neither root read
    as a clean pass, which is how two arm-C runs concluded their memory system was
    healthy while the checker was quietly guessing. It is a warning, not a
    violation: the guess may well be right, and a correct graph should not fail
    a check over how its roots were located.
    """
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
        if config_given:
            report.add("warning", "I5", roots[0].ref,
                       f"config declares no `{label}_root:` — inferred "
                       f"`{roots[0].slug}` as the only parentless node. Declare it "
                       "so a second root cannot silently change the answer.")
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
        # "the record root is not I2-checked" is why this can read one below the
        # number you imported. Saying so beats leaving a reader to work out whether
        # a node went missing.
        report.add("info", "I2", "-",
                   f"{exempted} pre-epoch record node(s) exempt from I2 (legacy "
                   f"history; the record root is not I2-checked, so this reads one "
                   f"below an import count that included it)")


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


def claim_units(body: str) -> list[str]:
    """Split a `## Current` section into the units that each need a citation.

    A unit is a bullet **with its wrapped continuation lines**, or a paragraph. Both,
    not either: the old rule was `bullets or paragraphs`, so a section containing any
    bullet had its prose paragraphs excluded from the check entirely — claims in them
    were never checked for citations, silently, which is the wrong direction for a
    checker to fail in. It also treated a unit as a single *line*, so a citation that
    wrapped onto the next line read as missing; that produced 27 false warnings on
    one adopted repo and taught its agent to reformat correct prose."""
    units: list[str] = []
    current: list[str] | None = None
    fenced = False
    lines = body.splitlines()

    def flush(index: int | None = None):
        """`index` is the line that ended this unit, so a lead-in can see what follows."""
        nonlocal current
        if current is None:
            return
        text = "\n".join(current)
        # "Two failures are measured rather than suspected:" introduces the bullets
        # that carry the evidence; it is punctuation for the list, not a claim of its
        # own, and demanding a citation on it teaches people to cite noise.
        lead_in = text.rstrip().endswith(":") and index is not None and any(
            ln.strip().startswith("- ") for ln in lines[index:index + 2] if ln.strip())
        if not lead_in:
            units.append(text)
        current = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            flush(i)
            fenced = not fenced
            continue
        if fenced:
            continue                          # a code block asserts nothing
        if stripped.startswith("#"):
            flush(i)
            continue                          # a heading is structure, not a claim
        if stripped.startswith("- "):
            flush(i)
            current = [stripped]
        elif not stripped:
            flush(i + 1)
        elif current is not None:
            current.append(stripped)          # a wrapped continuation of the bullet
        else:
            current = [stripped]              # a paragraph, checked like any claim
    flush()
    return [u for u in units if u.strip()]


def check_current_citations(node: Node, sections: dict[str, str], report: Report) -> None:
    """I1 proxy (warning): claim units in ## Current without an inline citation."""
    body = sections.get("current")
    if body is None:
        report.add("warning", "I1", node.ref, "no `## Current` section")
        return
    for unit in claim_units(COMMENT_RE.sub("", body)):
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


def read_hwm(state_root: Node) -> tuple[list[str] | None, str | None]:
    """→ (reconciliation frontier, reconciled_at or None).

    The frontier is the set of record tips whose ancestry has been folded into state
    (SPEC I5). `None` means the `high_water_mark:` line is absent; `[]` means it reads
    `none`, i.e. nothing has been reconciled yet. One slug — the pre-0.0.5 form, and
    still what a project with a linear record graph writes — parses as a frontier of one.

    A frontier rather than a single mark because merges make the record graph a DAG with
    several tips, and no single tip dominates the others [rec: vast-rain-4873].
    """
    _, sections = split_sections(state_root.content)
    body = sections.get("reconciliation")
    if body is None:
        return None, None
    frontier: list[str] | None = None
    ts = None
    for line in body.splitlines():
        if m := HWM_RE.match(line.strip()):
            raw = m.group("hwm").strip()
            if raw == "none":
                frontier = []
            else:
                seen: list[str] = []
                for slug in raw.replace(",", " ").split():
                    slug = slug.strip("`")
                    if slug and slug not in seen:
                        seen.append(slug)
                frontier = seen
        elif m := RECONCILED_AT_RE.match(line.strip()):
            ts = m.group("ts")
    return frontier, ts


def format_hwm(frontier: list[str] | None) -> str:
    """The `high_water_mark:` value for a frontier — the exact inverse of `read_hwm`."""
    return ", ".join(frontier) if frontier else "none"


def ancestors_of(graph: Graph, slugs: list[str]) -> set[str]:
    """Node ids reachable from `slugs` by walking parents, seeds included.

    Cycles are impossible in a causal graph but the visited set makes it safe anyway,
    and unknown slugs are skipped — the caller reports those as violations.
    """
    seen: set[str] = set()
    stack = [graph.by_slug[s].node_id for s in slugs if s in graph.by_slug]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        stack.extend(pid for pid in node.parent_ids if pid in graph.nodes)
    return seen


def unreconciled_nodes(record: Graph, frontier: list[str],
                       record_root: Node | None) -> list[Node]:
    """Record nodes whose impact has not been folded into state.

    Reachability, never wall-clock: a node authored before the last reconcile but
    merged after it is *not* an ancestor of the frontier, and enumerating by timestamp
    silently drops it [rec: vast-rain-4873].
    """
    reconciled = ancestors_of(record, frontier)
    out = []
    for node in record.nodes.values():
        if record_root and node.node_id == record_root.node_id:
            continue
        if node.node_id not in reconciled:
            out.append(node)
    return sorted(out, key=lambda n: (n.created_at, n.slug))


def suggest_frontier(record: Graph, frontier: list[str],
                     record_root: Node | None) -> list[str]:
    """The frontier that expresses, in ancestry, what the pre-0.0.5 timestamp rule
    treated as reconciled: every record node at or before the newest current mark.

    Returns the *maximal* members of that set — the ones with no child also in it —
    because listing every node would be noise. Migration aid only (`hwm --suggest`).
    """
    marks = [record.by_slug[s] for s in frontier if s in record.by_slug]
    if not marks:
        return []
    cutoff = max((m.created for m in marks if m.created is not None), default=None)
    if cutoff is None:
        return sorted({m.slug for m in marks})
    covered = {n.node_id for n in record.nodes.values()
               if n.created is not None and n.created <= cutoff
               and not (record_root and n.node_id == record_root.node_id)}
    has_covered_child = set()
    for node in record.nodes.values():
        if node.node_id in covered:
            has_covered_child.update(pid for pid in node.parent_ids)
    tips = [record.nodes[nid] for nid in covered if nid not in has_covered_child]
    return [n.slug for n in sorted(tips, key=lambda n: (n.created_at, n.slug))]


def check_hwm(record: Graph, state: Graph, record_root: Node | None,
              state_root: Node | None, report: Report) -> None:
    """I5: parseable high-water mark on the state root + unreconciled enumeration."""
    if state_root is None:
        return
    frontier, ts = read_hwm(state_root)
    if frontier is None and ts is None:
        report.add("violation", "I5", state_root.ref,
                   "state root missing `## Reconciliation` section")
        return
    if frontier is None:
        report.add("violation", "I5", state_root.ref, "missing `high_water_mark:` line")
    if not ts or parse_ts(ts) is None:
        report.add("violation", "I5", state_root.ref,
                   f"missing or unparseable `reconciled_at:` timestamp (got {ts!r})")
    if frontier is None:
        return

    unknown = [s for s in frontier if s not in record.by_slug]
    for slug in unknown:
        report.add("violation", "I5", state_root.ref,
                   f"high_water_mark `{slug}` does not resolve to a record node")
    if unknown:
        return

    unreconciled = unreconciled_nodes(record, frontier, record_root)
    report.add("info", "I5", state_root.ref,
               f"{len(unreconciled)} unreconciled record node(s) past high-water mark")

    # Migration aid. Before 0.0.5 the frontier was one slug and membership was a
    # timestamp comparison, so a merged side branch counted as reconciled without ever
    # being an ancestor. Those nodes surface here the first time a project upgrades;
    # they are not new work, and re-folding them would duplicate claims.
    marks = [record.by_slug[s] for s in frontier]
    newest = max((m.created for m in marks if m.created is not None), default=None)
    predating = [n for n in unreconciled
                 if n.created is not None and newest is not None and n.created <= newest]
    if predating:
        report.add("info", "I5", state_root.ref,
                   f"{len(predating)} of those predate the newest mark — if they were folded "
                   f"under the pre-0.0.5 timestamp rule, run `hypergraph hwm --suggest` "
                   f"and adopt the frontier it prints (SPEC I5)")
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
    """Read `.hypergraph/config.yml`, failing with an instruction rather than a stack.

    An agent on a fresh box ran `check --config .hypergraph/config.yml` before the
    config existed and got a raw `FileNotFoundError` traceback out of `read_text`.
    Nothing in it named the missing file as the problem, so the agent inferred the
    *contents* were wrong and wrote a stub — `backend: local`, no `record_root`,
    no `state_root`. `check` then reported 0 violations, which looked like a fix
    and was not: it had silently fallen back to guessing the roots. Two of three
    arm-C runs did exactly this.

    So: a missing or unparseable config says what is missing and what to do, and
    `find_root` below refuses to guess quietly.
    """
    if path is None:
        return {}
    import yaml  # deferred: PEP 723 dep, only needed when --config is passed

    path = Path(path)
    if not path.exists():
        raise SystemExit(
            f"check: no config at {path}\n"
            "  A config declares `record_root:` and `state_root:` so the checker\n"
            "  knows which node anchors each graph. Either create it (see\n"
            "  templates/config.yml) or omit --config to let the checker infer\n"
            "  the roots — it can only do that when each graph has exactly one\n"
            "  parentless node.")
    try:
        loaded = yaml.safe_load(path.read_text())
    except OSError as exc:
        raise SystemExit(f"check: cannot read {path}: {exc}") from None
    except yaml.YAMLError as exc:
        raise SystemExit(f"check: {path} is not valid YAML: {exc}") from None
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise SystemExit(
            f"check: {path} must be a YAML mapping, got {type(loaded).__name__}")
    return loaded


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


def check_legacy_backend_key(config: dict, report: Report) -> None:
    """Warn — never fail — on a pre-0.0.4 `backend:` key.

    Storage is no longer a choice (SPEC: Storage), so the key is ignored. A missing
    `backend:` used to mean `flywheel` and now means the node files, which is correct
    by construction because there is only one thing it can mean. Anything other than
    `local` names a graph that lives somewhere this tool will not read, so say so —
    but as a warning: failing someone's CI over a key the tool ignores is hostile."""
    backend = config.get("backend")
    if backend is not None and str(backend) != "local":
        report.add("warning", "-", "config",
                   f"`backend: {backend}` is ignored — the node files are the graph "
                   "(SPEC: Storage). If this project's graph still lives on a hosted "
                   "store, re-home it into the repo first: see 'Re-homing a hosted "
                   "graph into the repo' in backend/mirror.md. Then drop the key.")


def check_conflict_markers(graph: Graph, report: Report) -> None:
    """Reject node content that git's merge driver wrote and nobody resolved.

    Every other check validates what an author meant. This one validates that an author
    was involved at all: a body carrying `<<<<<<< HEAD` parses cleanly, satisfies every
    invariant, commits, and is then published to an append-only mirror [rec: vast-rain-4873].

    `<<<<<<<` and `>>>>>>>` are unambiguous — no markdown construct starts a line that
    way. A bare `=======` is *not*: it is also a setext H1 underline, so it is reported
    only inside a node that already shows a real marker.
    """
    for node in graph.nodes.values():
        lines = node.content.splitlines()
        hard = [(i, ln) for i, ln in enumerate(lines, 1)
                if CONFLICT_EDGE_RE.match(ln)]
        if not hard:
            continue
        mid = [i for i, ln in enumerate(lines, 1) if CONFLICT_MID_RE.match(ln)]
        where = ", ".join(f"line {i}" for i, _ in hard[:3]) + ("…" if len(hard) > 3 else "")
        report.add("violation", "-", node.ref,
                   f"unresolved git conflict marker ({where}"
                   + (f"; separator at line {mid[0]}" if mid else "")
                   + f"): {hard[0][1].strip()[:40]!r}. Resolve the merge before recording — "
                     "a record node is immutable once published, so this would be permanent.")


def run_check(record_path: Path, state_path: Path, config: dict | None = None,
              *, config_given: bool | None = None) -> Report:
    if config_given is None:
        config_given = bool(config)
    config = config or {}
    report = Report()
    record = load_graph(record_path)
    state = load_graph(state_path)
    record_root = find_root(record, config.get("record_root"), report, "record",
                            config_given=config_given)
    state_root = find_root(state, config.get("state_root"), report, "state",
                           config_given=config_given)
    check_legacy_backend_key(config, report)
    if config_given:
        check_version_skew(config, report)
        check_tag_vocabulary(record, state, config, report)
    check_conflict_markers(record, report)
    check_conflict_markers(state, report)
    epoch_cutoff = resolve_epoch_cutoff(config, record, report)
    check_impacts(record, state, record_root, report, epoch_cutoff)
    check_state_nodes(record, state, state_root, report)
    check_hwm(record, state, record_root, state_root, report)
    return report


def check_tag_vocabulary(record: Graph, state: Graph, config: dict, report: Report) -> None:
    """The only thing `check` says about tags, and it is a warning.

    A tag is annotation: no invariant reads one, so an undeclared name can never be a
    violation — that would invent an obligation the spec does not carry. But a project
    that committed a `tags.yml` has said out loud that it keeps a vocabulary, and a
    name drifting outside it is worth one line. A project with no `tags.yml` hears
    nothing at all.

    This is the *only* brake on a taxonomy nothing enforces. Whether it is enough is
    an open question [rec: simple-ocean-1716], not a settled one."""
    graph_dir = Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    try:
        vocab = load_tag_vocab(tags_file_for(config, graph_dir))
    except LocalGraphError as exc:
        report.add("warning", "-", "tags", str(exc))
        return
    if not any(vocab.get(k) for k in GRAPH_KINDS):
        return
    for kind, graph in (("record", record), ("state", state)):
        declared = declared_tag_names(vocab, kind)
        for node in sorted(graph.nodes.values(), key=lambda n: n.ref):
            for name in node.tags:
                if name not in declared:
                    report.add("warning", "-", node.ref,
                               f"tag `{name}` is not declared in this project's "
                               f"vocabulary — `hypergraph tags add --graph {kind} "
                               f"{name}` adds it, or drop the tag")


def check_since(ref: str, config: dict, report: Report, *, cwd: Path | None = None) -> None:
    """I1 across a branch: did this work get recorded at all?

    `check` can only see nodes that exist; work that was never recorded is invisible to
    it by construction. Comparing the branch against its merge base with `ref` closes
    that gap, and it is the only mechanism that reaches a contributor who never read
    AGENTS.md [rec: vast-rain-4873].

    Three-dot range on purpose: `<ref>...HEAD` is what the branch *adds*, not everything
    that has happened on `<ref>` since it forked.
    """
    repo = cwd or Path.cwd()
    if not _git(repo, "rev-parse", "--is-inside-work-tree").strip():
        report.add("violation", "I1", "-", f"--since {ref}: not a git checkout")
        return
    if not _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip():
        report.add("violation", "I1", "-",
                   f"--since {ref}: no such ref. In CI, check out with fetch-depth: 0 — "
                   "a shallow clone has no merge base to compare against.")
        return

    graph_dir = str(config.get("graph_dir") or DEFAULT_GRAPH_DIR).strip("/")
    generated = {str(config.get("state_md") or "STATE.md").strip("/"),
                 str(config.get("cache_dir") or DEFAULT_CACHE_DIR).strip("/")}

    def is_generated(path: str) -> bool:
        return any(path == g or path.startswith(g + "/") for g in generated)

    changed = [p for p in _git(repo, "diff", "--name-only", f"{ref}...HEAD").splitlines() if p]
    added = [p for p in _git(repo, "diff", "--name-only", "--diff-filter=A",
                             f"{ref}...HEAD").splitlines() if p]

    work = [p for p in changed
            if not p.startswith(graph_dir + "/") and p != graph_dir and not is_generated(p)]
    records = [p for p in added if p.startswith(f"{graph_dir}/record/") and p.endswith(".md")]

    if not work:
        report.add("info", "I1", "-", f"--since {ref}: no work outside the graph — nothing to record")
        return
    if records:
        report.add("info", "I1", "-",
                   f"--since {ref}: {len(records)} record node(s) for {len(work)} changed file(s)")
        return
    sample = ", ".join(sorted(work)[:4]) + ("…" if len(work) > 4 else "")
    report.add("violation", "I1", "-",
               f"--since {ref}: {len(work)} file(s) changed and no record node was added "
               f"({sample}). Work that exists only in the diff is invisible to the project's "
               "memory — run the hypergraph-record skill, or `hypergraph new record`.")


def cmd_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = run_check(args.record, args.state, config,
                       config_given=args.config is not None)
    if getattr(args, "since", None):
        check_since(args.since, config, report)
    violations, warnings, infos = report.violations(), report.warnings(), report.infos()
    for f in violations:
        print(f"VIOLATION {f}")
    for f in warnings:
        print(f"warning   {f}")
    for f in infos:
        print(f"info      {f}")
    print(f"\ncheck: {len(violations)} violation(s), {len(warnings)} warning(s)")
    return 1 if violations else 0


def cmd_hwm(args: argparse.Namespace) -> int:
    """Report the reconciliation frontier, or suggest the one a pre-0.0.5 graph needs.

    Read-only in both modes: it prints a value for the reconcile pass to write, because
    the state root is a state node and only reconcile may write those (SPEC I3).
    """
    config = load_config(args.config)
    record = load_graph(args.record)
    state = load_graph(args.state)
    scratch = Report()
    record_root = find_root(record, config.get("record_root"), scratch, "record")
    state_root = find_root(state, config.get("state_root"), scratch, "state")
    if state_root is None:
        raise LocalGraphError("hwm: cannot identify the state root — pass --config")

    frontier, ts = read_hwm(state_root)
    frontier = frontier or []

    if args.suggest:
        suggested = suggest_frontier(record, frontier, record_root)
        if not suggested:
            print("hwm --suggest: nothing reconciled yet — the frontier is `none`")
            return 0
        print(f"high_water_mark: {format_hwm(suggested)}")
        if suggested != frontier:
            covered = len(ancestors_of(record, suggested)) - (1 if record_root else 0)
            print(f"\n{len(suggested)} tip(s) covering {covered} record node(s). This is what the "
                  f"pre-0.0.5 timestamp rule treated as reconciled, expressed as ancestry.\n"
                  f"Adopt it in the next reconcile pass — do not hand-edit the state root.",
                  file=sys.stderr)
        return 0

    print(f"high_water_mark: {format_hwm(frontier)}")
    print(f"reconciled_at:   {ts or 'unknown'}")
    unknown = [s for s in frontier if s not in record.by_slug]
    for slug in unknown:
        print(f"  ! `{slug}` does not resolve to a record node")
    if unknown:
        return 1
    pending = unreconciled_nodes(record, frontier, record_root)
    print(f"\n{len(pending)} unreconciled record node(s):")
    for node in pending:
        print(f"  {node.slug}  {node.created_at}  {node.title[:70]}")
    return 0


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
    frontier, ts = read_hwm(root)
    hwm = ", ".join(f"`{s}`" for s in frontier) if frontier else None

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
        f"Reconciled through {hwm or '`unknown`'} at {ts or 'unknown'}.",
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

    frontier = None
    ts = None
    if state_root is not None:
        frontier, ts = read_hwm(state_root)
    frontier = frontier or []
    hwm_ids = {record.by_slug[s].node_id for s in frontier if s in record.by_slug}
    reconciled_ids = ancestors_of(record, frontier)
    # The timeline draws a single vertical rule and shades everything to its right as
    # unreconciled. That reading only holds for a linear record graph; with several tips
    # the rule is suppressed and the per-node accent carries the information instead.
    hwm = frontier[0] if len(frontier) == 1 else None

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
        unreconciled = not is_root and node.node_id not in reconciled_ids
        ly, od = rec_layout[node.node_id]
        record_nodes.append({
            "slug": node.ref, "title": node.title, "created_at": node.created_at,
            "parents": [id_to_slug["record"][p] for p in node.parent_ids
                        if p in id_to_slug["record"]],
            "content": node.content, "is_root": is_root,
            "is_hwm": node.node_id in hwm_ids,
            "unreconciled": unreconciled,
            "impacts": impacts, "impact_none": none_reason,
            "tags": list(node.tags),
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
            "tags": list(node.tags),
            "layer": ly, "order": od, "seq": seq,
            "prov_count": len(prov_slugs),
            "last_record_at": max(touched) if touched else None,
            "impact_count": sum(1 for l in links
                                if l["state"] == node.ref and l["kind"] == "impact"),
        })

    project = (config.get("project")
               or (state_root.title.split(" — ")[0].strip() if state_root else "")
               or "project")
    # Tag chips: the declared vocabulary where there is one, synthesized from the
    # name's digest where there is not, so an undeclared name still renders and two
    # machines agree on its colour without coordinating.
    used: dict[str, int] = {}
    for group in (record_nodes, state_nodes):
        for entry in group:
            for name in entry["tags"]:
                used[name] = used.get(name, 0) + 1
    try:
        vocab = load_tag_vocab(tags_file_for(config, Path(
            config.get("graph_dir") or DEFAULT_GRAPH_DIR)))
    except LocalGraphError:
        vocab = {}          # a broken vocabulary must not stop the page rendering
    tag_defs = [{"name": name, "count": count,
                 **{k: v for k, v in tag_def(name, vocab).items() if k != "name"}}
                for name, count in sorted(used.items())]
    return {
        "project": project,
        "record": {"root": record_root.ref if record_root else None, "nodes": record_nodes},
        "state": {"root": state_root.ref if state_root else None, "nodes": state_nodes},
        "links": links,
        "tag_defs": tag_defs,
        "reconciliation": {"high_water_mark": hwm, "reconciled_at": ts,
                           "high_water_frontier": frontier},
        # Page settings, not graph data — the `viz:` block of the config, baked in
        # so a tuning you like travels with the repo rather than with one browser.
        # `viz --live` deliberately does not swap this on refresh (see live.js).
        "settings": {"blob": (config.get("viz") or {}).get("blob") or {}},
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
# `tags` sits between `summary` and `origin`: it is annotation the author writes,
# not provenance bookkeeping a tool stamps. Omitted entirely when empty — writing
# `tags: []` into every node would rewrite every file in every adopting repo for
# nothing.
FM_ORDER = ("node_id", "slug", "title", "created_at", "parents", "summary", "tags",
            "origin", "flywheel")
# Structural bounds on a tag name. Not an invariant — no invariant reads a tag
# (SPEC: Per-project files). The comma is the one that matters: the CLI transport
# joins `--tag_ids` with `,`, so a name carrying one is unshippable.
TAG_NAME_MAX = 64

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
    def tags(self) -> list[str]:
        """Tag *names*, mirroring `parents` holding slugs rather than node ids.

        A name is the portable identity: it survives a fork, a re-home and a mirror
        that mints its own tag ids, exactly as a slug does for a node."""
        raw = self.meta.get("tags") or []
        return [str(t) for t in (raw if isinstance(raw, list) else [raw])]

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
        for problem in tag_name_problems(node.tags):
            raise LocalGraphError(f"{path}: {problem}")
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
                                 created_at=node.created_at, tags=node.tags)
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


# ------------------------------------------------------------------------- tags
# INTERFACE op 10. A tag is *annotation*: no invariant reads one, and `check` stays
# tag-blind except for a single warning when a declared vocabulary exists. That is
# deliberate — a claim that lives only as a tag is invisible to the protocol, and the
# right home for a claim is a node body.
#
# Two files, two jobs. Per-node assignment is a `tags:` list of **names** in the node
# frontmatter, for the same reason `parents:` holds slugs: a name survives a fork, a
# re-home, and a mirror that mints its own tag ids. The vocabulary — colours, flags,
# and whatever id a backend minted — lives in a committed `.hypergraph/tags.yml`,
# keyed by graph kind because `tags:create` is per graph root and this protocol has
# two roots.
#
# It is **not** in config.yml. `push` must *update* vocabulary entries in place to
# stamp mirror tag ids, and config.yml is only ever appended to textually so its
# hand-written comments survive a write (see `mint_mirror_roots`).

DEFAULT_TAGS_FILE = Path(".hypergraph/tags.yml")
TAG_VOCAB_VERSION = 1


def tag_name_problems(names: list[str]) -> list[str]:
    """Structural complaints about tag names, in order. Empty list = fine.

    Shape only. This is not an invariant check — it is the set of names the
    transport and the file format can carry at all."""
    problems: list[str] = []
    for name in names:
        if not isinstance(name, str) or not name.strip():
            problems.append(f"tag {name!r} is empty")
            continue
        if "," in name:
            problems.append(
                f"tag {name!r} contains a comma — the mirror transport joins tag ids "
                "with `,`, so a comma in a name is unshippable")
        if name != name.strip():
            problems.append(f"tag {name!r} has leading or trailing whitespace")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
            problems.append(f"tag {name!r} contains a control character")
        if len(name) > TAG_NAME_MAX:
            problems.append(f"tag {name!r} is longer than {TAG_NAME_MAX} characters")
    return problems


def synth_tag(name: str) -> dict:
    """A deterministic colour pair for an undeclared name.

    So `tags.yml` stays *optional*: a repo that never declares a vocabulary still
    renders and pushes its tags, and two machines agree on the colour without
    coordinating. Hue comes from the name's digest; the pair is a dark chip with
    light text, matching the palettes real graphs already use."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    import colorsys  # deferred: only the tag palette needs it

    def hexed(r: float, g: float, b: float) -> str:
        return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))

    return {"bg_color": hexed(*colorsys.hsv_to_rgb(hue, 0.45, 0.37)),
            "text_color": hexed(*colorsys.hsv_to_rgb(hue, 0.10, 0.96))}


def tag_def(name: str, vocab: dict | None = None, kind: str | None = None) -> dict:
    """The full definition for a name: declared if it is, synthesized if it is not."""
    for entry in tag_vocab_entries(vocab or {}, kind):
        if str(entry.get("name") or "") == name:
            merged = dict(synth_tag(name))
            merged.update({k: v for k, v in entry.items() if v is not None})
            return merged
    return {"name": name, **synth_tag(name)}


def tag_vocab_entries(vocab: dict, kind: str | None = None) -> list[dict]:
    """Declared tag definitions for one graph kind, or all of them when kind is None."""
    kinds = [kind] if kind else list(GRAPH_KINDS)
    out: list[dict] = []
    for k in kinds:
        for entry in vocab.get(k) or []:
            if isinstance(entry, dict) and entry.get("name"):
                out.append(entry)
    return out


def declared_tag_names(vocab: dict, kind: str | None = None) -> set[str]:
    return {str(e["name"]) for e in tag_vocab_entries(vocab, kind)}


def tags_file_for(config: dict, graph_dir: Path | None = None,
                  explicit: Path | None = None) -> Path:
    """Where this project's vocabulary lives: `--tags-file`, config, then the default
    beside the graph directory."""
    if explicit is not None:
        return Path(explicit)
    named = config.get("tags_file")
    if named:
        return Path(named)
    if graph_dir is not None:
        return Path(graph_dir).parent / "tags.yml"
    return DEFAULT_TAGS_FILE


def load_tag_vocab(path: Path | None) -> dict:
    """`.hypergraph/tags.yml` → `{kind: [tagdef]}`. A missing file is `{}`, not an
    error: the vocabulary is optional and `synth_tag` covers every undeclared name."""
    if path is None:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    import yaml

    try:
        loaded = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise LocalGraphError(f"{path} is not valid YAML: {exc}") from None
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise LocalGraphError(f"{path} must be a YAML mapping, got {type(loaded).__name__}")
    out: dict = {}
    for kind in GRAPH_KINDS:
        entries = loaded.get(kind) or []
        if not isinstance(entries, list):
            raise LocalGraphError(f"{path}: `{kind}:` must be a list of tag definitions")
        seen: set[str] = set()
        clean: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("name"):
                raise LocalGraphError(
                    f"{path}: every `{kind}:` entry needs a `name:` (got {entry!r})")
            name = str(entry["name"])
            if name in seen:
                raise LocalGraphError(
                    f"{path}: `{name}` is declared twice under `{kind}:` — a duplicate "
                    "definition is the one unrecoverable tag failure, exactly as a "
                    "duplicate node is")
            for problem in tag_name_problems([name]):
                raise LocalGraphError(f"{path}: {problem}")
            seen.add(name)
            clean.append(dict(entry, name=name))
        out[kind] = clean
    return out


def write_tag_vocab(path: Path, vocab: dict) -> Path:
    """Write the vocabulary back, entries in place.

    A full rewrite rather than an append, unlike config.yml: this file is generated
    and machine-owned, and `push` has to *update* entries in place to stamp the tag
    ids the mirror minted."""
    import yaml

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"version": TAG_VOCAB_VERSION}
    for kind in GRAPH_KINDS:
        payload[kind] = [dict(e) for e in (vocab.get(kind) or [])]
    header = (
        "# Tag vocabulary for this project (INTERFACE op 10).\n"
        "#\n"
        "# Generated and machine-owned — `hypergraph tags add|rm` edits it, and `push`\n"
        "# stamps the ids the mirror minted into each `flywheel:` block. Commit it: the\n"
        "# names in node frontmatter are resolved against this file, and it is what\n"
        "# keeps a second `tags:create` from minting a duplicate definition.\n"
        "#\n"
        "# Keyed by graph kind because `tags:create` is per graph root, and this\n"
        "# protocol has two roots. A name that is not declared here still works — it\n"
        "# just gets a colour derived from its own digest.\n")
    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=4096)
    path.write_text(header + body)
    return path


def merge_tag_def(vocab: dict, kind: str, entry: dict) -> dict:
    """Merge one definition into the vocabulary by name, in place, and return it.

    Never clobbers a `flywheel:` stamp: that block records a tag this project already
    created on its mirror, and losing it is how you get a second definition of the
    same name."""
    name = str(entry.get("name") or "")
    if not name:
        raise LocalGraphError("a tag definition needs a `name:`")
    entries = vocab.setdefault(kind, [])
    for existing in entries:
        if str(existing.get("name") or "") != name:
            continue
        stamp = existing.get("flywheel")
        existing.update({k: v for k, v in entry.items() if k != "flywheel"})
        if stamp is not None:
            existing["flywheel"] = stamp
        elif entry.get("flywheel") is not None:
            existing["flywheel"] = entry["flywheel"]
        return existing
    entries.append(dict(entry))
    return entries[-1]


def cmd_tags(args: argparse.Namespace) -> int:
    """`hypergraph tags {list,add,rm}` — so nothing ever hand-edits the YAML.

    The record skill teaches agents to tag; without a command they would edit a
    generated file by hand, and a hand-merged duplicate name is the failure this
    whole file exists to prevent."""
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    path = tags_file_for(config, graph_dir, args.tags_file)
    vocab = load_tag_vocab(path)

    if args.action == "list":
        used: dict[str, int] = {}
        for kind in GRAPH_KINDS:
            for node in load_local_nodes(graph_dir, kind, missing_ok=True).values():
                for name in node.tags:
                    used[name] = used.get(name, 0) + 1
        if args.json:
            print(json.dumps({"path": str(path), "vocabulary": {
                k: tag_vocab_entries(vocab, k) for k in GRAPH_KINDS},
                "usage": used}, indent=2, ensure_ascii=False))
            return 0
        if not any(vocab.get(k) for k in GRAPH_KINDS):
            print(f"no tag vocabulary at {path} — this project tags nothing yet.\n"
                  "`hypergraph tags add <name>` starts one.")
        for kind in GRAPH_KINDS:
            entries = tag_vocab_entries(vocab, kind)
            if not entries:
                continue
            print(f"{kind}:")
            for entry in entries:
                stamp = (entry.get("flywheel") or {}).get("tag_id")
                notes = ["pointer"] if entry.get("one_only") else []
                if stamp:
                    notes.append(str(stamp))
                print(f"    {str(entry['name']):<32} "
                      f"{used.get(str(entry['name']), 0):>4} node(s)"
                      + (f"   [{', '.join(notes)}]" if notes else ""))
        undeclared = sorted(set(used) - declared_tag_names(vocab))
        for name in undeclared:
            print(f"  ? {name:<32} {used[name]:>4} node(s)   [not declared]")
        return 0

    if args.action == "add":
        for problem in tag_name_problems([args.name]):
            raise LocalGraphError(problem)
        entry = {"name": args.name}
        entry.update(synth_tag(args.name))
        if args.bg_color:
            entry["bg_color"] = args.bg_color
        if args.text_color:
            entry["text_color"] = args.text_color
        if args.one_only:
            entry["one_only"] = True
        if args.track_history:
            entry["track_history"] = True
        merged = merge_tag_def(vocab, args.graph, entry)
        write_tag_vocab(path, vocab)
        print(f"tags: `{merged['name']}` declared under `{args.graph}:` in {path}")
        return 0

    if args.action == "rm":
        entries = vocab.get(args.graph) or []
        keep = [e for e in entries if str(e.get("name") or "") != args.name]
        if len(keep) == len(entries):
            raise LocalGraphError(
                f"`{args.name}` is not declared under `{args.graph}:` in {path}")
        still_used = sorted(
            node.slug for kind in GRAPH_KINDS
            for node in load_local_nodes(graph_dir, kind, missing_ok=True).values()
            if args.name in node.tags)
        if still_used and not args.force:
            raise LocalGraphError(
                f"`{args.name}` is still on {len(still_used)} node(s) "
                f"({', '.join(still_used[:5])}{'…' if len(still_used) > 5 else ''}). "
                "Undeclaring it leaves them tagged with a name nothing defines — pass "
                "--force if that is what you mean.")
        vocab[args.graph] = keep
        write_tag_vocab(path, vocab)
        # Deliberately local-only: `tags:delete` on the mirror un-tags every node that
        # used the tag, which is a data loss no local edit asked for.
        print(f"tags: `{args.name}` undeclared under `{args.graph}:` in {path}\n"
              "      The mirror definition is left alone — `tags:delete` would un-tag "
              "every node that used it.")
        return 0

    raise LocalGraphError(f"unknown tags action: {args.action}")


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
            "tags": node.tags,
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


def local_tag_name(name: str, taken: set[str]) -> str:
    """A source tag name → a name this backend can carry, deterministically.

    `★ studio-baseline` → `studio-baseline`. Decoration and separators go; the word
    stays. **A name is never dropped**: if transliteration empties it or collides, the
    original is preserved through a digest suffix rather than lost, because the name
    is the tag's whole portable identity."""
    cleaned = "".join(" " if (ord(ch) < 0x20 or ord(ch) == 0x7F or ch == ",") else ch
                      for ch in str(name))
    # strip leading/trailing non-alphanumerics (the ★ and its space), keep the middle
    cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", cleaned, flags=re.U).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:TAG_NAME_MAX].strip()
    if not cleaned:
        cleaned = "tag-" + hashlib.sha256(str(name).encode()).hexdigest()[:8]
    if cleaned in taken:
        suffix = "-" + hashlib.sha256(str(name).encode()).hexdigest()[:6]
        cleaned = cleaned[:TAG_NAME_MAX - len(suffix)] + suffix
    return cleaned


def collect_source_tags(raw_nodes: list[dict]) -> dict[str, dict]:
    """`graph_tags` across every node → `{tag_id: tagdef}`.

    A **union** is required, not a read of any one node: in the neural-whoop archive
    only 130 of 189 nodes echo the vocabulary while 59 carry an empty `graph_tags`
    beside a populated `tag_ids` [rec: fresh-spire-9002]. The **parentless node's copy
    wins** when copies disagree — the vocabulary is defined on the graph root, so that
    copy is the authoritative one."""
    union: dict[str, dict] = {}
    root_copy: dict[str, dict] = {}
    for raw in raw_nodes:
        parentless = not (raw.get("incoming_ids") or raw.get("parent_ids")
                          or raw.get("parents"))
        for tag in raw.get("graph_tags") or []:
            if not isinstance(tag, dict) or not tag.get("tag_id"):
                continue
            tid = str(tag["tag_id"])
            union.setdefault(tid, tag)
            if parentless:
                root_copy[tid] = tag
    union.update(root_copy)
    return union


def import_tag_vocabulary(raw_nodes: list[dict], *, fork: bool, pushed_at: str,
                          out=lambda m: print(m, file=sys.stderr)
                          ) -> tuple[dict[str, str], list[dict]]:
    """Source `graph_tags` → (`{tag_id: local name}`, ordered tag definitions).

    The fork rule mirrors the node rule exactly. `--fork` records the source id under
    `origin:` and omits `flywheel:`, so the first push *creates* the vocabulary fresh
    under roots this project owns. A re-home stamps `flywheel:`, so the first push is
    a no-op against the graph it already lives on."""
    source = collect_source_tags(raw_nodes)
    by_id: dict[str, str] = {}
    defs: list[dict] = []
    taken: set[str] = set()
    for tid, tag in sorted(source.items(), key=lambda kv: str(kv[1].get("name") or kv[0])):
        original = str(tag.get("name") or tid)
        name = local_tag_name(original, taken)
        taken.add(name)
        by_id[tid] = name
        entry: dict = {"name": name}
        if name != original:
            # Never a silent rename: the source spelling stays queryable, and the
            # rename is reported on stderr as it happens.
            entry["archive_name"] = original
            out(f"import: tag {original!r} → {name!r} (kept as archive_name:)")
        for key in ("bg_color", "text_color"):
            if tag.get(key):
                entry[key] = str(tag[key])
        for key in ("one_only", "track_history"):
            if tag.get(key):
                entry[key] = True
        if fork:
            entry["origin"] = {"backend": "flywheel", "tag_id": tid,
                               "exported_at": str(pushed_at)}
        else:
            entry["flywheel"] = {"tag_id": tid, "pushed_at": str(pushed_at)}
        defs.append(entry)
    return by_id, defs


def pointer_tag_chains(raw_nodes: list[dict], tag_by_id: dict[str, str]) -> dict:
    """Reconstruct each moving pointer tag's chain from per-node `tag_history`.

    Deliberately **not** modelled in frontmatter. This goes to
    `cache/import-report.json` and from there into the epoch marker body as prose: a
    pointer move with a reason is a decision, and a decision is a record node. Putting
    the chain in frontmatter would be a third home for a claim no invariant reads
    (SPEC I1).

    The chains are also the finding: every hop carries a timestamp and a successor,
    and **not one carries a reason** [rec: fresh-spire-9002]."""
    hops: dict[str, list[dict]] = {}
    slug_by_id = {str(n.get("node_id") or n.get("id") or ""): str(
        n.get("slug_name") or n.get("slug") or n.get("node_id") or "") for n in raw_nodes}
    for raw in raw_nodes:
        for hop in raw.get("tag_history") or []:
            if not isinstance(hop, dict) or not hop.get("tag_id"):
                continue
            tid = str(hop["tag_id"])
            successor = str(hop.get("superseded_by_node_id") or "")
            hops.setdefault(tid, []).append({
                "slug": str(raw.get("slug_name") or raw.get("slug") or ""),
                "history_index": hop.get("history_index"),
                "superseded_at": hop.get("superseded_at"),
                "superseded_by_slug": slug_by_id.get(successor, successor),
            })
    out: dict = {}
    for tid, chain in hops.items():
        chain.sort(key=lambda h: (h.get("history_index") is None,
                                  h.get("history_index"), str(h.get("superseded_at"))))
        out[tag_by_id.get(tid, tid)] = chain
    return out


def cmd_import(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    tags_path = tags_file_for(config, graph_dir, getattr(args, "tags_file", None))
    want_tags = not getattr(args, "no_tags", False)
    vocab = load_tag_vocab(tags_path) if want_tags else {}
    chains: dict = {}
    tag_counts: dict[str, int] = {}
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
        tag_by_id: dict[str, str] = {}
        if want_tags:
            tag_by_id, tag_defs = import_tag_vocabulary(
                list(extras.values()), fork=args.fork, pushed_at=str(pushed_at))
            for entry in tag_defs:
                merge_tag_def(vocab, kind, entry)
            chains.update(pointer_tag_chains(list(extras.values()), tag_by_id))
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
            # Tags travel on both paths, and for the same reason `summary` does: they
            # are annotation the source authored, not mirror bookkeeping. Omitted when
            # empty so an untagged graph's files are byte-unchanged.
            tags = sorted({tag_by_id[str(t)] for t in (src.get("tag_ids") or [])
                           if str(t) in tag_by_id})
            if tags:
                meta["tags"] = tags
                for name in tags:
                    tag_counts[name] = tag_counts.get(name, 0) + 1
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

    if want_tags and any(vocab.get(k) for k in GRAPH_KINDS):
        write_tag_vocab(tags_path, vocab)
        declared = sum(len(vocab.get(k) or []) for k in GRAPH_KINDS)
        print(f"import: {declared} tag(s) declared in {tags_path}, "
              f"{sum(tag_counts.values())} assignment(s) across "
              f"{len(tag_counts)} name(s)")
        report_path = write_import_report(config, graph_dir, chains, tag_counts,
                                          fork=args.fork)
        if chains:
            # Loud on purpose. This is the one thing the import cannot carry, and the
            # adopt skill's step 6 has to pick it up by hand.
            print("", file=sys.stderr)
            print("=" * 72, file=sys.stderr)
            print("POINTER TAGS MOVED, AND THE MOVES DO NOT TRAVEL.", file=sys.stderr)
            for name, chain in sorted(chains.items()):
                print(f"  {name}: {len(chain)} hop(s) — "
                      + " → ".join(str(h.get("slug") or "?") for h in chain)
                      + (f" → {chain[-1].get('superseded_by_slug')}"
                         if chain and chain[-1].get("superseded_by_slug") else ""),
                      file=sys.stderr)
            print("", file=sys.stderr)
            print("The names travelled; the chain did not. Every hop has a timestamp",
                  file=sys.stderr)
            print("and no reason, so frontmatter would be a third home for a claim no",
                  file=sys.stderr)
            print("invariant reads. Write the chain into the epoch marker body as prose",
                  file=sys.stderr)
            print("(hypergraph-adopt step 6) — that is what makes this routing rather",
                  file=sys.stderr)
            print("than loss. The full chains are in:", file=sys.stderr)
            print(f"  {report_path}", file=sys.stderr)
            print("=" * 72, file=sys.stderr)
    return 0


def write_import_report(config: dict, graph_dir: Path, chains: dict,
                        counts: dict[str, int], *, fork: bool) -> Path:
    """What the import carried and what it could not, as a file the adopt skill reads."""
    cache_dir = Path(config.get("cache_dir") or (Path(graph_dir).parent / "cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "import-report.json"
    path.write_text(json.dumps({
        "version": EXPORT_VERSION,
        "generated_at": utc_now(),
        "mode": "fork" if fork else "re-home",
        "tag_assignments": dict(sorted(counts.items())),
        "pointer_tag_history": chains,
        "note": ("Pointer-tag history is deliberately not modelled in the graph. Record "
                 "these chains in the adoption epoch marker's body as prose; a pointer "
                 "move with a reason is a decision, and a decision is a record node."),
    }, indent=2, ensure_ascii=False) + "\n")
    return path


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
    check_conflict_markers(solo, report)
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
    tags = sorted(dict.fromkeys(args.tag or []))
    for problem in tag_name_problems(tags):
        raise LocalGraphError(problem)
    if tags:
        # Warn, never refuse: a tag is annotation and no invariant reads one, so an
        # undeclared name must stay usable. The warning exists only once a project
        # has said "we have a vocabulary" by committing a tags.yml.
        vocab = load_tag_vocab(tags_file_for(config, graph_dir, args.tags_file))
        if any(vocab.get(k) for k in GRAPH_KINDS):
            for name in tags:
                if name not in declared_tag_names(vocab, kind):
                    print(f"warning   tag `{name}` is not declared in this project's "
                          f"vocabulary — `hypergraph tags add {name}` adds it",
                          file=sys.stderr)
        meta["tags"] = tags     # omitted when empty: see FM_ORDER
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


# --------------------------------------------------------- graph comparison layer
# One typed diff of two graphs on named fields, sitting *above* everything that
# needs one. `push_plan` diffs a graph against its own frontmatter, `verify_mirror`
# diffs it against a live mirror export, and every healer diffs it against a source
# graph on exactly one field. Before this section each of those was its own loop with
# its own ideas about matching, so a new comparison meant a new loop.
#
# Three rules the loops did not previously state out loud:
#
# 1. **Match keys are declared, never inferred.** A content hash is not a match key —
#    two record nodes can legitimately share a body, and matching on one would fuse
#    them.
# 2. **Ambiguity is reported, never resolved.** Two nodes claiming the same key make
#    a `Drift(kind="ambiguous")` and *both* are excluded from field comparison.
#    Picking one is how a repair writes the wrong node.
# 3. **A Drift carries both values, not a message.** Callers reconstruct the wording
#    they already had, so adding a comparison never changes an existing report.

@dataclass(frozen=True)
class Drift:
    """One difference between two graphs, at one key, on one field."""
    kind: str        # field | missing-right | missing-left | unkeyed | ambiguous
    field: str       # body | title | summary | revision | parents | tags | artifacts
    key: str
    left: object = None
    right: object = None
    left_ref: str = "-"
    right_ref: str = "-"
    note: str = ""

    @property
    def ref(self) -> str:
        for candidate in (self.left_ref, self.right_ref, self.key):
            if candidate and candidate != "-":
                return candidate
        return self.key


@dataclass
class GraphSide:
    """One side of a comparison: normalized records, keyed for matching.

    `records` keeps source order (file order for a local side), because a report that
    walks it must read in the order a human's directory listing does. `nodes` is the
    keyed subset — the two differ by exactly `unkeyed` and the losing half of every
    collision."""
    name: str
    key: str                              # flywheel | origin | node_id | slug
    nodes: dict[str, dict] = field(default_factory=dict)
    collisions: dict[str, list[str]] = field(default_factory=dict)
    unkeyed: list[dict] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)


def _side_record(*, ref: str, kind: str, key: str | None, body: str, title: str,
                 summary: str, revision: object, parents: list[str], tags: list[str],
                 created_at: str, node_id: str, slug: str, artifacts: list,
                 has_summary: bool = True, node: object = None,
                 raw: dict | None = None) -> dict:
    return {"ref": ref, "kind": kind, "key": key, "body": body, "title": title,
            "summary": summary, "revision": revision, "parents": parents,
            "tags": tags, "created_at": created_at, "node_id": node_id, "slug": slug,
            "artifacts": artifacts, "has_summary": has_summary, "node": node,
            "raw": raw}


def _index(side: GraphSide) -> GraphSide:
    for record in side.records:
        key = record.get("key")
        if not key:
            side.unkeyed.append(record)
            continue
        if key in side.nodes:
            side.collisions.setdefault(key, [side.nodes[key]["ref"]]).append(record["ref"])
            continue
        if key in side.collisions:
            side.collisions[key].append(record["ref"])
            continue
        side.nodes[key] = record
    for key in side.collisions:
        side.nodes.pop(key, None)
    return side


def side_from_local(graph_dir: Path, *, key: str, kinds=GRAPH_KINDS,
                    name: str = "local") -> GraphSide:
    """The committed node files as one comparable side.

    `key` names where the match id comes from: `flywheel` and `origin` read the
    matching frontmatter block, `node_id` and `slug` read the node's own identity."""
    side = GraphSide(name=name, key=key)
    for kind in kinds:
        for node in load_local_nodes(graph_dir, kind, missing_ok=True).values():
            if key in ("flywheel", "origin"):
                block = node.meta.get(key) or {}
                match = str(block.get("node_id") or "") or None
                revision = block.get("revision")
            elif key == "node_id":
                match, revision = node.node_id or None, None
            elif key == "slug":
                match, revision = node.slug or None, None
            else:
                raise LocalGraphError(f"unknown match key for a local side: {key!r}")
            side.records.append(_side_record(
                ref=node.slug, kind=kind, key=match, body=node.content,
                title=node.title, summary=str(node.meta.get("summary") or ""),
                revision=revision, parents=node.parents, tags=node.tags,
                created_at=node.created_at, node_id=node.node_id, slug=node.slug,
                artifacts=[], node=node))
    return _index(side)


def _export_records(raw_nodes: list[dict], key: str) -> list[dict]:
    # tag ids resolve through the union of `graph_tags` across every node: an export
    # echoes the vocabulary on only some of its nodes (130 of 189 in the neural-whoop
    # archive), so a per-node read loses a third of the graph [rec: fresh-spire-9002]
    vocab = collect_source_tags(raw_nodes)
    names = {tid: str(tag.get("name") or tid) for tid, tag in vocab.items()}
    records = []
    for raw in raw_nodes:
        node_id = str(raw.get("node_id") or raw.get("id") or "")
        slug = str(raw.get("slug_name") or raw.get("slug") or "")
        if key == "node_id":
            match = node_id or None
        elif key == "slug":
            match = slug or None
        else:
            raise LocalGraphError(f"unknown match key for an export side: {key!r}")
        declared = raw.get("tags")
        tags = ([str(t) for t in declared] if isinstance(declared, list)
                else sorted({names[str(t)] for t in (raw.get("tag_ids") or [])
                             if str(t) in names}))
        records.append(_side_record(
            ref=slug or node_id, kind="", key=match,
            body=str(raw.get("content") or ""), title=str(raw.get("title") or ""),
            summary=str(raw.get("summary") or ""),
            revision=raw.get("committed_revision", raw.get("revision")),
            parents=_norm_parents(raw.get("parent_ids") or raw.get("parents")
                                  or raw.get("incoming_ids")),
            tags=tags, created_at=str(raw.get("created_at") or ""),
            node_id=node_id, slug=slug,
            artifacts=list(raw.get("artifacts") or []),
            has_summary="summary" in raw, raw=raw))
    return records


def side_from_export(path_or_data: object, *, key: str = "node_id",
                     name: str = "export") -> GraphSide:
    """A graph export (a file path, or already-parsed JSON) as one comparable side."""
    if isinstance(path_or_data, (str, Path)):
        data = json.loads(Path(path_or_data).read_text())
    else:
        data = path_or_data
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    raw_nodes = [r for r in (raw_nodes or []) if isinstance(r, dict)]
    side = GraphSide(name=name, key=key)
    side.records = _export_records(raw_nodes, key)
    return _index(side)


def plan_op_counts(plan: dict) -> tuple[int, int, int]:
    """(creates, body updates, tag assignments). Counted by op, never by subtraction —
    a tag assignment is not an update, and reporting it as one overstates what the
    push does to the record graph."""
    ops = plan.get("ops") or []
    creates = sum(1 for o in ops if o.get("op") == "create")
    tags = sum(1 for o in ops if o.get("op") == "tags")
    return creates, len(ops) - creates - tags, tags


def _load_export_nodes(path: Path) -> dict[str, dict]:
    """Export JSON → {node_id: raw node dict}. Thin wrapper over `side_from_export`,
    kept because callers outside this section still speak in raw dicts."""
    return {r["node_id"]: r["raw"] for r in side_from_export(path).records
            if r["node_id"]}


@dataclass(frozen=True)
class FieldComparator:
    """How one field is read off a record and when two readings disagree.

    `applies` exists because two comparisons are conditional in ways that are not
    "the values differ": a mirror export that omits `summary` entirely is not
    asserting the summary is empty, and a revision only skews when *both* sides
    claim one."""
    extract: object
    equal: object = staticmethod(lambda a, b: a == b)
    applies: object = staticmethod(lambda left, right: True)


FIELD_COMPARATORS: dict[str, FieldComparator] = {
    "body": FieldComparator(
        extract=lambda r: r["body"],
        equal=lambda a, b: body_sha256(a) == body_sha256(b)),
    "title": FieldComparator(extract=lambda r: r["title"]),
    "summary": FieldComparator(
        extract=lambda r: r["summary"],
        applies=lambda left, right: right.get("has_summary", True)),
    "revision": FieldComparator(
        extract=lambda r: r["revision"],
        equal=lambda a, b: int(a) == int(b),
        applies=lambda left, right: left["revision"] is not None
        and right["revision"] is not None),
    "parents": FieldComparator(extract=lambda r: list(r["parents"])),
    "created_at": FieldComparator(extract=lambda r: r["created_at"]),
    "tags": FieldComparator(extract=lambda r: sorted(r["tags"])),
    # No healer reads this one yet. It is here because the extensibility claim is
    # "a new comparison costs one entry in this table", and a claim with no second
    # instance is not evidence.
    "artifacts": FieldComparator(
        extract=lambda r: sorted(str(a.get("artifact_id") or a) if isinstance(a, dict)
                                 else str(a) for a in r["artifacts"])),
}


def diff_graphs(left: GraphSide, right: GraphSide, *,
                fields=("body", "summary", "revision"),
                exempt_left=None, exempt_right=None) -> list[Drift]:
    """Left against right, in left's source order, then right's leftovers.

    Order is part of the contract: a caller formatting these back into a report gets
    the same per-node interleaving it would have produced with its own loop."""
    exempt_left = set(exempt_left or ())
    exempt_right = set(exempt_right or ())
    for name in fields:
        if name not in FIELD_COMPARATORS:
            raise LocalGraphError(
                f"no comparator for field {name!r} "
                f"(have: {', '.join(sorted(FIELD_COMPARATORS))})")
    drifts: list[Drift] = []
    seen: set[str] = set()
    for record in left.records:
        key = record.get("key")
        if not key:
            drifts.append(Drift(kind="unkeyed", field="-", key=record["ref"],
                                left=record, left_ref=record["ref"],
                                note=f"no `{left.key}` match key"))
            continue
        if key in exempt_left:
            seen.add(key)
            continue
        if key in left.collisions:
            drifts.append(Drift(kind="ambiguous", field="-", key=key, left=record,
                                left_ref=record["ref"],
                                note=f"{left.name}: {', '.join(left.collisions[key])} "
                                     f"all claim `{key}`"))
            seen.add(key)
            continue
        if key in right.collisions:
            drifts.append(Drift(kind="ambiguous", field="-", key=key, left=record,
                                left_ref=record["ref"],
                                note=f"{right.name}: {', '.join(right.collisions[key])} "
                                     f"all claim `{key}`"))
            seen.add(key)
            continue
        other = right.nodes.get(key)
        if other is None:
            drifts.append(Drift(kind="missing-right", field="-", key=key, left=record,
                                left_ref=record["ref"]))
            continue
        seen.add(key)
        for name in fields:
            comparator = FIELD_COMPARATORS[name]
            if not comparator.applies(record, other):
                continue
            mine, theirs = comparator.extract(record), comparator.extract(other)
            if not comparator.equal(mine, theirs):
                drifts.append(Drift(kind="field", field=name, key=key, left=mine,
                                    right=theirs, left_ref=record["ref"],
                                    right_ref=other["ref"]))
    for key, record in sorted(right.nodes.items()):
        if key in seen or key in exempt_right:
            continue
        drifts.append(Drift(kind="missing-left", field="-", key=key, right=record,
                            right_ref=record["ref"]))
    return drifts


def pending_push_drift(side: GraphSide) -> list[Drift]:
    """Local nodes edited since their last push, from the file alone.

    Deliberately *not* part of `diff_graphs`: this compares a node's body against the
    hash stamped in its own frontmatter, so there is no second graph involved.
    Folding it in would make `diff_graphs` mean two different things."""
    drifts = []
    for record in side.records:
        node = record.get("node")
        stamp = (getattr(node, "meta", {}) or {}).get("flywheel") or {}
        if stamp.get("content_sha256") and stamp["content_sha256"] != body_sha256(record["body"]):
            drifts.append(Drift(kind="field", field="body", key=record.get("key") or record["ref"],
                                left=record["body"], right=None, left_ref=record["ref"],
                                note="pending push"))
    return drifts


# -------------------------------------------------------------- flywheel mirror

def tags_sha256(names: list[str]) -> str:
    """A stamp for a node's tag set, deliberately **separate** from `content_sha256`.

    Folding tags into the body hash would be cheaper by one field and wrong twice
    over: `verify_mirror` and `push_legend` both rest on body byte-identity, and every
    existing adopter's entire graph would re-push the first time this shipped. A
    sibling stamp in the same `flywheel:` block costs one line and breaks nothing."""
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def push_plan(graph_dir: Path, *, do_tags: bool = True) -> dict:
    """Diff local files against their `flywheel:` frontmatter → an ordered op list.

    This tool never calls MCP; the skill layer executes the plan and feeds the
    returned ids back via `push --record-result` (backend/local-adapter.md)."""
    ops: list[dict] = []
    violations: list[str] = []
    tag_ops: list[dict] = []
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
            if do_tags:
                stamp = flywheel.get("tags_sha256")
                want = tags_sha256(node.tags)
                # The `or` clause is what makes *clearing* tags possible: with no
                # stamp and no tags there is nothing to do, but a stamp with an empty
                # list is a node whose tags were removed locally, and without this it
                # would stay tagged on the mirror forever.
                if (node.tags and stamp != want) or (stamp and not node.tags):
                    tag_ops.append({"graph": kind, "slug": node.slug, "op": "tags",
                                    "tags": list(node.tags), "tags_sha256": want,
                                    "flywheel_node_id": flywheel.get("node_id"),
                                    "base_revision": flywheel.get("revision")})
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
    # A second pass, appended after every node op: a tag assignment needs the node to
    # exist, and a node created in this same run only gets its mirror id from
    # `minted` partway through the loop above.
    return {"version": EXPORT_VERSION, "graph_dir": str(graph_dir),
            "generated_at": utc_now(), "ops": ops + tag_ops, "violations": violations}


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


VERIFY_FIELDS = ("body", "summary", "revision")
# Off by default and opt-in through `push --verify --strict`, because each would fire
# on correct graphs: mirror root titles differ from local ones by doctrine, mirror
# parent ids are mirror ids rather than local slugs, and a re-homed node's created_at
# is the mirror's. `--strict` maps parents before comparing, which is the only way to
# see topology drift at all.
VERIFY_STRICT_FIELDS = ("body", "summary", "revision", "title", "parents", "tags")


def verify_mirror(graph_dir: Path, against: Path,
                  exempt_ids: set[str] | None = None, *,
                  fields=VERIFY_FIELDS, strict: bool = False) -> Report:
    """Read-only drift check: a fresh mirror export vs the local node files.

    Drift = missing nodes on either side, body-hash or summary mismatches, local
    edits not yet pushed, or revision skew vs `flywheel:` frontmatter. Mirror-only
    structure is exempt by design: the slug-legend node (LEGEND_TITLE) and any
    `exempt_ids` (the config's `mirror_roots`, minted when an adopted project
    mirrors its post-epoch nodes under fresh roots).

    The comparison is `diff_graphs`; everything here is wording. The findings are
    byte-identical to the hand-rolled loop this replaced — `test_verify_mirror_
    findings_are_byte_identical_after_the_refactor` is what holds that true."""
    report = Report()
    exempt_ids = set(exempt_ids or ())
    local = side_from_local(graph_dir, key="flywheel")
    mirror = side_from_export(against, name="mirror")
    if strict:
        fields = VERIFY_STRICT_FIELDS
        # Local parents are slugs, mirror parents are mirror ids: map before
        # comparing, or every node reports drift over a difference in vocabulary
        # rather than in topology. Both sides sort — parent *order* is not meaning.
        by_slug = {r["slug"]: r["key"] for r in local.records if r["slug"] and r["key"]}
        for record in local.records:
            record["parents"] = sorted(str(by_slug.get(p) or p) for p in record["parents"])
        for record in mirror.records:
            record["parents"] = sorted(str(p) for p in record["parents"])
    # The legend is mirror-only bookkeeping and has no local counterpart by design.
    exempt_right = exempt_ids | {
        r["key"] for r in mirror.records
        if r["key"] and str((r["raw"] or {}).get("title") or "") == LEGEND_TITLE}

    pending = {}
    for drift in pending_push_drift(local):
        pending.setdefault(drift.key, []).append(drift)

    by_key: dict[str, list[Drift]] = {}
    tail: list[Drift] = []
    for drift in diff_graphs(local, mirror, fields=fields, exempt_right=exempt_right):
        if drift.kind == "missing-left":
            tail.append(drift)
        else:
            by_key.setdefault(drift.key, []).append(drift)

    field_message = {
        "body": "body hash mismatch between local file and mirror",
        "summary": "summary mismatch between local file and mirror",
        "title": "title mismatch between local file and mirror",
        "parents": "parent set differs between local file and mirror",
        "tags": "tag set differs between local file and mirror",
        "created_at": "created_at differs between local file and mirror",
    }
    for record in local.records:
        key = record.get("key") or record["ref"]
        # pending-push first: it explains a body mismatch that is not corruption
        for drift in pending.get(key, []):
            report.add("violation", "mirror", drift.left_ref,
                       "local body changed since last push (pending update)")
        for drift in by_key.get(key, []):
            if drift.kind == "unkeyed":
                report.add("violation", "mirror", drift.left_ref,
                           f"local {record['kind']} node never pushed to the mirror")
            elif drift.kind == "missing-right":
                report.add("violation", "mirror", drift.left_ref,
                           f"local {record['kind']} node missing from the mirror export "
                           f"(flywheel id {drift.key})")
            elif drift.kind == "ambiguous":
                report.add("violation", "mirror", drift.left_ref,
                           f"ambiguous mirror identity — {drift.note}. Refusing to pick "
                           "one; two nodes cannot share a mirror id.")
            elif drift.field == "revision":
                report.add("violation", "mirror", drift.left_ref,
                           f"revision skew: mirror at {drift.right}, frontmatter says "
                           f"{drift.left}")
            else:
                report.add("violation", "mirror", drift.left_ref,
                           field_message.get(drift.field,
                                             f"{drift.field} mismatch between local file "
                                             "and mirror"))
    for drift in tail:
        report.add("violation", "mirror", drift.right_ref or drift.key,
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


def apply_push_results(graph_dir: Path, results: object, *,
                       nodes: dict | None = None) -> int:
    """Fold the mirror's returned ids/revisions back into each node's frontmatter.

    `nodes` lets a caller pass an already-loaded node map. Results are folded every
    `--batch` nodes, so without it a 2000-node push reloads the whole graph 100
    times."""
    if isinstance(results, dict):
        results = results.get("results", results.get("ops", []))
    if not isinstance(results, list):
        raise LocalGraphError("results file must be a list, or an object with a `results` list")
    if nodes is None:
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
        # A sibling of content_sha256, never folded into it: the body hash is what
        # `verify_mirror` and `push_legend` rest on, and moving it would re-push every
        # existing adopter's whole graph the first time this shipped.
        if entry.get("tags_sha256") is not None:
            fw["tags_sha256"] = str(entry["tags_sha256"])
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


def _links_into(dst: Path, tree: Path) -> bool:
    """Is `dst` a symlink that resolves inside `tree`?

    This is the dogfooding case: `.claude/skills/hypergraph-record` is a committed
    relative symlink back into `skills/`. Copying over it would silently replace the
    live skill with a stale snapshot of itself, so `install` refuses instead."""
    if not dst.is_symlink():
        return False
    try:
        resolved = dst.resolve()
    except OSError:  # broken or looping link — not ours; let the caller replace it
        return False
    try:
        resolved.relative_to(tree.resolve())
    except ValueError:
        return False
    return True


def upgrade_skills(source: Path, target: Path, changes: list, dry_run: bool) -> None:
    """Replace installed skills wholesale, so a file we deleted upstream goes away.

    `skills install` copies with `dirs_exist_ok`, which merges — a reference file
    removed in a later release would linger forever. Upgrade is the one place that
    can safely prune, because the whole directory is ours."""
    for src in sorted(source.glob("hypergraph-*")):
        if not src.is_dir():
            continue
        dst = target / src.name
        if not dst.exists() and not dst.is_symlink():
            continue                      # not installed here — upgrade never installs
        if _links_into(dst, source):
            changes.append(("skipped", dst, "symlinked to the source (dev checkout)"))
            continue
        if dst.is_dir() and not dst.is_symlink() and _trees_match(src, dst):
            changes.append(("unchanged", dst, ""))
            continue
        if not dry_run:
            if dst.is_symlink():
                dst.unlink()
            elif dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        changes.append(("refreshed", dst, ""))


def _trees_match(src: Path, dst: Path) -> bool:
    """Same relative paths, same bytes. Cheap enough for five small skill trees."""
    def snapshot(root: Path) -> dict:
        return {str(p.relative_to(root)): p.read_bytes()
                for p in sorted(root.rglob("*")) if p.is_file()}
    try:
        return snapshot(src) == snapshot(dst)
    except OSError:
        return False


def upgrade_onboarding(block: str, repo: Path, changes: list, dry_run: bool,
                       write: bool = False) -> None:
    """Refresh the sentinel-delimited block, unless the adopter has edited it.

    Writing through a symlink is deliberate: `CLAUDE.md` is often a link to
    `AGENTS.md`, and `write_text` follows it, so the target is edited and the link
    survives. Adopt has warned about that rule in prose since it shipped; here it
    falls out of the implementation.

    What does *not* fall out of the implementation, and used to be wrong: the
    sentinels mark the block hypergraph owns, and adopt writes per-project content
    inside them anyway, because that is where the contract reconciliation belongs.
    So the block is only ours to replace while it is still verbatim something we
    shipped (`SHIPPED_BLOCK_DIGESTS`). Once an adopter has edited it, an upgrade
    reports and steps back — `--agents-block` is the way to say "overwrite it, I
    have merged what I wanted"."""
    seen: set[Path] = set()
    for name in ONBOARDING_FILES:
        path = repo / name
        if not path.exists():
            continue
        resolved = path.resolve()
        if resolved in seen:      # CLAUDE.md → AGENTS.md: one file, edited once
            continue
        text = path.read_text(errors="replace")
        current = extract_agents_block(text)
        if current is None:
            continue              # no block: this file never had one, so leave it
        seen.add(resolved)
        if block_digest(current) == block_digest(block):
            changes.append(("unchanged", path, ""))
            continue
        if block_digest(current) not in SHIPPED_BLOCK_DIGESTS and not write:
            changes.append(("customized", path,
                            "local edits inside the sentinels — pass --agents-block "
                            "to overwrite"))
            continue
        updated = replace_agents_block(text, block)
        if not dry_run:
            path.write_text(updated)
        note = "hypergraph block" + (" — overwrote local edits" if write else "")
        changes.append(("refreshed", path, note))


def upgrade_workflows(source: Path, repo: Path, changes: list, dry_run: bool,
                      write: bool) -> None:
    """Report drifted CI workflows; rewrite them only when asked.

    Workflows are the one copied artifact adopters genuinely edit — a different base
    branch, an extra step, a self-hosted runner. Overwriting that by default would
    make `upgrade` something you cannot run without reading the diff first, so the
    default reports and `--workflows` acts."""
    target_dir = repo / ".github" / "workflows"
    for src in sorted(source.glob("*.yml")):
        dst = target_dir / src.name
        if not dst.exists():
            continue              # never had it — upgrade does not opt anyone into CI
        if dst.read_bytes() == src.read_bytes():
            changes.append(("unchanged", dst, ""))
            continue
        if not write:
            changes.append(("differs", dst, "pass --workflows to overwrite"))
            continue
        if not dry_run:
            dst.write_bytes(src.read_bytes())
        changes.append(("refreshed", dst, ""))


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Bring an adopted repo's *copies* up to the running CLI's release."""
    repo = Path(args.repo or ".").resolve()
    root = skills_data_root()
    if is_source_checkout(repo, root):
        raise LocalGraphError(
            f"{repo} is the protocol's own checkout, not a project that adopted it. "
            "Its skills are the dogfooding symlinks into `skills/` and its publish "
            "workflow deliberately differs from the shipped template — refreshing "
            "either from the package would overwrite the source with a copy of "
            "itself. Run `upgrade` in an adopted repo, or pass --repo.")

    changes: list = []
    # Scope mirrors `skills install`: project by default, `--user` for ~/.claude.
    # Refreshing both implicitly would edit files outside the repo you named, which
    # is not something a repo-scoped command should do without being asked.
    skills_target = (Path.home() / ".claude" / "skills" if args.user
                     else repo / ".claude" / "skills")
    upgrade_skills(root / "skills", skills_target, changes, args.dry_run)
    block_path = root / "templates" / "agents-block.md"
    if block_path.exists():
        upgrade_onboarding(block_path.read_text(), repo, changes, args.dry_run,
                           args.agents_block)
    upgrade_workflows(root / "templates" / "github-actions", repo, changes,
                      args.dry_run, args.workflows)

    config_path = Path(args.config) if args.config else repo / ".hypergraph" / "config.yml"
    if config_path.exists():
        text = config_path.read_text()
        stamped = stamp_config_version(text, __version__)
        if stamped == text:
            changes.append(("unchanged", config_path, f"hypergraph_version: {__version__}"))
        else:
            if not args.dry_run:
                config_path.write_text(stamped)
            changes.append(("refreshed", config_path, f"hypergraph_version: {__version__}"))
    else:
        changes.append(("skipped", config_path, "no config — not an adopted project"))

    verb = {"refreshed": "would refresh", "unchanged": "unchanged",
            "skipped": "skipped", "differs": "differs",
            "customized": "customized"} if args.dry_run else {}
    for state, path, note in changes:
        label = verb.get(state, state)
        try:
            shown = path.relative_to(repo)
        except ValueError:
            shown = path
        print(f"  {label:<14} {shown}" + (f"   ({note})" if note else ""))
    touched = sum(1 for state, _p, _n in changes if state == "refreshed")
    drifted = [c for c in changes if c[0] == "differs"]
    kept = [c for c in changes if c[0] == "customized"]
    tail = ((f", {len(drifted)} workflow(s) differ" if drifted else "")
            + (f", {len(kept)} block(s) left alone" if kept else ""))
    if not changes or all(c[0] != "refreshed" for c in changes):
        print(f"\nupgrade: already current at {__version__}" + tail.replace(",", " —", 1))
    else:
        print(f"\nupgrade: {touched} item(s) "
              f"{'would be refreshed' if args.dry_run else 'refreshed'} to {__version__}"
              + tail)
    if kept:
        # Naming the shipped copy is the whole remedy: the adopter diffs it against
        # their block and merges by hand, which is the only safe merge of prose that
        # is half ours and half theirs.
        print(f"\nThe block in {len(kept)} file(s) carries edits of your own, so it "
              f"was left as it is.\nCompare it against this release's version and "
              f"merge what you want:\n  {block_path}")
    if not args.dry_run and touched:
        print("Commit the result — these files travel with the repo.")

    # `upgrade` refreshes *copies*; it never touches graph content. But it is the one
    # command an adopter runs after a release, so it is the only place that will
    # reliably tell them a *graph* repair is now available. Computed offline from each
    # healer's `blocked_by` — and deliberately not keyed off `hypergraph_version:`,
    # which SPEC calls "not a compatibility floor". Stamping it here would falsely
    # assert the heals had run.
    config = load_config(config_path) if config_path.exists() else {}
    applicable = [h for h, reason in applicable_heals(config, repo) if reason is None]
    if applicable:
        print(f"\n{len(applicable)} retroactive graph repair(s) apply to this project.")
        for healer in applicable:
            print(f"  heal {healer.name:<10} {healer.summary} (since {healer.since})")
        print("\nThese rewrite graph content, not copies, so they are a separate "
              "command\nand detect-only by default:\n"
              f"  hypergraph heal {applicable[0].name}")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    root = skills_data_root()
    source = root / "skills"
    if args.target:
        target = Path(args.target)
    elif args.user:
        target = Path.home() / ".claude" / "skills"
    else:
        target = Path.cwd() / ".claude" / "skills"
    target.mkdir(parents=True, exist_ok=True)
    installed = []
    for src in sorted(source.glob("hypergraph-*")):
        if not src.is_dir():
            continue
        dst = target / src.name
        if _links_into(dst, source):
            raise LocalGraphError(
                f"{dst} is already linked to the source ({src}) — nothing to install. "
                "This is a dev checkout where the skills are dogfooded through "
                "symlinks; installing would replace the live skill with a stale copy. "
                "Use --target DIR to install elsewhere.")
        if dst.is_symlink():  # a link to somewhere else — replace it wholesale
            dst.unlink()
        if args.link:
            # A link edits-through: the installed skill is never a stale snapshot.
            # Only safe where the source tree stays put (a dev checkout, not a wheel).
            if dst.exists():
                shutil.rmtree(dst)
            dst.symlink_to(src.resolve(), target_is_directory=True)
        else:
            # symlinked references/ entries are materialized as real files on copy,
            # so the installed skill is self-contained
            shutil.copytree(src, dst, dirs_exist_ok=True)
        installed.append(src.name)
    if not installed:
        raise LocalGraphError(f"no hypergraph-* skills found under {source}")
    verb = "linked" if args.link else "installed"
    for name in installed:
        print(f"{verb} {target / name}")
    return 0


# ------------------------------------------------------------------- upgrading
# An adopted repo carries *copies* of things this package ships: the five skills
# under `.claude/skills/`, the sentinel-delimited AGENTS.md block, and sometimes the
# CI workflows. `uv tool upgrade` refreshes the CLI and cannot see any of them, so
# before this command the only way a fix reached an adopter's skill was for someone
# to remember to say so. That is how the 0.0.6 adoption fixes shipped into a package
# whose *installed* skill still described the step order they fixed.
#
# The contract is deliberately narrow: **refresh what is already there, never
# install what is not.** An upgrade that quietly adds CI to a repo that never wanted
# it is a worse failure than a stale file.

AGENTS_BEGIN = "<!-- hypergraph:begin -->"
AGENTS_END = "<!-- hypergraph:end -->"
ONBOARDING_FILES = ("AGENTS.md", "CLAUDE.md", ".hypergraph/AGENTS.md")

# Every agents-block this project has ever shipped, by content digest.
#
# The sentinels do **not** mean "ours to overwrite". hypergraph-adopt's step 8
# deliberately writes per-project content *inside* them — the contract
# reconciliation that routes an existing discipline through hypergraph, and the
# project's epoch note — so a block in the wild is a mixture of our template and
# the adopter's own prose, often woven into the same sentence.
#
# That leaves one honest question an upgrade can ask: *did anyone edit this?* A
# block whose digest is in this set is a template we shipped and nobody touched,
# so replacing it loses nothing. Anything else is the adopter's, and gets
# reported rather than overwritten — the same treatment `.github/workflows/`
# already gets, and for the same reason.
#
# Add a line here whenever templates/agents-block.md changes;
# `test_shipped_block_digest_is_registered` fails until you do.
SHIPPED_BLOCK_DIGESTS = frozenset({
    # 0.0.1–0.0.6
    "9119d3e23dbac92888b7f420213b2307d280b8d584c62c02d6ac6dbe4d53330c",
    # 0.0.7 — adds the `hypergraph upgrade` note to non-negotiable 4
    "c0698b961c95a5c98a1e3df40cba88e5917db5d02e427c6fa4c7727a57feafa0",
    # 0.0.8 — says what the two graphs are for, not just where they live
    "0e6bd61095cb87c87cb96d5c74c52e18ad0dc22f5f6a5ae2dd636f4d4961a7d3",
})


def block_digest(block: str) -> str:
    """Content digest of a sentinel block, insensitive to surrounding whitespace.

    Files gain and lose a trailing newline as editors touch them; that is not an
    edit to the block, and treating it as one would report every adopter as
    having customized their onboarding."""
    return hashlib.sha256(block.strip().encode()).hexdigest()


def extract_agents_block(text: str) -> str | None:
    """The sentinel block including its markers, or None when there is none."""
    start = text.find(AGENTS_BEGIN)
    end = text.find(AGENTS_END)
    if start < 0 or end < 0 or end < start:
        return None
    return text[start:end + len(AGENTS_END)]


def version_tuple(text: str) -> tuple[int, ...] | None:
    """`0.0.6` → `(0, 0, 6)`; anything else → None (never guess at an ordering)."""
    parts = str(text).strip().split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def check_version_skew(config: dict, report: Report) -> None:
    """Compare the version that installed this repo's copies against the running CLI.

    `hypergraph_version:` records which release last wrote the skills, the AGENTS.md
    block and the workflows into this repo — not a compatibility floor. The node
    files are additive markdown and an older CLI reads a newer graph fine; what goes
    stale is the *copies*, silently, because nothing else in the repo names a version.

    Always a warning, never a violation. Failing someone's CI because their skill
    files are a release behind would be hostile, and the skew is often deliberate."""
    declared = config.get("hypergraph_version")
    if declared is None:
        report.add("info", "-", "config",
                   "no `hypergraph_version:` — this project's skills and AGENTS.md "
                   "block predate the stamp, so nothing can tell whether they are "
                   "current. `hypergraph upgrade` refreshes them and adds it.")
        return
    theirs, ours = version_tuple(declared), version_tuple(__version__)
    if theirs is None or ours is None or theirs == ours:
        return
    if theirs < ours:
        report.add("warning", "-", "config",
                   f"this project's skills and AGENTS.md block were installed by "
                   f"{declared}; the CLI here is {__version__}. The node files are "
                   f"fine — the copies are stale. Run `hypergraph upgrade`.")
    else:
        report.add("warning", "-", "config",
                   f"this project was set up by {declared} and the CLI here is "
                   f"{__version__} — the CLI is the old half. Run "
                   f"`uv tool upgrade hypergraph-protocol`.")


def is_source_checkout(repo: Path, source_root: Path) -> bool:
    """Is `repo` the protocol's own tree, rather than a project that adopted it?

    Refusing here is not politeness. This repo's `.claude/skills/hypergraph-*` are
    committed symlinks into `skills/` (the dogfooding), and its publish workflow
    deliberately differs from the shipped template — it runs the CLI out of the
    checkout. Refreshing either from the package would destroy a difference that is
    the point."""
    try:
        return repo.resolve() == source_root.resolve()
    except OSError:
        return False


def replace_agents_block(text: str, block: str) -> str | None:
    """Swap what is between the sentinels. None when the file has no block.

    Everything outside the markers is the adopter's own prose and must survive
    verbatim — that is what the markers were introduced for."""
    start = text.find(AGENTS_BEGIN)
    end = text.find(AGENTS_END)
    if start < 0 or end < 0 or end < start:
        return None
    return text[:start] + block.strip() + text[end + len(AGENTS_END):]


def stamp_config_version(text: str, version: str) -> str:
    """Set `hypergraph_version:` without reformatting the rest.

    A config is hand-edited and comment-heavy (hypergraph-init writes it from the
    template by hand), so this is a line edit, not a YAML round-trip: dumping the
    parsed document back would silently delete every comment in it."""
    line = f"hypergraph_version: {version}"
    if re.search(r"^hypergraph_version:.*$", text, flags=re.M):
        return re.sub(r"^hypergraph_version:.*$", line, text, count=1, flags=re.M)
    comment = ("# The release that last installed this project's skills, AGENTS.md\n"
               "# block and workflows — refreshed by `hypergraph upgrade`.\n")
    match = re.search(r"^project:.*$", text, flags=re.M)
    if match:
        return f"{text[:match.end()]}\n\n{comment}{line}{text[match.end():]}"
    return text.rstrip("\n") + f"\n\n{comment}{line}\n"


# ---------------------------------------------------------------------- healing
# `upgrade` answers "are this repo's *copies* current". `heal` answers "is this
# repo's *graph content* current" — and they are separate commands because the
# answers cost different things. Every effect of `upgrade` is a file we shipped and
# `git checkout` undoes it. `heal` rewrites the graph itself and spends an
# irreversible mirror-write budget, so it cannot share `upgrade`'s "just run it"
# posture.
#
# The framework exists because tags will not be the last capability to land after
# somebody's adoption. Healer number two must cost **one registry entry and one
# comparator** — that is the whole extensibility claim, and
# `test_registry_names_unique_ordering_acyclic_archive_readers_never_write` is what
# holds it honest.
#
# **Nothing is persisted.** No "have I run?" flag, no journal, no version stamp. The
# written data *is* the state and `detect` re-derives it from the files — the same
# property that makes `push_plan` a safe resume primitive. A heal that recorded its
# own completion could lie; one that re-derives cannot.

@dataclass(frozen=True)
class Change:
    """One thing a healer did, or declined to do, to one target."""
    state: str        # healed | unchanged | skipped | blocked | refused
    target: object
    note: str = ""


@dataclass
class HealContext:
    """Everything a healer may read. Deliberately not a grab-bag: a healer that needs
    something not in here is a healer whose blast radius nobody has thought about."""
    repo: Path
    graph_dir: Path
    config: dict
    args: argparse.Namespace
    out: object = print
    offline: bool = True
    session: object = None     # (transport, journal, pacer, cache_dir), built lazily
    source: object = None      # the archive export, read once per run
    vocab: object = None       # the source vocabulary, transliterated once per run


@dataclass(frozen=True)
class Healer:
    """One retroactive repair: what it reads, what it writes, and why it may not run."""
    name: str
    summary: str
    since: str                       # the release the capability landed in
    reads: str                       # archive | mirror | local
    writes: tuple                    # ("frontmatter", "mirror")
    detect: object                   # (HealContext) -> list[Drift]
    apply: object                    # (HealContext, list[Drift]) -> list[Change]
    blocked_by: object               # (config, repo) -> a REASON string, or None
    after: tuple = ()                # healer names that must run first


def heal_write_targets(graph_dir: Path, config: dict) -> dict[str, str]:
    """{slug: mirror node id}, read from `flywheel:` and **never** from `origin:`.

    This mechanizes a guardrail hypergraph-adopt has only ever stated in prose:
    *never write, tag, or re-parent archive nodes.* In an adopted repo every
    `origin.node_id` is an id on the frozen archive — the same shape as a mirror id,
    resolvable by the same credentials, and one attribute lookup away in the same
    dict. A healer reaching for the wrong one would write the archive with the
    mirror's key and nothing else in this file would stop it.

    So there is exactly one sanctioned way to obtain a write target, and it refuses
    when the two have been confused."""
    archive_ids = {str(r.get("node_id")) for r in (config.get("archive") or {}).get("roots", [])
                   if isinstance(r, dict) and r.get("node_id")}
    targets: dict[str, str] = {}
    for kind in GRAPH_KINDS:
        for node in load_local_nodes(graph_dir, kind, missing_ok=True).values():
            node_id = str((node.meta.get("flywheel") or {}).get("node_id") or "")
            if not node_id:
                continue
            origin_id = str((node.meta.get("origin") or {}).get("node_id") or "")
            if origin_id and node_id == origin_id:
                raise LocalGraphError(
                    f"{node.path}: `flywheel.node_id` and `origin.node_id` are the same "
                    f"id ({node_id}). On an adopted project the origin is the frozen "
                    "archive, so writing there would edit history this project promised "
                    "never to touch. Refusing to treat it as a write target.")
            if node_id in archive_ids:
                raise LocalGraphError(
                    f"{node.path}: `flywheel.node_id` is a declared `archive:` root "
                    f"({node_id}). The archive is frozen; this project never writes to it.")
            targets[node.slug] = node_id
    return targets


def heal_source_export(ctx: HealContext) -> tuple[object, str]:
    """Where a healer reads the archive from: `--source`, the pull cache, or a live
    read-only export. → (parsed export, a human description of where it came from).

    The cache is tried before the network on purpose: a repo that adopted through
    `mirror pull` already has every source node on disk, so the common repair needs no
    credentials at all. Read once per run: `detect` and `apply` both need it, and the
    live path would otherwise export the archive twice."""
    if ctx.source is not None:
        return ctx.source
    ctx.source = _heal_source_export(ctx)
    return ctx.source


def _heal_source_export(ctx: HealContext) -> tuple[object, str]:
    explicit = getattr(ctx.args, "source", None)
    if explicit:
        return json.loads(Path(explicit).read_text()), str(explicit)
    cache_dir = Path(ctx.config.get("cache_dir") or (ctx.graph_dir.parent / "cache"))
    cached = cache_dir / "mirror-pull.json"
    if cached.exists():
        return json.loads(cached.read_text()), str(cached)
    if ctx.offline:
        raise LocalGraphError(
            f"no source graph to read: pass --source PATH, or drop --offline so the "
            f"archive can be exported live. Looked for {cached}.")
    roots = [str(r.get("node_id")) for r in (ctx.config.get("archive") or {}).get("roots", [])
             if isinstance(r, dict) and r.get("node_id")]
    if not roots:
        raise LocalGraphError(
            "no `archive:` roots in the config and no cached pull — nothing to read "
            "the original tags from. Pass --source PATH.")
    transport, _journal, _pacer, cache = heal_session(ctx)
    # Read-only. The archive is frozen and this is the one place a heal touches it.
    export = transport.export_subgraph(roots, cache / "heal-source.json")
    return json.loads(Path(export).read_text()), str(export)


def heal_session(ctx: HealContext):
    if ctx.session is None:
        if ctx.offline:
            raise LocalGraphError("this step needs the mirror, and --offline was passed")
        ctx.session = mirror_session(ctx.config, ctx.args)
    return ctx.session


# --------------------------------------------------------------- healer 1: tags

def tags_blocked_by(config: dict, repo: Path) -> str | None:
    """→ why `heal tags` does not apply here, or None when it does."""
    graph_dir = Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    if not (repo / graph_dir).is_dir() and not graph_dir.is_dir():
        return "no graph directory — this is not a hypergraph project"
    root = repo / graph_dir if (repo / graph_dir).is_dir() else graph_dir
    imported = 0
    for kind in GRAPH_KINDS:
        for node in load_local_nodes(root, kind, missing_ok=True).values():
            if (node.meta.get("origin") or {}).get("node_id"):
                imported += 1
    if not imported:
        return ("no node carries `origin:` — nothing was imported from another graph, "
                "so there are no original tags to recover")
    return None


def heal_tag_vocabulary(ctx: HealContext) -> tuple[dict[str, str], list[dict]]:
    """({archive tag_id: local name}, definitions), transliterated exactly as `import`
    would have done.

    Not a detail. A repo healed today and a repo imported tomorrow must end up with
    the *same* names, or `★ studio-baseline` and `studio-baseline` become two tags
    that mean one thing — which is the duplicate-definition failure by another route.

    Cached on the context: `detect` and `apply` both need it, and every rename it
    reports must be said once, not once per caller."""
    if ctx.vocab is not None:
        return ctx.vocab
    data, _where = heal_source_export(ctx)
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    raw_nodes = [r for r in (raw_nodes or []) if isinstance(r, dict)]
    ctx.vocab = import_tag_vocabulary(
        raw_nodes, fork=True, pushed_at=str(utc_now()),
        out=lambda m: ctx.out(m.replace("import:", "heal tags:")))
    return ctx.vocab


def tags_detect(ctx: HealContext) -> list[Drift]:
    """The archive's tags against ours, matched on `origin.node_id`.

    Every match is exact: an imported node's `origin.node_id` **is** its archive id,
    so there is no fuzzy matching anywhere in this healer and no case where it has to
    guess which node it is looking at."""
    data, where = heal_source_export(ctx)
    ctx.out(f"heal tags: reading the source graph from {where}")
    by_id, _defs = heal_tag_vocabulary(ctx)
    local = side_from_local(ctx.graph_dir, key="origin", name="repo")
    archive = side_from_export(data, key="node_id", name="archive")
    for record in archive.records:
        record["tags"] = sorted({by_id[str(t)]
                                 for t in ((record["raw"] or {}).get("tag_ids") or [])
                                 if str(t) in by_id})
    drifts = diff_graphs(local, archive, fields=("tags",))
    # Only tag drift is this healer's business. A node with no `origin:` (authored
    # after the adoption) and a node the archive no longer holds are both normal.
    return [d for d in drifts if d.kind == "field" and d.field == "tags"]


def tags_apply(ctx: HealContext, drifts: list[Drift]) -> list[Change]:
    """Two separable phases: frontmatter offline, then the mirror."""
    changes: list[Change] = []
    tags_path = tags_file_for(ctx.config, ctx.graph_dir)
    vocab = load_tag_vocab(tags_path)

    # --- phase 1: the repo, offline --------------------------------------------
    _by_id, tag_defs = heal_tag_vocabulary(ctx)
    local = {}
    for kind in GRAPH_KINDS:
        for slug, node in load_local_nodes(ctx.graph_dir, kind, missing_ok=True).items():
            local[slug] = (kind, node)

    names_by_kind: dict[str, set[str]] = {k: set() for k in GRAPH_KINDS}
    for drift in drifts:
        slug = drift.left_ref
        entry = local.get(slug)
        if entry is None:
            changes.append(Change("skipped", slug, "no longer a node in this repo"))
            continue
        kind, node = entry
        theirs = sorted(str(t) for t in (drift.right or []))
        if node.tags and sorted(node.tags) != theirs:
            # Never overwrite an authored tag set. A repair that can destroy work
            # is not a repair, and this is the only case where the two disagree.
            changes.append(Change("skipped", slug,
                                  f"local tags {sorted(node.tags)} differ from the "
                                  f"archive's {theirs} — heal never overwrites an "
                                  "authored tag set"))
            continue
        if not theirs:
            changes.append(Change("unchanged", slug, "no tags on the archive node"))
            continue
        names_by_kind[kind].update(theirs)
        meta = dict(node.meta)
        meta["tags"] = theirs
        text = render_node_file(meta, node.content)
        # Byte-compare before writing: a no-op heal must touch zero files, or every
        # run leaves a diff and the idempotence claim is unverifiable.
        if text == node.path.read_text():
            changes.append(Change("unchanged", node.path, ""))
            continue
        if ctx.args.apply:
            node.path.write_text(text)
        changes.append(Change("healed", node.path, f"{len(theirs)} tag(s)"))

    # The vocabulary is declared per graph kind, so a name is declared under exactly
    # the graphs whose nodes carry it — `tags:create` is per graph root.
    declared = 0
    for entry in tag_defs:
        for kind, names in names_by_kind.items():
            if str(entry["name"]) in names:
                merge_tag_def(vocab, kind, entry)
                declared += 1
    if declared:
        if ctx.args.apply:
            write_tag_vocab(tags_path, vocab)
        changes.append(Change("healed", tags_path, f"{declared} tag definition(s)"))

    # --- phase 2: the mirror ----------------------------------------------------
    if ctx.offline:
        changes.append(Change("skipped", "mirror",
                              "--offline: the vocabulary and assignments were not "
                              "published. Commit the frontmatter, then re-run without "
                              "--offline (or just `hypergraph push`)."))
        return changes
    if not mirror_configured(ctx.config):
        changes.append(Change("skipped", "mirror", "no mirror configured"))
        return changes
    if blocked := publish_branch_block(ctx.config, cwd=ctx.repo):
        changes.append(Change("blocked", "mirror", blocked))
        return changes
    # The one sanctioned way to obtain a write target. Raises rather than returns if
    # `origin:` and `flywheel:` have been confused anywhere in the graph.
    targets = heal_write_targets(ctx.graph_dir, ctx.config)
    if not targets:
        changes.append(Change("skipped", "mirror",
                              "no node carries `flywheel:` — nothing has been pushed "
                              "yet, so `hypergraph push` is the right command"))
        return changes
    if not ctx.args.apply:
        changes.append(Change("healed", "mirror",
                              f"would publish tags for up to {len(targets)} node(s)"))
        return changes
    transport, _journal, pacer, _cache = heal_session(ctx)
    if reason := mirror_not_ours(ctx.config, transport):
        changes.append(Change("blocked", "mirror", reason))
        return changes
    assigned = push_tags(ctx.graph_dir, ctx.config, mirror_root_ids(ctx.config),
                         transport, pacer=pacer, out=ctx.out)
    changes.append(Change("healed", "mirror", f"{assigned} node(s) tagged on the mirror"))
    return changes


HEAL_TAGS = Healer(
    name="tags",
    summary="carry the original graph's tag names into node frontmatter, "
            ".hypergraph/tags.yml, and the mirror",
    since="0.0.9",
    reads="archive",
    writes=("frontmatter", "mirror"),
    detect=tags_detect,
    apply=tags_apply,
    blocked_by=tags_blocked_by,
)

# The registry. A new healer is one entry here plus, if it compares a new field, one
# entry in FIELD_COMPARATORS. Nothing else.
HEALERS: tuple = (HEAL_TAGS,)


def healer_by_name(name: str) -> Healer:
    for healer in HEALERS:
        if healer.name == name:
            return healer
    raise LocalGraphError(
        f"no healer named `{name}` (have: {', '.join(h.name for h in HEALERS)})")


def healers_in_order(names: list[str]) -> list[Healer]:
    """Requested healers, with each one's `after:` dependencies respected."""
    wanted = [healer_by_name(n) for n in names]
    ordered: list[Healer] = []
    for healer in HEALERS:            # registry order is the tie-break, and is stable
        if healer in wanted:
            ordered.append(healer)
    for healer in ordered:
        for dependency in healer.after:
            if dependency in names and \
                    [h.name for h in ordered].index(dependency) > ordered.index(healer):
                raise LocalGraphError(
                    f"healer `{healer.name}` must run after `{dependency}`, but the "
                    "registry orders them the other way round")
    return ordered


def applicable_heals(config: dict, repo: Path) -> list[tuple]:
    """[(healer, reason-or-None)] — computed **offline**, so `upgrade` can print it.

    Not keyed off `hypergraph_version:`. SPEC calls that stamp "not a compatibility
    floor", and letting `upgrade` bump it would falsely assert that heals had run."""
    out = []
    for healer in HEALERS:
        try:
            reason = healer.blocked_by(config, repo)
        except LocalGraphError as exc:
            reason = str(exc)
        out.append((healer, reason))
    return out


def heal_dirty_block(graph_dir: Path, repo: Path) -> str | None:
    """→ why the graph directory is not safe to rewrite, or None.

    Scoped to `graph_dir`, not the repo: heal rewrites node files, and an unrelated
    dirty file elsewhere is not this command's business.

    This deliberately does **not** copy `push`'s stance of having no dirty-tree guard.
    That exemption exists because reconcile publishes *before* it commits, so a dirty
    graph is the expected state at push time. Nothing about heal is inside that flow —
    it rewrites ~188 files at once, outside any commit, and an uncommitted edit
    underneath it has no diff to recover from."""
    if not _git(repo, "rev-parse", "--is-inside-work-tree").strip():
        return None
    dirty = _git(repo, "status", "--porcelain", "--", str(graph_dir)).strip()
    if not dirty:
        return None
    count = len(dirty.splitlines())
    return (f"{count} uncommitted change(s) under {graph_dir}. Heal rewrites node "
            "files in place, and an uncommitted edit underneath has no committed diff "
            "to recover from. Commit or stash first, or pass --allow-dirty.")


def cmd_heal(args: argparse.Namespace) -> int:
    """Carry a capability backwards into a repo that adopted before it existed.

    **Dry run is the default here, and opt-in everywhere else in this CLI.** That
    inversion is deliberate and worth stating rather than leaving as folklore: heal is
    human-initiated, sits in no commit flow, rewrites the whole graph at once, and
    spends mirror writes that cannot be un-spent. `--apply` is the word that makes it
    act."""
    repo = Path(args.repo or ".").resolve()
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)

    names = [h.name for h in HEALERS] if args.all else list(args.healer or [])
    if not names:
        return heal_list(config, repo, json_out=args.json)

    root = skills_data_root()
    if is_source_checkout(repo, root):
        raise LocalGraphError(
            f"{repo} is the protocol's own checkout. Its graph was authored under this "
            "release, so there is nothing retroactive to repair — and a heal here would "
            "rewrite the reference graph the tests read. Run `heal` in an adopted repo, "
            "or pass --repo.")

    healers = healers_in_order(names)
    if args.apply and not args.allow_dirty:
        if blocked := heal_dirty_block(graph_dir, repo):
            raise LocalGraphError(f"refusing to heal: {blocked}")

    ctx = HealContext(repo=repo, graph_dir=graph_dir, config=config, args=args,
                      offline=args.offline,
                      out=lambda m: print(m) if not args.json else None)

    exit_code = 0
    payload: dict = {"repo": str(repo), "apply": bool(args.apply), "healers": []}
    for healer in healers:
        reason = healer.blocked_by(config, repo)
        if reason:
            if args.json:
                payload["healers"].append({"name": healer.name, "blocked_by": reason})
            else:
                print(f"\n{healer.name}: does not apply — {reason}")
            continue

        drifts = healer.detect(ctx)
        if args.limit is not None:
            if len(drifts) > args.limit:
                # Never a silent cap: a truncated run that reads as "all clear" is
                # worse than no run at all.
                print(f"heal {healer.name}: --limit {args.limit} of "
                      f"{len(drifts)} finding(s); the rest are NOT addressed",
                      file=sys.stderr)
            drifts = drifts[:args.limit]

        report = Report()
        for drift in drifts:
            report.add("warning", "heal", drift.ref,
                       f"{healer.name}: {drift.field} differs — "
                       f"repo {drift.left!r}, {healer.reads} {drift.right!r}")
        entry = {"name": healer.name, "drift": len(drifts),
                 "findings": [{"node": f.node, "message": f.message}
                              for f in report.findings]}

        if not args.apply:
            if not args.json:
                for finding in report.findings:
                    print(f"  drift     {finding}")
                changes = healer.apply(ctx, drifts) if drifts else []
                print(f"\nheal {healer.name}: {len(drifts)} node(s) would change "
                      f"({healer.since}, reads {healer.reads}, writes "
                      f"{'/'.join(healer.writes)})")
                _print_changes(changes, repo, dry_run=True)
                if drifts:
                    print("\nThis was a dry run — nothing was written. "
                          f"`hypergraph heal {healer.name} --apply` acts.")
            entry["changes"] = []
            payload["healers"].append(entry)
            # Detected drift alone is **exit 0**. Unhealed drift is a capability that
            # landed after your adoption, not a broken invariant — the same reasoning
            # as `check_version_skew`, which is a warning for the same reason.
            if drifts and args.fail_on_drift:
                exit_code = 1
            continue

        changes = healer.apply(ctx, drifts)
        entry["changes"] = [{"state": c.state, "target": str(c.target), "note": c.note}
                            for c in changes]
        if not args.json:
            _print_changes(changes, repo, dry_run=False)
        # The registry rule, checked at runtime as well as in the tests: every effect
        # a healer claims must be visible to the next detect. What it skipped stays
        # drifted, and that is fine; what it healed must not.
        skipped = {str(c.target) for c in changes if c.state == "skipped"}
        residual = [d for d in healer.detect(ctx)
                    if d.ref not in skipped and d.left_ref not in skipped]
        entry["residual"] = len(residual)
        if residual:
            if not args.json:
                print(f"\nheal {healer.name}: {len(residual)} finding(s) survived the "
                      "repair — the heal did not do what it reported")
            exit_code = 1
        payload["healers"].append(entry)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return exit_code


def _print_changes(changes: list, repo: Path, *, dry_run: bool) -> None:
    verb = {"healed": "would heal", "unchanged": "unchanged", "skipped": "skipped",
            "blocked": "blocked", "refused": "refused"} if dry_run else {}
    for change in changes:
        try:
            shown = Path(change.target).relative_to(repo)
        except (ValueError, TypeError):
            shown = change.target
        label = verb.get(change.state, change.state)
        print(f"  {label:<14} {shown}" + (f"   ({change.note})" if change.note else ""))


def heal_list(config: dict, repo: Path, *, json_out: bool = False) -> int:
    """`hypergraph heal` with no healer named: the registry and what applies here."""
    rows = applicable_heals(config, repo)
    if json_out:
        print(json.dumps({"healers": [
            {"name": h.name, "summary": h.summary, "since": h.since, "reads": h.reads,
             "writes": list(h.writes), "blocked_by": reason}
            for h, reason in rows]}, indent=2, ensure_ascii=False))
        return 0
    print("Retroactive repairs. Each carries a capability backwards into a repo that\n"
          "adopted before it existed. Detection is read-only; nothing writes without\n"
          "--apply.\n")
    for healer, reason in rows:
        mark = "applies" if reason is None else "n/a"
        print(f"  {healer.name:<10} [{mark}]  {healer.summary}")
        print(f"  {'':<10}         since {healer.since}, reads the {healer.reads}, "
              f"writes {' + '.join(healer.writes)}")
        if reason:
            print(f"  {'':<10}         → {reason}")
    applicable = [h for h, reason in rows if reason is None]
    if applicable:
        print(f"\n  hypergraph heal {applicable[0].name}            # detect only "
              "(the default)\n"
              f"  hypergraph heal {applicable[0].name} --apply    # rewrite the graph "
              "and publish")
    return 0


# ---------------------------------------------------------------- mirror errors
# Everything below is the optional one-way mirror (backend/mirror.md). It is
# reachable only from `push` / `sync` / `mirror`, and only when the config declares
# a mirror — `check`, `render`, `viz`, `export`, `import`, `new`, `update` and
# `skills` must never resolve a credential, look for a binary, or import a network
# module. That is why `time`, `urllib` and `os` are imported lazily inside the
# methods that need them, matching the deferred `import yaml` above.

class MirrorError(LocalGraphError):
    """Anything wrong on the mirror path.

    Subclasses LocalGraphError, so main()'s existing handler renders every one of
    these as `error: <one line>` and exits 2 with no extra plumbing."""


class MirrorUnavailable(MirrorError):
    """No usable transport: the binary is absent, or no credentials exist."""


class MirrorAuthError(MirrorError):
    """401/403. Aborts before any node file is stamped — a key that can read but not
    write must not leave the graph half-pushed."""


class MirrorConflict(MirrorError):
    """409. Never blind-retried: under SPEC I3 there is one writer, so a conflict is
    evidence that something else wrote."""


class MirrorRateLimited(MirrorError):
    """429. Carries the server's Retry-After when it supplied one."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class MirrorNode:
    """One node as the host returned it. Constructed only through `from_raw`."""
    node_id: str
    slug: str
    title: str
    content: str
    summary: str
    revision: int | None
    can_write: bool | None = None
    is_owner: bool | None = None

    @property
    def sha256(self) -> str:
        return body_sha256(self.content)

    @staticmethod
    def _bool(value: object) -> bool | None:
        # the CLI stringifies booleans in JSON output ("True"/"False")
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        return None

    @classmethod
    def from_raw(cls, raw: object, *, context: str, need_revision: bool = True) -> "MirrorNode":
        """Probe the response shape and fail loudly.

        Every mutating endpoint's success schema in the live OpenAPI is literally
        `{}`, so nothing here may be assumed. In particular **never default
        `revision` to 0**: `revision: 0` is a real value (this repo's own mirror
        roots sit at 0), and a wrongly-defaulted 0 makes every later update conflict
        forever. An absent revision stays `None`, and the caller must read the live
        one rather than invent it."""
        if isinstance(raw, dict) and isinstance(raw.get("node"), dict):
            raw = raw["node"]  # some responses wrap the node
        if not isinstance(raw, dict):
            raise MirrorError(f"{context}: expected a node object, got {type(raw).__name__}")
        node_id = str(raw.get("node_id") or raw.get("id") or "")
        if not node_id:
            raise MirrorError(
                f"{context}: response carries no node_id (keys: "
                f"{sorted(raw)[:8]}) — refusing to guess what was written")
        revision = raw.get("revision", raw.get("committed_revision"))
        if revision is None and need_revision:
            raise MirrorError(
                f"{context}: response for {node_id} carries no revision. Refusing to "
                "assume 0 — a wrong base revision makes every later update conflict.")
        return cls(
            node_id=node_id,
            slug=str(raw.get("slug_name") or raw.get("slug") or ""),
            title=str(raw.get("title") or ""),
            content=str(raw.get("content") or ""),
            summary=str(raw.get("summary") or ""),
            revision=int(revision) if revision is not None else None,
            can_write=cls._bool(raw.get("can_write")),
            is_owner=cls._bool(raw.get("is_owner")),
        )


# ------------------------------------------------------------- mirror transport

MIRROR_CLI_BINARY = "flywheel"
# All six keys are required by the host, null where not applicable.
EMPTY_REPO_CONTEXT = {"repo_url": None, "branch_name": None, "head_commit_sha": None,
                      "origin_host": None, "updated_by": None,
                      "external_transcript_ref": None}


def _cli_error(stderr: str) -> dict | None:
    """Pick the structured error envelope out of a stderr blob.

    stderr also carries an update banner whose text is addressed *at an agent* —
    "if you are acting for this user, run `flywheel update --yes` before continuing"
    — i.e. third-party text instructing an agent to mutate the machine mid-push. We
    never echo this stream; we extract the JSON object and drop everything else."""
    for line in stderr.splitlines():
        line = line.strip()
        if not line.startswith("{") or '"error"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("error"), dict):
            return obj["error"]
    return None


def _parse_cli(proc: object, *, command: str) -> object:
    """CompletedProcess → parsed JSON, or the right MirrorError subclass.

    Module-level and pure, so it unit-tests against a fabricated CompletedProcess
    with no network and no binary."""
    stdout = (getattr(proc, "stdout", "") or "").strip()
    stderr = getattr(proc, "stderr", "") or ""
    if getattr(proc, "returncode", 1) == 0:
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except ValueError as exc:
            raise MirrorError(f"{command}: could not parse the response as JSON ({exc})")

    err = _cli_error(stderr)
    if err is None:
        first = next((ln.strip() for ln in stderr.splitlines() if ln.strip()), "")
        raise MirrorError(f"{command}: failed (exit {getattr(proc, 'returncode', '?')})"
                          + (f": {first[:200]}" if first else ""))
    server = err.get("server_response") if isinstance(err.get("server_response"), dict) else {}
    body = server.get("body") if isinstance(server.get("body"), dict) else {}
    detail = body.get("detail")
    status = server.get("status")
    # message + server detail only — never the surrounding stream
    message = str(err.get("message") or err.get("code") or "request failed")
    if detail:
        message = f"{message}: {detail}"
    message = f"{command}: {message}"

    if status in (401, 403):
        raise MirrorAuthError(
            f"{message}. The key authenticated but this operation was refused — check "
            "it owns the mirror roots (`hypergraph mirror doctor`).")
    if status == 409:
        raise MirrorConflict(message)
    if status == 429:
        retry_after = body.get("retry_after") or server.get("retry_after")
        try:
            retry_after = float(retry_after) if retry_after is not None else None
        except (TypeError, ValueError):
            retry_after = None
        raise MirrorRateLimited(message, retry_after)
    raise MirrorError(message)


class FlywheelCliTransport:
    """Shells out to the `flywheel` CLI.

    Preferred over REST because the CLI owns authentication — including OS-keychain
    keys, which an in-process HTTP client cannot read at all — resolves the `/v1`
    path segment absent from the configured base URL, and handles the undocumented
    idempotency key. Keeps this file stdlib-only."""

    name = "cli"

    def __init__(self, run_dir: Path, binary: str = MIRROR_CLI_BINARY,
                 env_profile: str | None = None):
        self.binary = binary
        self.env_profile = env_profile
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._payload_seq = 0

    @staticmethod
    def available(binary: str = MIRROR_CLI_BINARY) -> bool:
        return shutil.which(binary) is not None

    def version(self) -> str:
        """Logged for the record, never acted on."""
        try:
            proc = subprocess.run([self.binary, "--version"], capture_output=True,
                                  text=True, timeout=30)
            return (proc.stdout or proc.stderr or "").strip().splitlines()[0][:60]
        except (OSError, subprocess.SubprocessError, IndexError):
            return "unknown"

    def _run(self, command: str, *, payload: dict | None = None,
             extra: list[str] | None = None, **flags) -> object:
        argv = [self.binary, command, "--format=json"]
        if self.env_profile:
            argv += [f"--env={self.env_profile}"]
        for key, value in flags.items():
            if value is None:
                continue
            argv += [f"--{key}={value}"]
        if payload is not None:
            # Always a file, never inline: node bodies are multi-KB, argv limits are
            # platform-dependent, and a leftover payload is free forensics on a crash.
            self._payload_seq += 1
            path = self.run_dir / f"payload-{self._payload_seq:05d}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False))
            argv += [f"--payload_json=@{path}"]
        argv += extra or []
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        except FileNotFoundError:
            raise MirrorUnavailable(
                f"`{self.binary}` is not on PATH. Install it (npm i -g "
                "@paradigma-inc/flywheel) or run with --transport rest, which needs "
                "FLYWHEEL_BASE_URL and FLYWHEEL_API_KEY in the environment.")
        except subprocess.TimeoutExpired:
            raise MirrorError(f"{command}: timed out after 600s")
        return _parse_cli(proc, command=command)

    # --- the seven operations ------------------------------------------------
    def auth_status(self) -> dict:
        raw = self._run("auth:status")
        return raw if isinstance(raw, dict) else {}

    def get_node(self, node_id: str) -> MirrorNode:
        raw = self._run("nodes:get", node_id=node_id, projection="core")
        return MirrorNode.from_raw(raw, context=f"nodes:get {node_id}")

    def children(self, node_id: str):
        """Yield every direct child, paging to exhaustion.

        The cursor loop is not optional: a record root with more than one page of
        children silently misses an existing legend node without it, and then
        creates a second one on every push (backend/mirror.md)."""
        after = None
        seen = 0
        while True:
            raw = self._run("nodes:children", node_id=node_id, first=500,
                            projection="core", after=after)
            if not isinstance(raw, dict):
                raise MirrorError(f"nodes:children {node_id}: unexpected response shape")
            edges = raw.get("edges") or []
            for edge in edges:
                node = edge.get("node") if isinstance(edge, dict) else None
                if isinstance(node, dict):
                    seen += 1
                    yield MirrorNode.from_raw(node, context=f"nodes:children {node_id}",
                                              need_revision=False)
            page = raw.get("page_info") if isinstance(raw.get("page_info"), dict) else {}
            if MirrorNode._bool(page.get("has_next_page")) is not True:
                return
            after = page.get("end_cursor")
            if not after:
                return

    def commit_new(self, *, parent_ids: list[str], title: str, content: str,
                   summary: str = "", repo_context: dict | None = None,
                   temp_id: str | None = None) -> MirrorNode:
        payload = {
            "local_temp_node_id": temp_id or f"hypergraph-{uuid.uuid4()}",
            "parent_ids": [p for p in parent_ids if p],
            "staged_payload": {
                "title": title, "content": content, "summary": summary,
                "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT),
            },
        }
        raw = self._run("nodes:commit-new", payload=payload)
        return MirrorNode.from_raw(raw, context="nodes:commit-new", need_revision=False)

    def commit(self, *, node_id: str, base_revision: int, title: str, content: str,
               summary: str = "", repo_context: dict | None = None) -> MirrorNode:
        """acquire → commit → release, with the release in a `finally`.

        The whole lease dance lives here so 409 semantics exist in exactly one
        place."""
        session = f"hypergraph-{uuid.uuid4()}"
        self._run("nodes:stage:lease:acquire", node_id=node_id,
                  stage_session_id=session, base_committed_revision=base_revision)
        try:
            raw = self._run("nodes:commit", node_id=node_id, payload={
                "stage_session_id": session,
                "base_committed_revision": base_revision,
                "staged_payload": {
                    "title": title, "content": content, "summary": summary,
                    "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT),
                },
            })
        finally:
            try:
                self._run("nodes:stage:lease:release", node_id=node_id,
                          stage_session_id=session)
            except MirrorError:
                pass  # the commit's outcome is what matters; leases expire on their own
        return MirrorNode.from_raw(raw, context=f"nodes:commit {node_id}",
                                   need_revision=False)

    def export_subgraph(self, node_ids: list[str], out: Path, *,
                        include_descendants: bool = True, max_nodes: int = 5000) -> Path:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        self._run("export:subgraph", node_ids=",".join(node_ids),
                  include_descendants="true" if include_descendants else "false",
                  max_nodes=max_nodes, extra=[f"--out={out}"])
        if not out.exists():
            raise MirrorError(f"export:subgraph wrote no file at {out}")
        return out

    def delete_node(self, node_id: str, *, mode: str = "detach_shared") -> None:
        self._run("nodes:delete", node_id=node_id, delete_mode=mode, extra=["--yes"])

    # --- op 10: tags -----------------------------------------------------------
    def graph_tags(self, root_node_id: str) -> tuple[list[dict], int]:
        """The vocabulary on one graph root, plus that root's current revision.

        There is **no `tags:list`**. The vocabulary comes back on any node under
        `--projection full`, as `graph_tags`. An absent key **raises**: reading it as
        "this graph has no tags" would make the next push re-create all 22 of them,
        which is the duplicate-definition failure this whole feature guards against."""
        raw = self._run("nodes:get", node_id=root_node_id, projection="full")
        return _parse_graph_tags(raw, context=f"nodes:get {root_node_id} (full)")

    def create_tag(self, *, root_node_id: str, name: str, expected_revision: int,
                   bg_color: str, text_color: str, one_only: bool = False,
                   track_history: bool = False) -> dict:
        """One `tags:create`. **Never blind-retried** — creates cannot be de-duplicated.

        `expected_revision` must be re-read before every call: each create bumps the
        root revision, so a revision computed once and reused across a 22-tag loop is
        stale after the first.

        **The return value is not the tag's identity.** Measured against the live host:
        this endpoint returns the updated *graph root node* — `content`, `artifacts`,
        `graph_projection` — with no `tag_id` anywhere in it. The caller re-reads the
        root and resolves the new tag **by name**, which is the same rule as never
        assuming a revision, and is also exactly the recovery path a crashed run
        needs."""
        # argv trap: `_run` renders `--{k}={v}` for anything non-None, so a Python
        # False would become the *truthy string* `--one_only=False`. These are
        # store-true flags — omit them, or pass them bare.
        extra = (["--one_only"] if one_only else []) + \
                (["--track_history"] if track_history else [])
        raw = self._run("tags:create", root_node_id=root_node_id, name=name,
                        expected_revision=int(expected_revision), bg_color=bg_color,
                        text_color=text_color, extra=extra)
        return raw if isinstance(raw, dict) else {}

    def assign_tags(self, *, node_id: str, tag_ids: list[str],
                    expected_revision: int) -> None:
        """Atomic replace of a node's whole tag set. Bumps the *node* revision."""
        self._run("tags:assign", node_id=node_id, tag_ids=",".join(tag_ids),
                  expected_revision=int(expected_revision))


def _parse_graph_tags(raw: object, *, context: str) -> tuple[list[dict], int]:
    """A full-projection node response → (its graph's tag definitions, root revision)."""
    if isinstance(raw, dict) and isinstance(raw.get("node"), dict):
        raw = raw["node"]
    if not isinstance(raw, dict):
        raise MirrorError(f"{context}: expected a node object, got {type(raw).__name__}")
    if "graph_tags" not in raw:
        raise MirrorError(
            f"{context}: the response carries no `graph_tags` key (keys: "
            f"{sorted(raw)[:10]}). Refusing to read that as \"this graph has no "
            "tags\" — that would re-create the whole vocabulary on the next push, "
            "and a duplicate tag definition cannot be cleanly merged.")
    tags = [t for t in (raw.get("graph_tags") or []) if isinstance(t, dict)]
    revision = raw.get("revision", raw.get("committed_revision"))
    if revision is None:
        raise MirrorError(
            f"{context}: no revision on the root. `tags:create` locks against it and "
            "refusing to assume 0 is the same rule as everywhere else here.")
    return tags, int(revision)


def tag_by_name(tags: list[dict], name: str) -> dict | None:
    """A tag definition out of a root's `graph_tags`, by name.

    Name is the only lookup key here, deliberately. It is what makes a create
    idempotent by inspection — a crashed run finds the tag rather than repeating it —
    and it is what identifies a tag whose id the create response never returned."""
    for tag in tags:
        if isinstance(tag, dict) and str(tag.get("name") or "") == name:
            return tag
    return None


class FlywheelRestTransport(FlywheelCliTransport):
    """Explicit fallback for machines without the npm binary.

    Same seven operations over `urllib`. It cannot read OS-keychain keys, so it
    requires FLYWHEEL_BASE_URL and FLYWHEEL_API_KEY in the environment."""

    name = "rest"

    def __init__(self, run_dir: Path, base_url: str, api_key: str):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._payload_seq = 0

    @staticmethod
    def from_env(run_dir: Path) -> "FlywheelRestTransport":
        import os  # deferred: nothing off the mirror path reads the environment
        base = os.environ.get("FLYWHEEL_BASE_URL", "").strip()
        key = os.environ.get("FLYWHEEL_API_KEY", "").strip()
        if not base or not key:
            raise MirrorUnavailable(
                "--transport rest needs FLYWHEEL_BASE_URL and FLYWHEEL_API_KEY in the "
                "environment (a key held only in the OS keychain is unreadable here — "
                "use the CLI transport for that).")
        return FlywheelRestTransport(run_dir, base, key)

    def version(self) -> str:
        return f"rest {self.base_url}"

    def _request(self, method: str, path: str, *, body: dict | None = None,
                 query: dict | None = None) -> object:
        import urllib.error  # deferred: keeps the non-mirror path network-module-free
        import urllib.parse
        import urllib.request

        # the configured base URL ends at /api; the runtime lives under /v1
        url = f"{self.base_url}/v1{path}"
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4()),
        })
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                raw = resp.read().decode() or "{}"
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                payload = json.loads(exc.read().decode())
                detail = str(payload.get("detail") or "")
            except Exception:
                pass
            message = f"{method} {path}: HTTP {exc.code}" + (f": {detail}" if detail else "")
            if exc.code in (401, 403):
                raise MirrorAuthError(message)
            if exc.code == 409:
                raise MirrorConflict(message)
            if exc.code == 429:
                retry = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    retry = float(retry) if retry else None
                except ValueError:
                    retry = None
                raise MirrorRateLimited(message, retry)
            raise MirrorError(message)
        except urllib.error.URLError as exc:
            raise MirrorUnavailable(f"{method} {path}: {exc.reason}")

    def auth_status(self) -> dict:
        raw = self._request("GET", "/auth/status")
        return raw if isinstance(raw, dict) else {}

    def get_node(self, node_id: str) -> MirrorNode:
        raw = self._request("GET", f"/nodes/{node_id}", query={"projection": "core"})
        return MirrorNode.from_raw(raw, context=f"GET /nodes/{node_id}")

    def children(self, node_id: str):
        after = None
        while True:
            raw = self._request("GET", f"/nodes/{node_id}/children",
                                query={"first": 500, "projection": "core", "after": after})
            if not isinstance(raw, dict):
                raise MirrorError(f"GET /nodes/{node_id}/children: unexpected shape")
            for edge in raw.get("edges") or []:
                node = edge.get("node") if isinstance(edge, dict) else None
                if isinstance(node, dict):
                    yield MirrorNode.from_raw(node, context="children", need_revision=False)
            page = raw.get("page_info") if isinstance(raw.get("page_info"), dict) else {}
            if MirrorNode._bool(page.get("has_next_page")) is not True:
                return
            after = page.get("end_cursor")
            if not after:
                return

    def commit_new(self, *, parent_ids, title, content, summary="",
                   repo_context=None, temp_id=None) -> MirrorNode:
        raw = self._request("POST", "/nodes/commit-new", body={
            "local_temp_node_id": temp_id or f"hypergraph-{uuid.uuid4()}",
            "parent_ids": [p for p in parent_ids if p],
            "staged_payload": {"title": title, "content": content, "summary": summary,
                               "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT)},
        })
        return MirrorNode.from_raw(raw, context="POST /nodes/commit-new",
                                   need_revision=False)

    def commit(self, *, node_id, base_revision, title, content, summary="",
               repo_context=None) -> MirrorNode:
        session = f"hypergraph-{uuid.uuid4()}"
        self._request("POST", f"/nodes/{node_id}/stage/lease/acquire", body={
            "stage_session_id": session, "base_committed_revision": base_revision})
        try:
            raw = self._request("POST", f"/nodes/{node_id}/commit", body={
                "stage_session_id": session, "base_committed_revision": base_revision,
                "staged_payload": {"title": title, "content": content,
                                   "summary": summary,
                                   "repo_context": dict(repo_context or EMPTY_REPO_CONTEXT)}})
        finally:
            try:
                self._request("POST", f"/nodes/{node_id}/stage/lease/release",
                              body={"stage_session_id": session})
            except MirrorError:
                pass
        return MirrorNode.from_raw(raw, context=f"POST /nodes/{node_id}/commit",
                                   need_revision=False)

    def export_subgraph(self, node_ids, out, *, include_descendants=True,
                        max_nodes=5000) -> Path:
        raw = self._request("POST", "/export", body={
            "node_ids": list(node_ids), "include_descendants": include_descendants,
            "max_nodes": max_nodes})
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
        return out

    def delete_node(self, node_id: str, *, mode: str = "detach_shared") -> None:
        self._request("DELETE", f"/nodes/{node_id}", query={"delete_mode": mode})

    # --- op 10: tags -----------------------------------------------------------
    def graph_tags(self, root_node_id: str) -> tuple[list[dict], int]:
        raw = self._request("GET", f"/nodes/{root_node_id}",
                            query={"projection": "full"})
        return _parse_graph_tags(raw, context=f"GET /nodes/{root_node_id} (full)")

    def create_tag(self, *, root_node_id: str, name: str, expected_revision: int,
                   bg_color: str, text_color: str, one_only: bool = False,
                   track_history: bool = False) -> dict:
        # As on the CLI transport: the response is not trusted for identity. The
        # caller re-reads the root and resolves the new tag by name.
        raw = self._request("POST", f"/nodes/{root_node_id}/tags", body={
            "name": name, "expected_revision": int(expected_revision),
            "bg_color": bg_color, "text_color": text_color,
            "one_only": bool(one_only), "track_history": bool(track_history)})
        return raw if isinstance(raw, dict) else {}

    def assign_tags(self, *, node_id: str, tag_ids: list[str],
                    expected_revision: int) -> None:
        self._request("PUT", f"/nodes/{node_id}/tags", body={
            "tag_ids": list(tag_ids), "expected_revision": int(expected_revision)})


def make_transport(config: dict, *, run_dir: Path, prefer: str = "auto"):
    """The single injection seam. Tests monkeypatch this, nothing else."""
    profile = str((config.get("mirror_profile") or "")) or None
    if prefer == "rest":
        return FlywheelRestTransport.from_env(run_dir)
    if prefer == "cli":
        if not FlywheelCliTransport.available():
            raise MirrorUnavailable(
                f"`{MIRROR_CLI_BINARY}` is not on PATH (npm i -g @paradigma-inc/flywheel).")
        return FlywheelCliTransport(run_dir, env_profile=profile)
    if FlywheelCliTransport.available():
        return FlywheelCliTransport(run_dir, env_profile=profile)
    return FlywheelRestTransport.from_env(run_dir)


# ---------------------------------------------------------------- crash journal

class PushJournal:
    """Local idempotency for mirror writes.

    Duplicate mirror nodes are the only unrecoverable failure in this feature
    (backend/local-adapter.md: duplicates cannot be cleanly merged), and the CLI
    transport cannot inject an Idempotency-Key header — so idempotency is owned
    here. An *intent* is written and fsynced **before** each request, a `done`
    after it. On the next run, any intent without a `done` is resolved **by
    looking**: page the intended parent's children and match title + body sha256.
    Blind retry is never an option."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, entry: dict) -> None:
        import os  # deferred: only the mirror path fsyncs
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                out.append(entry)
        return out

    def intent(self, op: dict, *, parent_id: str | None) -> str:
        intent_id = str(uuid.uuid4())
        self._append({"t": "intent", "id": intent_id, "op": op["op"],
                      "slug": op["slug"], "graph": op["graph"], "title": op["title"],
                      "content_sha256": op["content_sha256"], "parent_id": parent_id,
                      "flywheel_node_id": op.get("flywheel_node_id"),
                      "at": utc_now()})
        return intent_id

    def done(self, intent_id: str, *, slug: str, node: MirrorNode,
             content_sha256: str) -> None:
        self._append({"t": "done", "id": intent_id, "slug": slug,
                      "flywheel": {"node_id": node.node_id, "slug_name": node.slug,
                                   "revision": node.revision},
                      "content_sha256": content_sha256, "pushed_at": utc_now()})

    def abandon(self, intent_id: str, reason: str) -> None:
        """The intended write demonstrably never landed; it is safe to replan."""
        self._append({"t": "abandoned", "id": intent_id, "reason": reason,
                      "at": utc_now()})

    def pending(self) -> list[dict]:
        settled = {e["id"] for e in self.entries()
                   if e.get("t") in ("done", "abandoned") and e.get("id")}
        return [e for e in self.entries()
                if e.get("t") == "intent" and e.get("id") not in settled]

    def results(self) -> list[dict]:
        """Exactly the shape `apply_push_results` already eats."""
        return [{"slug": e["slug"], "flywheel": e["flywheel"],
                 "content_sha256": e.get("content_sha256"),
                 "pushed_at": e.get("pushed_at")}
                for e in self.entries() if e.get("t") == "done" and e.get("slug")]

    def reconcile_pending(self, transport, *, out=print) -> int:
        """Resolve every intent-without-done by looking, never by retrying."""
        pending = self.pending()
        if not pending:
            return 0
        out(f"push: {len(pending)} unfinished write(s) from a previous run — resolving "
            "by inspection")
        resolved = 0
        for entry in pending:
            slug = entry.get("slug")
            if entry.get("op") == "update":
                node_id = entry.get("flywheel_node_id")
                if not node_id:
                    self.abandon(entry["id"], "update intent carries no node id")
                    continue
                live = transport.get_node(node_id)
                if live.sha256 == entry.get("content_sha256"):
                    self.done(entry["id"], slug=slug, node=live,
                              content_sha256=live.sha256)
                    resolved += 1
                    out(f"  {slug}: update had landed — adopting revision {live.revision}")
                else:
                    self.abandon(entry["id"], "update did not land")
                    out(f"  {slug}: update never landed — will be replanned")
                continue
            parent_id = entry.get("parent_id")
            if not parent_id:
                self.abandon(entry["id"], "create intent carries no parent to search")
                continue
            match = None
            for child in transport.children(parent_id):
                if child.title == entry.get("title") \
                        and child.sha256 == entry.get("content_sha256"):
                    match = child
                    break
            if match is not None:
                # the create landed and we crashed before recording it
                live = transport.get_node(match.node_id)
                self.done(entry["id"], slug=slug, node=live, content_sha256=live.sha256)
                resolved += 1
                out(f"  {slug}: create had landed as {live.node_id} — adopted, not repeated")
            else:
                self.abandon(entry["id"], "create never landed")
                out(f"  {slug}: create never landed — will be replanned")
        return resolved


# ----------------------------------------------------------------------- pacing

class Pacer:
    """A minimum interval between writes, not a token bucket.

    A burst bucket spends itself instantly and then eats 429s; there is exactly one
    writer by protocol, so smoothing strictly dominates bursting. 100/min against
    the host's 120/min ceiling leaves headroom for the legend and lineage writes."""

    def __init__(self, per_minute: float = 100.0, *, sleep=None, clock=None):
        import time  # deferred: nothing off the mirror path needs a clock
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self.interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._last: float | None = None

    def wait(self) -> None:
        if self.interval <= 0:
            return
        now = self.clock()
        if self._last is not None:
            gap = self.interval - (now - self._last)
            if gap > 0:
                self.sleep(gap)
        self._last = self.clock()

    def slow_down(self, factor: float = 2.0) -> None:
        """The server disagrees with our model of the budget — believe the server."""
        self.interval = max(self.interval, 0.05) * factor

    def backoff(self, attempt: int, retry_after: float | None) -> float:
        delay = retry_after if retry_after is not None else min(2.0 ** attempt, 60.0)
        delay = min(float(delay), 120.0)
        # deterministic jitter: no Math.random-style nondeterminism in tests
        self.sleep(delay)
        return delay


MIRROR_MAX_ATTEMPTS = 4  # the CLI already retries 3x internally → 12 real requests


def mirror_call(fn, *, pacer: Pacer, what: str, retry_conflict=None, out=print):
    """Run one mirror write with pacing, 429 backoff, and no blind 409 retry."""
    last: Exception | None = None
    for attempt in range(MIRROR_MAX_ATTEMPTS):
        pacer.wait()
        try:
            return fn()
        except MirrorRateLimited as exc:
            last = exc
            pacer.slow_down()
            if attempt == MIRROR_MAX_ATTEMPTS - 1:
                break
            delay = pacer.backoff(attempt, exc.retry_after)
            out(f"  rate limited on {what}; slowing down and retrying in {delay:.0f}s")
        except MirrorConflict as exc:
            # One structured re-read, then abort. Under I3 there is one writer.
            if retry_conflict is not None:
                resolved = retry_conflict(exc)
                if resolved is not None:
                    return resolved
            raise MirrorConflict(
                f"{what}: {exc}. The mirror moved under us, which means a second "
                "writer touched it — SPEC I3 says reconcile is the only writer. "
                "Investigate before re-pushing; local files stay canonical.")
    raise last if last else MirrorError(f"{what}: exhausted retries")

# --------------------------------------------------------------- push executor

def mirror_configured(config: dict) -> bool:
    """A project that never asked for a mirror never enters this path.

    This is what lets the reconcile skill say `hypergraph push` unconditionally
    instead of making the agent evaluate a config test."""
    return bool(config.get("mirror"))


def mirror_root_ids(config: dict) -> dict:
    """{kind: mirror root node_id}, with the archive assertion made mechanical.

    Falls back to the configured record/state roots, which is right for a re-homed
    project that mirrors to the graph it was imported from (this repo has no
    `mirror_roots:` and must still push)."""
    roots: dict[str, str] = {}
    configured = config.get("mirror_roots") or {}
    for kind in GRAPH_KINDS:
        node_id = ""
        entry = configured.get(kind) if isinstance(configured, dict) else None
        if isinstance(entry, dict):
            node_id = str(entry.get("node_id") or "")
        elif isinstance(entry, str):
            node_id = entry
        if not node_id:
            fallback = config.get(f"{kind}_root") or {}
            if isinstance(fallback, dict):
                node_id = str(fallback.get("node_id") or "")
        if not node_id:
            raise MirrorError(
                f"no mirror root for the {kind} graph — set `mirror_roots.{kind}.node_id` "
                f"in the config (mint them with `hypergraph mirror roots --mint`)")
        roots[kind] = node_id

    archive_ids = {str(r.get("node_id")) for r in (config.get("archive") or {}).get("roots", [])
                   if isinstance(r, dict) and r.get("node_id")}
    clash = archive_ids & set(roots.values())
    if clash:
        raise MirrorError(
            f"mirror root {sorted(clash)[0]} is also an `archive:` root. The archive is "
            "frozen and this project never writes to it; splicing it in makes "
            "`push --verify` pass while the mirror holds almost none of the graph "
            "(backend/mirror.md).")
    return roots


def _repo_context_for(node: LocalNode) -> dict:
    """`## Repo` lines → the host's repo_context. All six keys, null where unknown."""
    ctx = dict(EMPTY_REPO_CONTEXT)
    for line in node.content.splitlines():
        m = re.match(r"^-\s*(repo|branch|commit):\s*(.+?)\s*$", line)
        if not m:
            continue
        key = {"repo": "repo_url", "branch": "branch_name", "commit": "head_commit_sha"}[m.group(1)]
        value = m.group(2).strip()
        if value and value.lower() not in ("none", "n/a", "-"):
            ctx[key] = value
    return ctx


def execute_push(graph_dir: Path, config: dict, transport, *, journal: PushJournal,
                 pacer: Pacer, batch: int = 20, limit: int | None = None,
                 dry_run: bool = False, do_legend: bool = True, do_tags: bool = True,
                 out=print) -> dict:
    """Plan → execute → fold, resumable at every point.

    `push_plan()` is a pure diff against each file's `flywheel:` frontmatter, so it
    *is* the idempotent resume primitive: everything already stamped is invisible to
    the next plan. Nothing here reimplements it."""
    roots = mirror_root_ids(config)

    # 1. resolve anything a previous run left ambiguous, before planning new work
    if journal.reconcile_pending(transport, out=out):
        applied = apply_push_results(graph_dir, journal.results())
        out(f"push: folded {applied} recovered write(s) into the node files")

    # 2. plan *after* the fold — the fold changed what the plan is a diff against
    plan = push_plan(graph_dir, do_tags=do_tags)
    if plan["violations"]:
        for violation in plan["violations"]:
            out(f"VIOLATION {violation}")
        raise MirrorError(
            "refusing to push: the record graph is append-only and the plan carries "
            f"{len(plan['violations'])} body change(s) to already-pushed record "
            "node(s). Fix the local edit — a correction is a new child node, not an "
            "edit (SPEC: record nodes are immutable).")

    # Tag ops are executed by `push_tags` after the node loop and the result fold, so
    # a node created in this same run already carries its mirror id by then.
    all_ops = plan["ops"]
    ops = [o for o in all_ops if o["op"] != "tags"]
    tag_ops = [o for o in all_ops if o["op"] == "tags"]
    if limit is not None:
        ops = ops[:limit]
    creates = sum(1 for o in ops if o["op"] == "create")
    out(f"push: {creates} create(s), {len(ops) - creates} update(s)"
        + (f", {len(tag_ops)} tag assignment(s)" if tag_ops else ""))
    if not ops and not tag_ops:
        out("push: mirror already matches the node files — nothing to do")
        return {"created": 0, "updated": 0, "ops": 0, "tagged": 0}

    if dry_run:
        for op in all_ops:
            out(f"  would {op['op']:6} {op['graph']:6} {op['slug']}"
                + (f"   [{', '.join(op['tags'])}]" if op["op"] == "tags" else ""))
        return {"created": creates, "updated": len(ops) - creates, "ops": len(ops),
                "tagged": len(tag_ops), "dry_run": True}

    nodes = {}
    for kind in GRAPH_KINDS:
        nodes.update(load_local_nodes(graph_dir, kind, missing_ok=True))

    minted: dict[str, str] = {}   # local slug → mirror node_id, for null-parent substitution
    pending_results: list[dict] = []
    created = updated = 0

    def settled(node: MirrorNode, what: str) -> MirrorNode:
        """A write's response may omit the revision; read the live one rather than
        stamp a guess. `revision: 0` is real, so a default would poison every later
        update with a permanent conflict."""
        if node.revision is None:
            node = transport.get_node(node.node_id)
        if node.revision is None:
            raise MirrorError(
                f"{what}: the mirror never reported a revision for {node.node_id} — "
                "refusing to stamp a guess into the node file")
        return node

    def flush() -> None:
        nonlocal pending_results
        if not pending_results:
            return
        apply_push_results(graph_dir, pending_results, nodes=nodes)
        out(f"  recorded {len(pending_results)} result(s) into the node files")
        pending_results = []

    for op in ops:
        slug = op["slug"]
        local = nodes.get(slug)
        repo_ctx = _repo_context_for(local) if local is not None else None

        if op["op"] == "create":
            parent_ids = []
            for parent_slug, parent_id in zip(op["parent_slugs"], op["parent_flywheel_ids"]):
                if parent_id:
                    parent_ids.append(str(parent_id))
                    continue
                # push_plan orders parents first, so the minted id must already exist
                substituted = minted.get(parent_slug)
                if not substituted:
                    raise MirrorError(
                        f"{slug}: parent `{parent_slug}` has no mirror id yet. The plan "
                        "is ordered parents-first, so this cannot happen — refusing to "
                        "guess a parent and silently reshape the mirror.")
                parent_ids.append(substituted)
            if not parent_ids:
                parent_ids = [roots[op["graph"]]]   # a local root hangs off the mirror root

            intent = journal.intent(op, parent_id=parent_ids[0])
            node = mirror_call(
                lambda: transport.commit_new(
                    parent_ids=parent_ids, title=op["title"], content=op["content"],
                    summary=op["summary"], repo_context=repo_ctx),
                pacer=pacer, what=f"create {slug}", out=out)
            node = settled(node, f"create {slug}")
            journal.done(intent, slug=slug, node=node, content_sha256=op["content_sha256"])
            minted[slug] = node.node_id
            created += 1
        else:
            node_id = str(op["flywheel_node_id"])
            base = op.get("base_revision")
            if base is None:
                # imported graphs carry no revision — read the live one, never assume 0
                base = transport.get_node(node_id).revision
            intent = journal.intent(op, parent_id=None)

            def _resolved(_exc, _op=op, _node_id=node_id):
                live = transport.get_node(_node_id)
                return live if live.sha256 == _op["content_sha256"] else None

            node = mirror_call(
                lambda: transport.commit(
                    node_id=node_id, base_revision=int(base), title=op["title"],
                    content=op["content"], summary=op["summary"], repo_context=repo_ctx),
                pacer=pacer, what=f"update {slug}", retry_conflict=_resolved, out=out)
            node = settled(node, f"update {slug}")
            journal.done(intent, slug=slug, node=node, content_sha256=op["content_sha256"])
            updated += 1

        pending_results.append({
            "slug": slug,
            "flywheel": {"node_id": node.node_id, "slug_name": node.slug,
                         "revision": node.revision},
            "content_sha256": op["content_sha256"]})
        if len(pending_results) >= batch:
            flush()
    flush()

    tagged = 0
    if tag_ops:
        tagged = push_tags(graph_dir, config, roots, transport, pacer=pacer, out=out)
    if do_legend:
        push_legend(graph_dir, roots["record"], transport, pacer=pacer, out=out)
    return {"created": created, "updated": updated, "ops": len(ops), "tagged": tagged}


def push_legend(graph_dir: Path, record_root_id: str, transport, *, pacer: Pacer,
                out=print) -> str:
    """Create or update the mirror-only slug legend under the mirror record root.

    Two traps, both closed here: children are paged to exhaustion (a root with more
    than one page silently misses the legend and creates a second one on every push,
    which is a duplicate-node generator), and the body hash decides whether the
    write happens at all."""
    body = legend_content(graph_dir)
    existing = None
    for child in transport.children(record_root_id):
        if child.title == LEGEND_TITLE:
            existing = child
            break
    if existing is None:
        mirror_call(lambda: transport.commit_new(
            parent_ids=[record_root_id], title=LEGEND_TITLE, content=body,
            summary="Mirror-only: maps local slugs to the slugs this mirror minted."),
            pacer=pacer, what="create legend", out=out)
        out("  legend: created")
        return "created"
    live = transport.get_node(existing.node_id)
    if live.sha256 == body_sha256(body):
        out("  legend: unchanged")
        return "unchanged"
    mirror_call(lambda: transport.commit(
        node_id=live.node_id, base_revision=live.revision, title=LEGEND_TITLE,
        content=body,
        summary="Mirror-only: maps local slugs to the slugs this mirror minted."),
        pacer=pacer, what="update legend", out=out)
    out("  legend: updated")
    return "updated"


# Some backends constrain *where* a tag may live, not merely that it exists. Flywheel
# requires a `cluster:*` tag to cover a **connected** set of nodes, and checks it on
# every assignment — so a tag whose final set is perfectly connected is still rejected
# part-way through, because an atomic per-node replace builds that set one node at a
# time. Assignment *order* is therefore part of the contract rather than a detail
# [rec: the neural-whoop field run].
#
# The prefix is a host rule, so it is named here rather than inferred, and a
# `connected:` key in tags.yml overrides it either way for a backend that decides
# differently.
CONNECTED_TAG_PREFIXES = ("cluster:",)


def connectivity_constrained(name: str, entry: dict | None = None) -> bool:
    if entry is not None and entry.get("connected") is not None:
        return bool(entry["connected"])
    return any(name.startswith(prefix) for prefix in CONNECTED_TAG_PREFIXES)


def assignment_order(pending: list, adjacency: dict, constrained: set,
                     already: dict | None = None) -> tuple[list, list]:
    """Order assignments so no constrained tag is ever momentarily split in two.

    → (ordered, blocked). A node is *safe* when, for every constrained tag it carries,
    that tag's already-assigned set is either empty or adjacent to this node. Growing
    each set outward from a single seed is a spanning-tree traversal, so a set that is
    connected at the end can always be built connected; the only real work is
    respecting several tags at once.

    `already` seeds the state from what the mirror currently holds, which is what makes
    this correct after a partial run rather than only on a clean graph."""
    assigned: dict[str, set] = {name: set(slugs) for name, slugs in (already or {}).items()}
    remaining = list(pending)
    ordered: list = []
    while remaining:
        progressed = False
        for i, node in enumerate(remaining):
            tags = [t for t in node.tags if t in constrained]
            if all(not assigned.get(t) or (adjacency.get(node.slug, set()) & assigned[t])
                   for t in tags):
                for t in tags:
                    assigned.setdefault(t, set()).add(node.slug)
                ordered.append(remaining.pop(i))
                progressed = True
                break
        if not progressed:
            # Never silently reorder past it: the host would reject the write anyway,
            # and a caller that cannot see which tag is unsatisfiable cannot fix it.
            return ordered, remaining
    return ordered, []


def reconcile_tag_vocabulary(kind: str, root_id: str, wanted: list[dict], transport, *,
                             pacer: Pacer, vocab: dict, tags_path: Path,
                             out=print) -> tuple[dict[str, str], list[str]]:
    """Make the mirror root's vocabulary hold every wanted name. → ({name: tag_id}, notes)

    **Resolve by name first, always.** A duplicate tag definition is the one
    unrecoverable failure here, exactly as a duplicate node is: `tags:delete` un-tags
    every node that used the tag, so there is no clean retraction. Every guard in this
    function — the committed `tags.yml`, the name lookup, the re-read below — exists
    for that one reason.

    Idempotent by inspection, with no journal. That is the whole reason to resolve by
    name: a crashed run leaves a tag that the next run *finds* rather than repeats."""
    live, root_revision = transport.graph_tags(root_id)
    by_name = {str(t.get("name") or ""): t for t in live}
    notes: list[str] = []
    ids: dict[str, str] = {}

    for entry in wanted:
        name = str(entry["name"])
        found = by_name.get(name)
        if found is not None:
            ids[name] = str(found.get("tag_id") or "")
            # Reported, never repaired. `tags:update` would rewrite a definition
            # someone may have deliberately restyled on the host, and no invariant
            # reads a colour or a flag.
            for key in ("bg_color", "text_color"):
                mine, theirs = entry.get(key), found.get(key)
                if mine and theirs and str(mine).upper() != str(theirs).upper():
                    notes.append(f"{name}: {key} differs (local {mine}, mirror {theirs})")
            for key in ("one_only", "track_history"):
                mine, theirs = entry.get(key), found.get(key)
                if mine is not None and theirs is not None and bool(mine) != bool(theirs):
                    notes.append(f"{name}: {key} differs (local {bool(mine)}, "
                                 f"mirror {bool(theirs)})")
            continue
        mirror_call(
            lambda entry=entry, rev=root_revision: transport.create_tag(
                root_node_id=root_id, name=str(entry["name"]),
                expected_revision=int(rev),
                bg_color=str(entry.get("bg_color") or synth_tag(str(entry["name"]))["bg_color"]),
                text_color=str(entry.get("text_color") or synth_tag(str(entry["name"]))["text_color"]),
                one_only=bool(entry.get("one_only")),
                track_history=bool(entry.get("track_history"))),
            pacer=pacer, what=f"create tag {name}", out=out)
        # **Never compute the next root revision, and never take the id from the
        # create's response.** Each create bumps the revision, and the live host
        # returns the updated *root node* here rather than the tag — so both facts
        # come from one authoritative re-read, resolved by name.
        live, root_revision = transport.graph_tags(root_id)
        by_name = {str(t.get("name") or ""): t for t in live}
        made = tag_by_name(live, name)
        if made is None or not made.get("tag_id"):
            raise MirrorError(
                f"create tag {name}: the tag is not on root {root_id} after the "
                "create, so the write did not land. Refusing to continue — the next "
                "step would assign an id that does not exist.")
        ids[name] = str(made["tag_id"])
        # Written after *each* create, not at the end: a crash between two creates
        # must leave the first one recorded, or the next run creates it twice.
        merge_tag_def(vocab, kind, {"name": name, "flywheel": {
            "tag_id": ids[name], "root_node_id": root_id, "pushed_at": utc_now()}})
        write_tag_vocab(tags_path, vocab)
        out(f"  tag: created `{name}` ({ids[name]})")
    return ids, notes


def live_tag_assignments(graph_dir: Path, root_id: str, transport,
                         nodes: dict) -> dict[str, set]:
    """{tag name: {local slug}} as the mirror currently holds it.

    Read through one subgraph export rather than per node: the assignment state is
    only needed when a connectivity-constrained tag exists, and then it is needed for
    the whole graph at once."""
    cache = Path(config_cache_dir(graph_dir))
    export = transport.export_subgraph([root_id], cache / "tag-state.json")
    data = json.loads(Path(export).read_text())
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    by_id = {str((n.meta.get("flywheel") or {}).get("node_id") or ""): slug
             for slug, n in nodes.items()}
    names = {t["tag_id"]: str(t.get("name") or "")
             for n in raw_nodes if isinstance(n, dict)
             for t in (n.get("graph_tags") or []) if isinstance(t, dict) and t.get("tag_id")}
    out: dict[str, set] = {}
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        slug = by_id.get(str(raw.get("node_id") or ""))
        if not slug:
            continue
        for tid in (raw.get("tag_ids") or []):
            name = names.get(str(tid))
            if name:
                out.setdefault(name, set()).add(slug)
    return out


def config_cache_dir(graph_dir: Path) -> Path:
    path = Path(graph_dir).parent / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def push_tags(graph_dir: Path, config: dict, roots: dict, transport, *, pacer: Pacer,
              out=print) -> int:
    """Create the vocabulary on the mirror roots, then assign it per node.

    Runs after the node loop and its result fold, so a node created in the same run
    already carries the `flywheel.node_id` an assignment needs."""
    tags_path = tags_file_for(config, graph_dir)
    vocab = load_tag_vocab(tags_path)
    assigned = 0

    for kind in GRAPH_KINDS:
        nodes = load_local_nodes(graph_dir, kind, missing_ok=True)
        used = sorted({name for node in nodes.values() for name in node.tags})
        declared = [dict(e) for e in tag_vocab_entries(vocab, kind)]
        known = {str(e["name"]) for e in declared}
        # An undeclared name in use still travels: the vocabulary is optional, and a
        # name with no declaration gets its colour from its own digest.
        wanted = declared + [{"name": n, **synth_tag(n)} for n in used if n not in known]
        pending = [node for node in nodes.values()
                   if node.tags or (node.meta.get("flywheel") or {}).get("tags_sha256")]
        if not wanted or not pending:
            continue

        ids, notes = reconcile_tag_vocabulary(
            kind, roots[kind], wanted, transport, pacer=pacer, vocab=vocab,
            tags_path=tags_path, out=out)
        for note in notes:
            out(f"  tag drift (reported, not repaired) {note}")

        by_name = {str(e["name"]): e for e in tag_vocab_entries(vocab, kind)}
        constrained = {n for n in used if connectivity_constrained(n, by_name.get(n))}
        if constrained:
            # One extra read, only when a constrained tag exists: what the mirror
            # already holds is the starting state, and without it a resumed run
            # re-derives an order that was valid from empty and is not valid from here.
            adjacency: dict[str, set] = {}
            for slug, node in nodes.items():
                for parent in node.parents:
                    if parent in nodes:
                        adjacency.setdefault(slug, set()).add(parent)
                        adjacency.setdefault(parent, set()).add(slug)
            already = live_tag_assignments(graph_dir, roots[kind], transport, nodes)
            pending, blocked = assignment_order(pending, adjacency, constrained, already)
            if blocked:
                stuck = sorted({t for node in blocked for t in node.tags if t in constrained})
                raise MirrorError(
                    f"cannot order {len(blocked)} assignment(s) so that "
                    f"{', '.join(stuck)} stay(s) connected at every step. This backend "
                    "requires such a tag to cover a connected set of nodes and checks it "
                    "on every write, so the set has to be grown outward from one node — "
                    "which is impossible if it is disconnected in this graph's topology. "
                    "Check whether those nodes are all present and parented as they were "
                    "on the source graph.")
            out(f"  tags: ordered {len(pending)} assignment(s) to keep "
                f"{len(constrained)} connected tag(s) whole at every step")

        results: list[dict] = []
        for node in pending:
            fw = node.meta.get("flywheel") or {}
            node_id = str(fw.get("node_id") or "")
            if not node_id:
                out(f"  tag: skipping `{node.slug}` — not on the mirror yet")
                continue
            want = tags_sha256(node.tags)
            if fw.get("tags_sha256") == want:
                continue
            tag_ids = [ids[name] for name in sorted(node.tags) if ids.get(name)]
            revision = fw.get("revision")
            if revision is None:
                revision = transport.get_node(node_id).revision

            def _reissue(_exc, _node_id=node_id, _tag_ids=tag_ids):
                """The one place the no-blind-retry rule inverts, on purpose.

                `tags:assign` is an **atomic replace**, so re-issuing it cannot
                duplicate anything — the worst case is writing the same set twice.
                A create has no such property and keeps the rule."""
                live = transport.get_node(_node_id)
                if live.revision is None:
                    return None
                transport.assign_tags(node_id=_node_id, tag_ids=_tag_ids,
                                      expected_revision=int(live.revision))
                return True

            mirror_call(
                lambda nid=node_id, tids=tag_ids, rev=revision: transport.assign_tags(
                    node_id=nid, tag_ids=tids, expected_revision=int(rev)),
                pacer=pacer, what=f"assign tags {node.slug}", retry_conflict=_reissue,
                out=out)
            # **The revision fold is not optional.** `tags:assign` bumps the node
            # revision, and `verify_mirror` treats revision skew as a violation — so
            # skipping this leaves one permanent false drift finding per tagged node.
            # Read it back; the mutating response schema is `{}`, so never assume +1.
            live = transport.get_node(node_id)
            if live.revision is None:
                raise MirrorError(
                    f"assign tags {node.slug}: the mirror reported no revision after "
                    "the assignment. Refusing to stamp a guess — an unstamped tag push "
                    "reads as drift on every later verify.")
            results.append({"slug": node.slug,
                            "flywheel": {"node_id": node_id, "slug_name": live.slug,
                                         "revision": live.revision},
                            "content_sha256": node.sha256, "tags_sha256": want})
            assigned += 1
        if results:
            apply_push_results(graph_dir, results, nodes=nodes)
            out(f"  tags: assigned on {len(results)} {kind} node(s)")
    return assigned


def push_lineage(graph_dir: Path, config: dict, record_root_id: str, transport, *,
                 pacer: Pacer, out=print) -> str:
    """Write the archive-lineage body onto the mirror record root (adopted projects)."""
    body = lineage_content(graph_dir, config)
    live = transport.get_node(record_root_id)
    if live.sha256 == body_sha256(body):
        out("  lineage: unchanged")
        return "unchanged"
    mirror_call(lambda: transport.commit(
        node_id=record_root_id, base_revision=live.revision, title=live.title,
        content=body, summary=live.summary), pacer=pacer, what="lineage", out=out)
    out("  lineage: updated")
    return "updated"


def verify_against_mirror(graph_dir: Path, config: dict, transport, *,
                          cache_dir: Path, out=print, strict: bool = False) -> Report:
    """Export this project's own mirror roots and diff them against the node files."""
    roots = mirror_root_ids(config)   # also asserts no archive root is spliced in
    export = transport.export_subgraph(list(roots.values()),
                                       cache_dir / "mirror-verify.json")
    data = json.loads(Path(export).read_text())
    if isinstance(data, dict) and data.get("truncated"):
        raise MirrorError(
            "the mirror export was truncated at max_nodes — every node past the cut "
            "would read as drift. Raise the bound rather than trusting this result.")
    exempt = set(roots.values())
    exempt |= {str(v.get("node_id"))
               for v in (config.get("mirror_roots") or {}).values()
               if isinstance(v, dict) and v.get("node_id")}
    report = verify_mirror(graph_dir, export, exempt, strict=strict)
    for finding in report.violations():
        out(f"DRIFT {finding}")
    out(f"push --verify{' --strict' if strict else ''}: "
        f"{len(report.violations())} drift finding(s)")
    return report

# -------------------------------------------------------------- mirror plumbing

def mirror_paths(config: dict, args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """(cache_dir, journal path, transport run dir) — all under the gitignored cache."""
    cache_dir = Path(config.get("cache_dir") or DEFAULT_CACHE_DIR)
    journal = Path(getattr(args, "journal", None) or cache_dir / "push-journal.jsonl")
    return cache_dir, journal, cache_dir / "push-run"


DEFAULT_PUBLISH_BRANCH = "main"


def publish_branch(config: dict, repo: Path) -> str:
    """The one branch a mirror is built from: config `publish_branch:`, else whatever
    `origin/HEAD` points at, else `main`."""
    named = config.get("publish_branch")
    if named:
        return str(named)
    ref = _git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").strip()
    if ref.startswith("refs/remotes/origin/"):
        return ref[len("refs/remotes/origin/"):]
    return DEFAULT_PUBLISH_BRANCH


def publish_branch_block(config: dict, *, cwd: Path | None = None) -> str | None:
    """→ why this checkout must not publish, or None when it may.

    The mirror is a projection of *published* history, so it is built from the default
    branch and nowhere else — the rule a docs site follows. Publishing from a feature
    branch puts nodes on an append-only public graph that may never merge, and an
    append-only store has no clean retraction [rec: vast-rain-4873].

    There is deliberately **no dirty-tree guard**. Reconcile publishes *before* it
    commits, precisely so `push`'s frontmatter writes land in the same `git add`, so a
    dirty graph is the expected state at push time and refusing on it would break the
    documented flow.
    """
    repo = cwd or Path.cwd()
    if not _git(repo, "rev-parse", "--is-inside-work-tree").strip():
        return None  # not a git checkout — nothing to compare against, so allow
    want = publish_branch(config, repo)
    have = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if not have:
        return None
    if have == "HEAD":
        return ("HEAD is detached, so there is no branch to publish from. Check out "
                f"`{want}` (or pass --allow-any-branch)")
    if have != want:
        return (f"on branch `{have}`, and this project publishes from `{want}`. "
                "Merge first and publish from there, or pass --allow-any-branch")
    return None


def mirror_not_ours(config: dict, transport) -> str | None:
    """→ why this machine cannot publish this project's mirror, or None when it can.

    Distinguishes *a contributor's clone* from *a broken owner setup*. A fork inherits
    the committed `mirror:` key but no credentials for it, and reconcile calls `push`
    unconditionally — so without this the documented workflow exits 2 on every outside
    contributor's machine [rec: vast-rain-4873].
    """
    try:
        status = transport.auth_status()
    except MirrorError as exc:
        return str(exc)
    if not status.get("authenticated"):
        return "not authenticated for this project's mirror"
    expected = str(config.get("mirror_account_id") or "")
    user_id = str(status.get("user_id") or "")
    if expected and user_id and expected != user_id:
        return (f"authenticated as account {user_id}, but this project's mirror belongs "
                f"to {expected} — this clone is not the publisher")
    return None


def mirror_session(config: dict, args: argparse.Namespace):
    """Build (transport, journal, pacer). The one place the mirror path starts."""
    cache_dir, journal_path, run_dir = mirror_paths(config, args)
    transport = make_transport(config, run_dir=run_dir,
                               prefer=getattr(args, "transport", "auto") or "auto")
    pacer = Pacer(float(getattr(args, "rate", None) or 100.0))
    return transport, PushJournal(journal_path), pacer, cache_dir


def cmd_push(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)

    # --- the offline modes, unchanged: plan / record-result / legend / lineage ---
    if args.record_result:
        count = apply_push_results(graph_dir, json.loads(Path(args.record_result).read_text()))
        print(f"push: stamped mirror identity onto {count} node file(s)")
        return 0
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
    if args.plan:
        # Deliberately network-free: this is the fallback for anyone without the
        # binary, and constructs no transport at all.
        plan = push_plan(graph_dir)
        text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            Path(args.output).write_text(text)
            print(f"wrote {args.output}")
        else:
            print(text, end="")
        creates, updates, tags = plan_op_counts(plan)
        print(f"push plan: {creates} create(s), {updates} update(s)"
              + (f", {tags} tag assignment(s)" if tags else ""), file=sys.stderr)
        if creates > PUSH_CREATE_WARN:
            print(f"WARNING {creates} creates is one mirror write each — expect rate limits "
                  f"(429 backoff) and record results in batches so a partial run stays "
                  f"resumable. To mirror less history, split the adoption epoch later so "
                  f"fewer nodes are imported (SPEC: Adoption epochs).", file=sys.stderr)
        for violation in plan["violations"]:
            print(f"VIOLATION {violation}", file=sys.stderr)
        return 1 if plan["violations"] else 0

    if args.verify and not args.against and not mirror_configured(config):
        print("push --verify: no mirror configured — nothing to verify")
        return 0
    if args.verify and args.against:
        # explicit export supplied: stay offline, exactly as before
        exempt = {str(v.get("node_id"))
                  for v in (config.get("mirror_roots") or {}).values()
                  if isinstance(v, dict) and v.get("node_id")}
        report = verify_mirror(graph_dir, args.against, exempt,
                               strict=getattr(args, "strict", False))
        for f in report.violations():
            print(f"DRIFT {f}")
        print(f"\npush --verify: {len(report.violations())} drift finding(s)")
        return 1 if report.violations() else 0

    # --- the executing path -------------------------------------------------
    # Three ways to reach "nothing to publish", all of them exit 0 unless
    # --require-mirror. Together they are what lets the reconcile skill run `push`
    # unconditionally instead of making the agent evaluate a config test — on the
    # maintainer's main, on a feature branch, and on a contributor's fork alike.
    def stand_down(reason: str) -> int:
        if args.require_mirror:
            raise MirrorError(f"{reason} (--require-mirror)")
        print(f"push: {reason} — nothing published")
        return 0

    if not mirror_configured(config):
        print("push: no mirror configured — nothing to publish")
        return 0

    if not args.allow_any_branch:
        if blocked := publish_branch_block(config):
            return stand_down(blocked)

    try:
        transport, journal, pacer, cache_dir = mirror_session(config, args)
        if reason := mirror_not_ours(config, transport):
            return stand_down(reason)
    except (MirrorUnavailable, MirrorAuthError) as exc:
        return stand_down(str(exc))

    if not args.skip_preflight:
        report = mirror_doctor(config, graph_dir, transport, probe_write=False)
        for finding in report.violations():
            print(f"PREFLIGHT {finding}", file=sys.stderr)
        if report.violations():
            raise MirrorError("preflight failed — run `hypergraph mirror doctor` for detail")

    if args.verify:
        report = verify_against_mirror(graph_dir, config, transport, cache_dir=cache_dir,
                                       strict=args.strict)
        return 1 if report.violations() else 0

    if not args.yes and not args.dry_run:
        plan = push_plan(graph_dir)
        creates = sum(1 for o in plan["ops"] if o["op"] == "create")
        if creates > PUSH_CREATE_WARN:
            raise MirrorError(
                f"{creates} creates in one run is above the {PUSH_CREATE_WARN} warning "
                "threshold. Re-run with --yes if that is intended, or --limit N to go "
                "in chunks.")

    summary = execute_push(graph_dir, config, transport, journal=journal, pacer=pacer,
                           batch=args.batch, limit=args.limit, dry_run=args.dry_run,
                           do_legend=not args.no_legend, do_tags=not args.no_tags)
    if summary.get("dry_run"):
        return 0
    if config.get("archive"):
        push_lineage(graph_dir, config, mirror_root_ids(config)["record"], transport,
                     pacer=pacer)
    print(f"push: {summary['created']} created, {summary['updated']} updated"
          + (f", {summary['tagged']} tagged" if summary.get("tagged") else ""))
    if not args.no_verify:
        report = verify_against_mirror(graph_dir, config, transport, cache_dir=cache_dir)
        if report.violations():
            return 1
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """export → render → check → push. The one new verb an agent learns, and it
    says nothing about any hosted service."""
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    cache_dir = args.out_dir or Path(config.get("cache_dir") or DEFAULT_CACHE_DIR)

    cmd_export(argparse.Namespace(config=args.config, graph_dir=graph_dir,
                                  out_dir=cache_dir))
    record_json, state_json = cache_dir / "record.json", cache_dir / "state.json"

    state_md = args.state_md or config.get("state_md") or "STATE.md"
    render_args = argparse.Namespace(state=state_json, config=args.config,
                                     output=Path(state_md))
    cmd_render(render_args)

    check_args = argparse.Namespace(record=record_json, state=state_json,
                                    config=args.config)
    code = cmd_check(check_args)
    if code != 0:
        print("sync: `check` reported violations — not publishing", file=sys.stderr)
        return code
    if args.no_push:
        return 0
    push_args = argparse.Namespace(
        config=args.config, graph_dir=graph_dir, plan=False, record_result=None,
        verify=False, against=None, strict=False, legend=False, lineage=False,
        output=None,
        dry_run=args.dry_run, batch=args.batch, limit=None, yes=args.yes,
        no_legend=False, no_tags=args.no_tags, no_verify=args.no_verify,
        skip_preflight=args.skip_preflight,
        transport=args.transport, rate=args.rate, journal=args.journal,
        allow_any_branch=args.allow_any_branch, require_mirror=args.require_mirror)
    return cmd_push(push_args)


# ---------------------------------------------------------------- mirror doctor

def mirror_doctor(config: dict, graph_dir: Path, transport, *,
                  probe_write: bool = True) -> Report:
    """Preflight, reported in `check`'s own shape so the output reads the same."""
    report = Report()
    if not mirror_configured(config):
        report.add("info", "mirror", "-", "no mirror configured — push is a no-op")
        return report

    report.add("info", "mirror", "-", f"transport: {transport.name} ({transport.version()})")

    try:
        status = transport.auth_status()
    except MirrorError as exc:
        report.add("violation", "mirror", "auth", str(exc))
        return report
    if not status.get("authenticated"):
        report.add("violation", "mirror", "auth",
                   "not authenticated — run `flywheel auth:login`")
        return report
    user_id = str(status.get("user_id") or "")
    report.add("info", "mirror", "auth",
               f"authenticated as {user_id or '(unknown user)'} "
               f"via {status.get('auth_method') or '?'}")

    # Account match. This retires an incident that cost two rounds: a mirror that
    # looked deleted and was not — the key simply belonged to a different account.
    expected = str(config.get("mirror_account_id") or "")
    if expected and user_id and expected != user_id:
        report.add("violation", "mirror", "account",
                   f"this key belongs to account {user_id}, but the config's "
                   f"`mirror_account_id:` says {expected}. The mirror is not missing — "
                   "you are looking at it from the wrong account.")
    elif not expected and user_id:
        report.add("warning", "mirror", "account",
                   f"config has no `mirror_account_id:` — add {user_id} so a "
                   "wrong-key run reports the account rather than a missing graph")

    try:
        roots = mirror_root_ids(config)
    except MirrorError as exc:
        report.add("violation", "mirror", "roots", str(exc))
        return report
    for kind, node_id in roots.items():
        try:
            node = transport.get_node(node_id)
        except MirrorError as exc:
            report.add("violation", "mirror", f"{kind}-root",
                       f"{node_id} does not resolve: {exc}")
            continue
        report.add("info", "mirror", f"{kind}-root",
                   f"{node.slug or node_id} — {node.title!r} (revision {node.revision})")
        if node.can_write is False:
            report.add("violation", "mirror", f"{kind}-root",
                       "the authenticated key cannot write this root")

    if probe_write:
        # Not optional. A key can authenticate cleanly, list hundreds of nodes and
        # 403 every write; there is no scope introspection, so only a real write
        # detects it. Parentless on purpose — under the mirror record root this
        # probe would immediately show up in `verify` as "no local counterpart".
        # The mirror is not scratch space.
        probe = None
        try:
            probe = transport.commit_new(
                parent_ids=[], title="hypergraph write probe",
                content="Transient probe written by `hypergraph mirror doctor`.\n"
                        "If you are reading this, a probe failed to clean up; "
                        "deleting it is safe.\n",
                summary="transient")
            report.add("info", "mirror", "write-probe",
                       f"write accepted (probe {probe.node_id})")
        except MirrorError as exc:
            report.add("violation", "mirror", "write-probe",
                       f"the key authenticated but cannot write: {exc}")
        finally:
            if probe is not None:
                try:
                    transport.delete_node(probe.node_id)
                    report.add("info", "mirror", "write-probe", "probe deleted")
                except MirrorError as exc:
                    report.add("warning", "mirror", "write-probe",
                               f"probe {probe.node_id} could not be deleted ({exc}) — "
                               "delete it by hand; it is parentless, so nothing else "
                               "points at it")

    try:
        plan = push_plan(graph_dir)
    except LocalGraphError as exc:
        report.add("violation", "mirror", "plan", str(exc))
        return report
    creates, updates, tags = plan_op_counts(plan)
    report.add("info", "mirror", "plan",
               f"{creates} create(s), {updates} update(s), "
               f"{tags} tag assignment(s) pending")
    if creates > PUSH_CREATE_WARN:
        report.add("warning", "mirror", "plan",
                   f"{creates} creates at 120 writes/min is roughly "
                   f"{creates // 100 + 1} minute(s) of paced writing")
    for violation in plan["violations"]:
        report.add("violation", "mirror", "plan", violation)
    return report


def cmd_mirror(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)

    if args.action == "doctor":
        if not mirror_configured(config):
            print("mirror doctor: no mirror configured — `push` is a no-op here")
            return 0
        transport, _journal, _pacer, _cache = mirror_session(config, args)
        report = mirror_doctor(config, graph_dir, transport,
                               probe_write=not args.no_write_probe)
        for finding in report.findings:
            print(f"{finding.level:9} {finding}")
        print(f"\nmirror doctor: {len(report.violations())} violation(s), "
              f"{len(report.warnings())} warning(s)")
        return 1 if report.violations() else 0

    if args.action == "roots":
        if not args.mint:
            roots = mirror_root_ids(config)
            for kind, node_id in roots.items():
                print(f"{kind}: {node_id}")
            return 0
        return mint_mirror_roots(config, args)

    if args.action == "pull":
        transport, _journal, _pacer, cache_dir = mirror_session(config, args)
        return mirror_pull(transport, args, out_dir=args.out_dir or cache_dir)

    raise LocalGraphError(f"unknown mirror action: {args.action}")


def mint_mirror_roots(config: dict, args: argparse.Namespace) -> int:
    """Mint both mirror roots and append them to the config, idempotently.

    Titles stay plain — `<project> — record` / `<project> — state`. Any lineage
    belongs in the root's body, never in its title (SPEC: a continuing graph is not
    a copy of the graph it forked from)."""
    existing = config.get("mirror_roots") or {}
    if existing and not args.force:
        raise LocalGraphError(
            "the config already declares `mirror_roots:` — re-minting would orphan the "
            "existing mirror. Pass --force only if you mean to abandon it.")
    transport, _journal, pacer, _cache = mirror_session(config, args)
    project = str(config.get("project") or "project")
    minted = {}
    for kind in GRAPH_KINDS:
        node = mirror_call(lambda kind=kind: transport.commit_new(
            parent_ids=[], title=f"{project} — {kind}",
            content=f"{'Append-only record' if kind == 'record' else 'Distilled state'} "
                    f"graph for {project}.\n\nThis graph is a one-way mirror of the "
                    "markdown node files committed in the repo, which stay canonical.\n",
            summary=f"{kind} graph mirror root for {project}."),
            pacer=pacer, what=f"mint {kind} root")
        minted[kind] = node
        print(f"minted {kind} root: {node.node_id} ({node.slug})")

    if args.config:
        # Surgical append, never a yaml round-trip: safe_dump would destroy 40 of
        # config.example.yml's 68 lines of comments.
        path = Path(args.config)
        text = path.read_text()
        block = ["", "# Mirror roots minted by `hypergraph mirror roots --mint`.",
                 "mirror_roots:"]
        for kind, node in minted.items():
            block += [f"  {kind}:", f"    node_id: {node.node_id}",
                      f"    slug: {node.slug}"]
        path.write_text(text.rstrip("\n") + "\n" + "\n".join(block) + "\n")
        print(f"appended mirror_roots: to {path}")
    return 0


def mirror_pull(transport, args: argparse.Namespace, *, out_dir: Path) -> int:
    """One export over every anchor, split locally into record.json / state.json.

    No `--import` flag: two commands, each inspectable. The split is a BFS from each
    graph's anchors — a node reachable from both is an error, because the two graphs
    are disjoint by construction (SPEC: pointers are markdown, never edges)."""
    record_ids = list(args.record_node_id or []) + list(args.node_id or [])
    state_ids = list(args.state_node_id or [])
    if not record_ids and not state_ids:
        raise LocalGraphError(
            "mirror pull needs at least one anchor: --record-node-id and/or "
            "--state-node-id (--node-id is an alias for the record graph)")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = transport.export_subgraph(record_ids + state_ids,
                                         out_dir / "mirror-pull.json")
    data = json.loads(Path(combined).read_text())
    raw_nodes = data.get("nodes", data) if isinstance(data, dict) else data
    if isinstance(raw_nodes, dict):
        raw_nodes = list(raw_nodes.values())
    by_id = {str(n.get("node_id") or n.get("id")): n for n in raw_nodes
             if isinstance(n, dict) and (n.get("node_id") or n.get("id"))}
    children: dict[str, list[str]] = {nid: [] for nid in by_id}
    for nid, raw in by_id.items():
        for parent in (raw.get("incoming_ids") or raw.get("parent_ids") or []):
            if str(parent) in children:
                children[str(parent)].append(nid)

    def reachable(anchors: list[str]) -> set[str]:
        seen, queue = set(), [a for a in anchors if a in by_id]
        while queue:
            nid = queue.pop()
            if nid in seen:
                continue
            seen.add(nid)
            queue.extend(children.get(nid, []))
        return seen

    record_set, state_set = reachable(record_ids), reachable(state_ids)
    overlap = record_set & state_set
    if overlap:
        raise LocalGraphError(
            f"{len(overlap)} node(s) are reachable from both the record and state "
            f"anchors (e.g. {sorted(overlap)[0]}). The two graphs must stay disjoint — "
            "check the anchors before importing.")

    for kind, ids in (("record", record_set), ("state", state_set)):
        if not ids:
            continue
        # `legacy-` and not `record.json`: `export` writes `record.json` into this
        # same directory by default, so the pull and the first export collided and
        # the export silently destroyed the legacy graph. Step 7 still needs it —
        # `--resolve-prefixes --against` reads it — and it is the only record of
        # pre-import artifact counts. Found on neural-whoop, recovered by re-pulling.
        path = out_dir / f"legacy-{kind}.json"
        path.write_text(json.dumps(
            {"version": EXPORT_VERSION, "graph": kind, "exported_at": utc_now(),
             "nodes": [by_id[i] for i in sorted(
                 ids, key=lambda i: (str(by_id[i].get("created_at") or ""), i))]},
            indent=2, ensure_ascii=False))
        print(f"wrote {path} ({len(ids)} node(s))")

    print("\n# Paste into .hypergraph/config.yml if this graph becomes a frozen archive:",
          file=sys.stderr)
    print("archive:\n  backend: flywheel\n  roots:", file=sys.stderr)
    for nid in record_ids + state_ids:
        raw = by_id.get(nid) or {}
        title = str(raw.get("title") or "").replace("'", "''")
        print(f"    - slug: {raw.get('slug_name') or raw.get('slug') or '?'}\n"
              f"      node_id: {nid}\n      title: '{title}'", file=sys.stderr)
    return 0


# ------------------------------------------------------------------- adoption
# Affordances for hypergraph-adopt. These compute *facts* — git shape, doc
# inventory, id-prefix resolution, a valid config — so the adopting agent spends
# its budget on judgment instead of mechanics.
#
# Deliberately absent: generated prose. No prehistory bodies, no `## Current`
# claims, no negative-knowledge entries. That would produce exactly the
# aspirational template-filling adopt's guardrails forbid, and it breaks I8 by
# definition: a claim nobody derived from evidence they read is not re-derivable.
# **The CLI computes facts; the agent writes claims.**

DOC_PATTERNS = ("README", "CHANGELOG", "CONTRIBUTING", "ARCHITECTURE", "DESIGN",
                "ROADMAP", "NOTES", "TODO", "HISTORY", "ADR", "RFC")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist",
             "build", "target", ".mypy_cache", ".pytest_cache", ".idea", ".vscode"}
ERA_GAP_DAYS = 21   # a quiet stretch this long reads as a boundary between eras


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def survey_tags(repo: Path) -> list[dict]:
    """Release tags, oldest first. The author's own boundary markers when they exist.

    Most repos have none — degrade to an empty list silently, never a warning."""
    out = _git(repo, "tag", "--sort=creatordate",
               "--format=%(refname:short)\t%(creatordate:short)")
    tags = []
    for line in out.splitlines():
        if "\t" in line:
            name, date = line.split("\t", 1)
            tags.append({"tag": name.strip(), "date": date.strip()})
    return tags


def survey_dir_births(repo: Path, source_dirs: list[str]) -> list[dict]:
    """First commit date touching each top-level source dir, oldest first.

    The signal that actually fires: quiet gaps found one era spanning all 347
    commits of a real repo, while directory births found four real boundaries on
    the same history. Bounded to top-level dirs — `git log -- <path>` is the
    slowest call in the survey."""
    births = []
    for name in source_dirs:
        out = _git(repo, "log", "--reverse", "--date=short", "--format=%ad",
                   "--", name)
        first = next((line.strip() for line in out.splitlines() if line.strip()), "")
        if first:
            births.append({"path": name, "date": first})
    return sorted(births, key=lambda entry: (entry["date"], entry["path"]))


def survey_git(repo: Path, source_dirs: list[str] | None = None) -> dict:
    """Repo shape from git alone: age, contributors, timeline signals, churn."""
    log = _git(repo, "log", "--reverse", "--date=short",
               "--pretty=format:%H\t%ad\t%an\t%s")
    rows = [line.split("\t", 3) for line in log.splitlines() if "\t" in line]
    if not rows:
        return {"is_repo": bool(_git(repo, "rev-parse", "--git-dir")), "commits": 0,
                "tags": [], "dir_births": []}

    contributors: dict[str, int] = {}
    for row in rows:
        if len(row) >= 3:
            contributors[row[2]] = contributors.get(row[2], 0) + 1

    # Candidate eras: runs of commits with no gap longer than ERA_GAP_DAYS. These
    # are a *suggestion* for where an adoption epoch might fall — the agent decides.
    eras: list[dict] = []
    previous = None
    for sha, date, *_rest in rows:
        day = datetime.fromisoformat(date).date()
        if previous is not None and (day - previous).days > ERA_GAP_DAYS and eras:
            eras[-1]["end"] = str(previous)
            eras.append({"start": str(day), "end": str(day), "commits": 0,
                         "first_sha": sha})
        elif not eras:
            eras.append({"start": str(day), "end": str(day), "commits": 0,
                         "first_sha": sha})
        eras[-1]["commits"] += 1
        eras[-1]["end"] = str(day)
        previous = day

    churn: dict[str, int] = {}
    for line in _git(repo, "log", "--name-only", "--pretty=format:").splitlines():
        line = line.strip()
        if line:
            churn[line] = churn.get(line, 0) + 1

    return {
        "is_repo": True,
        "commits": len(rows),
        "first_commit": {"sha": rows[0][0][:12], "date": rows[0][1],
                         "subject": rows[0][3] if len(rows[0]) > 3 else ""},
        "last_commit": {"sha": rows[-1][0][:12], "date": rows[-1][1],
                        "subject": rows[-1][3] if len(rows[-1]) > 3 else ""},
        "contributors": sorted(({"name": n, "commits": c} for n, c in contributors.items()),
                               key=lambda e: -e["commits"]),
        "eras": eras,
        "tags": survey_tags(repo),
        "dir_births": survey_dir_births(repo, source_dirs or []),
        "churn": [{"path": p, "changes": c} for p, c in
                  sorted(churn.items(), key=lambda kv: -kv[1])[:15]],
    }


def survey_layout(repo: Path) -> dict:
    """Source dirs, docs, tests, and the onboarding files adopt has to edit."""
    source_dirs, docs = [], []
    for entry in sorted(repo.iterdir()):
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        if entry.is_dir():
            files = sum(1 for _ in entry.rglob("*") if _.is_file())
            source_dirs.append({"path": entry.name, "files": files})
        elif entry.suffix.lower() in (".md", ".rst", ".txt"):
            if any(entry.stem.upper().startswith(p) for p in DOC_PATTERNS):
                docs.append(entry.name)
    for pattern in ("docs", "doc", "adr", "rfcs", "design"):
        directory = repo / pattern
        if directory.is_dir():
            docs += [str(p.relative_to(repo)) for p in sorted(directory.rglob("*.md"))][:40]

    tests = []
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        tests.append("pytest" if (repo / "tests").is_dir() or (repo / "test").is_dir()
                     else "python (no tests/ dir found)")
    if (repo / "package.json").exists():
        tests.append("node")
    if (repo / "go.mod").exists():
        tests.append("go test")
    if (repo / "Cargo.toml").exists():
        tests.append("cargo test")

    # adopt must append to AGENTS.md and must never break a CLAUDE.md → AGENTS.md
    # symlink. That was `ls -la` plus `readlink` by hand; make it mechanical.
    onboarding = {}
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = repo / name
        entry = {"exists": path.exists() or path.is_symlink(),
                 "is_symlink": path.is_symlink()}
        if path.is_symlink():
            entry["target"] = str(path.readlink())
            entry["target_exists"] = path.exists()
        if path.exists() and not path.is_dir():
            text = path.read_text(errors="replace")
            entry["bytes"] = len(text)
            entry["has_hypergraph_block"] = "<!-- hypergraph:begin -->" in text
        onboarding[name] = entry

    return {"source_dirs": source_dirs, "docs": sorted(set(docs)), "tests": tests,
            "onboarding": onboarding,
            "already_adopted": (repo / ".hypergraph" / "config.yml").exists()}


def adopt_survey(repo: Path) -> dict:
    # Layout first: its top-level source dirs are the input to the directory-birth
    # signal, which is the timeline evidence that actually fires on a real repo.
    layout = survey_layout(repo)
    return {"repo": str(repo), "surveyed_at": utc_now(),
            "git": survey_git(repo, [d["path"] for d in layout["source_dirs"]]),
            "layout": layout}


def print_timeline_signals(git: dict) -> None:
    """Three independent signals about where an era boundary might fall.

    Each is printed as *evidence*, never as a decided era: the author knows which
    of them meant something and the CLI does not. Each of the three prints either its
    findings or an explicit "none", so a quiet category is never mistaken for one that
    did not run."""
    tags, births = git.get("tags") or [], git.get("dir_births") or []
    gaps = git.get("eras") or []
    print("\n## Timeline signals (evidence for an epoch boundary — *suggestions*, "
          "not epochs)\n")
    # Every category prints, empty or not. Printing only the ones that fired left a
    # reader unable to tell "no tags in this repo" from "tags were not computed" —
    # one adoption had to read `--survey --json` to find out which, and a silent
    # category reads as an absent feature.
    if tags:
        print("  tags — the author's own markers")
        for tag in tags:
            print(f"    {tag['date']}  {tag['tag']}")
    else:
        print("  tags — none in this repo")
    if births:
        print("  directory births — first commit touching each top-level source dir")
        for birth in births:
            print(f"    {birth['date']}  {birth['path']}/")
    else:
        print("  directory births — none")
    if len(gaps) > 1:
        print(f"  quiet gaps — runs separated by more than {ERA_GAP_DAYS} idle days")
        for era in gaps:
            print(f"    {era['start']} → {era['end']}  {era['commits']:>5} commits")
    else:
        print(f"  quiet gaps — none longer than {ERA_GAP_DAYS} idle days; this repo "
              "reads as one continuous era")


def print_survey(survey: dict) -> None:
    git, layout = survey["git"], survey["layout"]
    print(f"# Survey of {survey['repo']}\n")
    if layout["already_adopted"]:
        print("ALREADY ADOPTED — .hypergraph/config.yml exists. Use orient/record "
              "instead of adopt.\n")
    if not git.get("is_repo"):
        print("Not a git repository — mode B has only the working tree to go on.\n")
    elif git.get("commits"):
        first, last = git["first_commit"], git["last_commit"]
        print(f"## Git\n\n{git['commits']} commits, {first['date']} → {last['date']}, "
              f"{len(git['contributors'])} contributor(s)")
        print(f"  first: {first['sha']} {first['subject'][:60]}")
        print(f"  head:  {last['sha']} {last['subject'][:60]}")
        top = ", ".join(f"{c['name']} ({c['commits']})" for c in git["contributors"][:5])
        print(f"  top:   {top}")
        print_timeline_signals(git)
        print("\n## Highest-churn paths\n")
        for row in git["churn"][:10]:
            print(f"  {row['changes']:>5}  {row['path']}")

    print("\n## Layout\n")
    for entry in layout["source_dirs"]:
        print(f"  {entry['files']:>5} files  {entry['path']}/")
    print(f"\n  tests: {', '.join(layout['tests']) or 'none detected'}")
    print(f"\n## Docs ({len(layout['docs'])})\n")
    for doc in layout["docs"][:25]:
        print(f"  {doc}")
    if len(layout["docs"]) > 25:
        print(f"  … and {len(layout['docs']) - 25} more")

    print("\n## Onboarding files\n")
    for name, entry in layout["onboarding"].items():
        if not entry["exists"]:
            print(f"  {name}: absent")
        elif entry["is_symlink"]:
            state = "resolves" if entry.get("target_exists") else "BROKEN"
            print(f"  {name}: symlink → {entry.get('target')} ({state}) — edit the "
                  "TARGET, never the link")
        else:
            print(f"  {name}: {entry['bytes']} bytes, hypergraph block: "
                  f"{'present' if entry.get('has_hypergraph_block') else 'absent'}")

    print("\nThe CLI computed the facts above. The claims — what actually works, what "
          "is broken,\nwhat was tried and abandoned — are yours to write, from evidence "
          "you read.")


def resolve_id_prefixes(repo: Path, against: Path) -> dict:
    """Map raw node-id prefixes cited in tracked docs to slugs.

    Docs written before adoption often cite `b3ea0b95` rather than a slug, and the
    protocol's pointer currency is slugs. Hex tokens that match no node id are left
    alone and reported separately — most of them are git SHAs."""
    nodes = _load_export_nodes(against)
    by_id = {nid.replace("-", "").lower(): raw for nid, raw in nodes.items()}
    tracked = [line for line in _git(repo, "ls-files").splitlines() if line.strip()]
    token_re = re.compile(r"\b[0-9a-f]{8,}\b")

    hits: dict[str, dict] = {}
    unmatched: dict[str, int] = {}
    for rel in tracked:
        path = repo / rel
        if path.suffix.lower() not in (".md", ".rst", ".txt", ".yml", ".yaml", ".json"):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for token in set(token_re.findall(text)):
            flat = token.replace("-", "").lower()
            matches = [raw for key, raw in by_id.items() if key.startswith(flat)]
            if not matches:
                unmatched[token] = unmatched.get(token, 0) + 1
                continue
            entry = hits.setdefault(token, {"prefix": token, "files": [],
                                            "candidates": []})
            entry["files"].append(rel)
            entry["candidates"] = [
                {"node_id": str(m.get("node_id") or m.get("id")),
                 "slug": str(m.get("slug_name") or m.get("slug") or ""),
                 "title": str(m.get("title") or "")} for m in matches]
    return {"resolved": [h for h in hits.values() if len(h["candidates"]) == 1],
            "ambiguous": [h for h in hits.values() if len(h["candidates"]) > 1],
            "unmatched_hex_tokens": sorted(unmatched)}


def create_root_node(graph_dir: Path, kind: str, title: str, body: str) -> str:
    """Mint a parentless graph root, through the same primitives `new --root` uses.

    Exists so adopt can write a *valid* config in one step. Hand-written YAML is a
    proven failure mode: a stub config with no roots once made `check` report 0
    violations while it silently guessed them (see `load_config`)."""
    existing = {k: load_local_nodes(graph_dir, k, missing_ok=True) for k in GRAPH_KINDS}
    roots = [s for s, n in existing[kind].items() if not n.parents]
    if roots:
        raise LocalGraphError(f"the {kind} graph already has a root: {', '.join(roots)}")
    slug = mint_slug(set(existing["record"]) | set(existing["state"]))
    created_at = utc_now()
    if kind == "record":
        content = compose_record_content(body, [], None, None, True)
    else:
        content = compose_state_content(body, "", [], [], None, created_at, True)
    _report_and_raise(
        validate_node_content(kind, slug, title, content, created_at,
                              local_graph(existing["record"], "record"),
                              local_graph(existing["state"], "state"), True),
        f"new {kind} root `{slug}`")
    meta = {"node_id": node_id_for(slug), "slug": slug, "title": title,
            "created_at": created_at, "parents": [], "summary": ""}
    directory = graph_kind_dir(graph_dir, kind)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(render_node_file(meta, content))
    return slug


def ensure_root_node(graph_dir: Path, kind: str, title: str,
                     body: str) -> tuple[str, bool]:
    """Adopt the graph's existing root, or mint one — returns `(slug, minted)`.

    Adoption arrives from both directions and `--init` has to land either way:
    mode A imports the legacy graph first and inits *over* the imported root
    (minting a rival would be wrong), and mode B may already have hand-authored
    prehistory that needed a root to parent on. `create_root_node` stays strict —
    it is the primitive; this is the policy. Two parentless roots is genuinely
    ambiguous, so it raises rather than picking."""
    existing = load_local_nodes(graph_dir, kind, missing_ok=True)
    roots = sorted(slug for slug, node in existing.items() if not node.parents)
    if len(roots) == 1:
        return roots[0], False
    if roots:
        raise LocalGraphError(
            f"the {kind} graph has {len(roots)} parentless roots: "
            f"{', '.join(roots)} — adopt --init will not choose between them. "
            "Re-parent all but one by hand, then re-run.")
    return create_root_node(graph_dir, kind, title, body), True


def cmd_adopt(args: argparse.Namespace) -> int:
    repo = Path(args.repo or ".").resolve()

    if args.survey:
        survey = adopt_survey(repo)
        if args.json:
            print(json.dumps(survey, indent=2, ensure_ascii=False))
        else:
            print_survey(survey)
        return 0

    if args.pull:
        config = load_config(args.config)
        transport, _journal, _pacer, cache_dir = mirror_session(config, args)
        return mirror_pull(transport, args, out_dir=args.out_dir or cache_dir)

    if args.resolve_prefixes:
        if not args.against:
            raise LocalGraphError(
                "adopt --resolve-prefixes needs --against <legacy-export.json>")
        result = resolve_id_prefixes(repo, args.against)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        for hit in result["resolved"]:
            node = hit["candidates"][0]
            print(f"{hit['prefix']} → {node['slug']}   {node['title'][:60]}")
            for rel in sorted(set(hit["files"]))[:5]:
                print(f"      cited in {rel}")
        for hit in result["ambiguous"]:
            print(f"AMBIGUOUS {hit['prefix']} matches "
                  f"{len(hit['candidates'])} nodes — resolve by hand, never guess")
        print(f"\nresolved {len(result['resolved'])}, "
              f"ambiguous {len(result['ambiguous'])}, "
              f"{len(result['unmatched_hex_tokens'])} hex token(s) matched no node "
              "(most will be git SHAs)")
        return 1 if result["ambiguous"] else 0

    if args.init:
        return adopt_init(repo, args)

    if args.marker:
        return adopt_marker(repo, args)

    raise LocalGraphError(
        "adopt needs one of --survey, --pull, --init, --marker, --resolve-prefixes. "
        "The judgment parts — distilling state, writing prehistory, interviewing the "
        "user — are the hypergraph-adopt skill's job, not this command's.")


def adopt_init(repo: Path, args: argparse.Namespace) -> int:
    """Mint (or adopt) both roots and write a *valid* config.

    Hand-written YAML is a proven failure mode: a stub config with no roots once made
    `check` report 0 violations while silently guessing them (see `load_config`). So
    `--init` must never be the step an agent has to route around: when a root already
    exists — imported in mode A, hand-authored in mode B — it adopts that root instead
    of refusing."""
    config_path = Path(args.config) if args.config else repo / ".hypergraph" / "config.yml"
    if config_path.exists() and not args.force:
        raise LocalGraphError(
            f"{config_path} already exists — this project is initialized. Use "
            "orient/record/reconcile, or pass --force to overwrite.")
    project = args.project or repo.name
    graph_dir = args.graph_dir or (repo / DEFAULT_GRAPH_DIR)

    def body(path, fallback):
        return Path(path).read_text() if path else fallback

    record_body = body(args.record_body,
                       f"Append-only record graph root for {project}.\n\n"
                       "Every unit of work lands here as a node with a declared "
                       "`## State Impact` (SPEC I1/I2).\n")
    state_body = body(args.state_body,
                      f"Distilled state graph root for {project}.\n\n"
                      "What is true now: architecture, what works, what is broken or "
                      "open. Rewritten only by reconcile (SPEC I3).\n")

    record_slug, record_minted = ensure_root_node(
        graph_dir, "record", f"{project} — record", record_body)
    state_slug, state_minted = ensure_root_node(
        graph_dir, "state", f"{project} — state", state_body)

    def root_id(kind: str, slug: str) -> str:
        """The node's *own* id, not one derived from its slug.

        `node_id_for(slug)` is right only for a root this command minted. A mode-A
        adoption imports the legacy root with `--fork`, which preserves the archive's
        node_id verbatim — so deriving the id from the slug wrote a config that
        disagreed with the node file it pointed at. `check` does not compare them,
        and `mirror_root_ids()`/`push` read the config, so the graph would have
        published under an id nothing else in the repo used. Found on neural-whoop,
        where the config claimed 8e92751d… and the node file said 51aabea1…."""
        node = load_local_nodes(graph_dir, kind, missing_ok=True).get(slug)
        return (node.node_id if node and node.node_id else node_id_for(slug))

    try:
        declared_graph_dir = Path(graph_dir).resolve().relative_to(repo)
    except ValueError:
        declared_graph_dir = Path(graph_dir)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        f"# .hypergraph/config.yml — written by `hypergraph adopt --init`.\n"
        f"project: {project}\n\n"
        f"# The release that last installed this project's skills, AGENTS.md block\n"
        f"# and workflows — refreshed by `hypergraph upgrade`.\n"
        f"hypergraph_version: {__version__}\n\n"
        f"record_root:\n  node_id: {root_id('record', record_slug)}\n  slug: {record_slug}\n\n"
        f"state_root:\n  node_id: {root_id('state', state_slug)}\n  slug: {state_slug}\n\n"
        f"cache_dir: .hypergraph/cache\n"
        f"state_md: STATE.md\n"
        f"graph_dir: {declared_graph_dir}\n")
    print(f"record root: {record_slug} ({'minted' if record_minted else 'adopted existing'})")
    print(f"state root:  {state_slug} ({'minted' if state_minted else 'adopted existing'})")
    print(f"wrote {config_path}")
    print("\nNext: import or author the history, then `hypergraph adopt --marker "
          "<slug>` once the epoch marker node exists.")
    return 0


def adopt_marker(repo: Path, args: argparse.Namespace) -> int:
    """Record the adoption epoch, after checking the marker actually resolves."""
    config_path = Path(args.config) if args.config else repo / ".hypergraph" / "config.yml"
    if not config_path.exists():
        raise LocalGraphError(f"{config_path} does not exist — run adopt --init first")
    config = load_config(config_path)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    if not Path(graph_dir).is_absolute():
        graph_dir = repo / graph_dir
    nodes = load_local_nodes(graph_dir, "record", missing_ok=True)
    if args.marker not in nodes:
        raise LocalGraphError(
            f"`{args.marker}` is not a record node under {graph_dir}. The epoch marker "
            "must resolve, or `check` exempts nothing and every legacy node is held to "
            "full I2 compliance.")
    text = config_path.read_text()
    if "epoch:" in text:
        raise LocalGraphError(
            f"{config_path} already declares an `epoch:` block — a project has one "
            "adoption epoch. Edit it by hand if the marker genuinely changed.")
    config_path.write_text(
        text.rstrip("\n") + "\n\n"
        "# Adoption epoch (SPEC: Adoption epochs). Record nodes created strictly\n"
        "# before this marker are legacy history, exempt from I2 in `check`.\n"
        f"epoch:\n  marker: {args.marker}\n")
    older = sum(1 for n in nodes.values() if n.created_at < nodes[args.marker].created_at)
    print(f"epoch marker: {args.marker} ({nodes[args.marker].created_at})")
    print(f"appended epoch: to {config_path} — {older} older record node(s) now exempt")
    return 0


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
  /* Open the tuning panel and this block gets tall. It scrolls itself rather
     than squeezing the node panel out of existence below it. */
  #controls { flex:none; max-height:72%; overflow-y:auto; padding:12px 18px;
              border-bottom:1px solid var(--grid); }
  #search { width:100%; font:inherit; font-size:12.5px; padding:5px 10px;
            border-radius:8px; border:1px solid var(--grid); background:var(--page);
            color:var(--ink); outline:none; }
  #search:focus { border-color:var(--accent); }
  #presets { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
  #presets button { flex:1; border:1px solid var(--grid); background:transparent;
                    color:var(--ink2); font:inherit; font-size:12px; padding:4px 0;
                    border-radius:999px; cursor:pointer; white-space:nowrap; }
  #presets button:hover { color:var(--ink); border-color:var(--muted); }
  #presets button.active { background:var(--page); color:var(--ink);
                           font-weight:600; border-color:var(--muted); }
  /* tag chips: annotation, so they filter and never restyle a node — a tag has no
     standing in the protocol and the drawing must not imply it has one */
  #tagchips { display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; }
  #tagchips[hidden] { display:none; }
  #tagchips button { border:1px solid transparent; font:inherit; font-size:11px;
                     padding:2px 8px; border-radius:999px; cursor:pointer;
                     opacity:.55; white-space:nowrap; }
  #tagchips button:hover { opacity:.85; }
  #tagchips button.active { opacity:1; border-color:var(--ink); font-weight:600; }
  #tagchips button i { font-style:normal; opacity:.7; margin-left:5px; }
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
  /* arrange: move the whole drawing without changing what is drawn */
  #arrange { display:flex; flex-wrap:wrap; align-items:center; gap:6px;
             margin-top:12px; }
  #arrange .lbl { font-size:10.5px; text-transform:uppercase; letter-spacing:.05em;
                  color:var(--muted); width:48px; flex:none; }
  #arrange button { border:1px solid var(--grid); background:var(--page);
                    color:var(--ink2); font:inherit; font-size:12px;
                    padding:3px 9px; border-radius:8px; cursor:pointer;
                    white-space:nowrap; }
  #arrange button:hover { color:var(--ink); border-color:var(--muted); }
  #arrange button[hidden] { display:none; }
  /* blob tuning: collapsed by default, so it costs nothing until you open it */
  #tuning { margin-top:12px; }
  #tuning summary { font-size:11px; text-transform:uppercase; letter-spacing:.05em;
                    color:var(--muted); cursor:pointer; list-style:none;
                    padding:2px 0; }
  #tuning summary::-webkit-details-marker { display:none; }
  #tuning summary::before { content:"▸ "; }
  #tuning[open] summary::before { content:"▾ "; }
  #tuning summary:hover { color:var(--ink2); }
  #sliders { margin-top:8px; }
  .tunegroup { font-size:10.5px; text-transform:uppercase; letter-spacing:.05em;
               color:var(--muted); margin:10px 0 4px; }
  .tunegroup:first-child { margin-top:0; }
  .row { margin-bottom:9px; }
  .row .rowhead { display:flex; justify-content:space-between; align-items:baseline;
                  font-size:12px; color:var(--ink2); }
  .row .value { font-family:ui-monospace, SFMono-Regular, Menlo, monospace;
                font-size:11px; color:var(--muted); }
  .row .value.changed { color:var(--accent); }
  .row .value.changed::after { content:" •"; }
  .row .hint { color:var(--muted); font-size:11px; margin-top:1px; line-height:1.4; }
  input[type=range] { width:100%; accent-color:var(--accent); margin:2px 0 0;
                      display:block; }
  .tunebtns { display:flex; gap:6px; margin-top:4px; }
  .tunebtns button { border:1px solid var(--grid); background:var(--page);
                     color:var(--ink2); font:inherit; font-size:12px;
                     padding:3px 10px; border-radius:8px; cursor:pointer;
                     white-space:nowrap; }
  .tunebtns button:hover { color:var(--ink); border-color:var(--muted); }
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
  .stats td { padding:1px 10px 2px 0; color:var(--ink2); font-size:12px;
              vertical-align:top; line-height:1.45; }
  .stats td:first-child { color:var(--muted); white-space:nowrap; }
  .stats code { font-family:ui-monospace, SFMono-Regular, Menlo, monospace;
                font-size:11px; background:var(--code); padding:0 3px;
                border-radius:3px; }
  .hint code { font-family:ui-monospace, SFMono-Regular, Menlo, monospace;
               font-size:11px; background:var(--code); padding:0 3px;
               border-radius:3px; }
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
        <button data-preset="everything" title="Everything on">Everything</button>
      </div>
      <!-- Tag chips. Only rendered when the graph carries tags; a project that
           tags nothing sees no control at all. -->
      <div id="tagchips" hidden></div>
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
      <div id="arrange">
        <span class="lbl">Arrange</span>
        <button id="arSpread" title="More space between everything">Spread</button>
        <button id="arTighten" title="Pull everything back in">Tighten</button>
        <button id="arShuffle" title="A different force layout">Shuffle</button>
        <button id="arRelax" title="Settle from where things are now">Relax</button>
        <button id="arReset" title="Back to the original layout, recomputed">Reset</button>
      </div>
      <details id="tuning">
        <summary>Blob tuning</summary>
        <div id="sliders"></div>
        <div class="tunebtns">
          <button id="tuneReset">Reset</button>
          <button id="tuneCopy">Copy as YAML</button>
        </div>
      </details>
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

// Display state: one unified view driven by toggles. The five views below are
// named after the job they do; any custom mix of toggles is equally valid.
//
// These values are the `everything` preset, which is also what the page boots
// into (boot.js). They are kept in step by hand: `applyPreset` assigns over this
// object at boot, so a disagreement would never show — it would just be a lie.
const show = {
  graphs: "both",     // "record" | "state" | "both"
  style:  "circles",  // "cards" | "circles"
  layout: "force",    // "timeline" | "board" | "layered" | "force"
  xaxis:  "rank",     // timeline only: "rank" (even) | "time" (real dates)
  board:  "status",   // board only: "status" columns | "tree" architecture
  window: "all",      // record graph: "all" or the most recent N by chrono
  links:  "all",      // cross-graph links: "focus" | "all" | "none"
  tree:   true,       // intra-graph parent edges
  impact: true,       // include impact links among the cross-graph ones
  prov:   true,       // include provenance links among them (needs graphs both)
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
// The shuffle seed *is* part of the signature — shuffling back to a seed you had
// before restores that whole arrangement, drags and all, out of `positions`.
const layoutKey = () => [show.layout, show.graphs, show.style, show.xaxis,
                         show.board, show.window, forceSeed,
                         [...collapsed].sort().join(",")].join(":");

// Bumped once per drag frame and once per Arrange action. Positions are mutated
// in place, so nothing else in a cache key changes when a node moves; anything
// keyed on where things are (the blob outlines, the obstacle grid) folds this in.
let posEpoch = 0;

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

// Five views, each named after its job. Timeline = what happened, in order.
// Frontier = what is true now, and what is open. Provenance = which record work
// each state claim rests on. Clusters = which work belongs to the same claim.
// Everything = all of it at once, which is the page's default: it shows what is
// there before it shows you a slice of it. The four focused views are one click
// away, and each of them is quieter on purpose.
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
  everything: { graphs:"both",   style:"circles", layout:"force",
                xaxis:"rank", board:"status", links:"all",   window:"all",
                tree:true, impact:true,  prov:true,  blobs:true },
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
// Active tag chips. Empty means "no tag filter", which is not the same as "no tags
// selected" — a filter that hid everything by default would make the control a
// mode rather than a lens.
const activeTags = new Set();
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

// FNV-1a hash of a string -> [0,1). Deterministic jitter source so the force
// layout is identical on every load (no randomness anywhere in this page).
function fnv1a(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h / 4294967296;
}

// Shuffle asks for *a different* arrangement, not a random one, so it walks a
// counter rather than reaching for a random number. Seed 0 hashes byte-for-byte
// as the unseeded hash did, so the layout you get on load never moves; 1, 2, 3…
// each give one other arrangement, reproducibly — an exported SVG still matches.
let forceSeed = 0;
function hashSlug(s) {
  return fnv1a(forceSeed ? s + "#" + forceSeed : s);
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

  // A single vertical rule reads as "everything to the right is unreconciled". That
  // only holds for a linear record graph; once a merge gives it several tips, no one
  // x-position separates the two sets, so the rule is suppressed and the per-node
  // "unreconciled" accent carries the information on its own. The exporter sets
  // high_water_mark to null whenever the frontier has more than one tip.
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

// Jitter throughout this file comes from `hashSlug` (core.js): FNV-1a of the
// slug, so every load lays out identically. It used to be declared here too,
// with an identical body — two hoisted declarations in one scope, where the
// later one silently won. The seeded copy in core.js is now the only one.

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
function runSim(pos, homes, ticks, alpha0) {
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
  let alpha = alpha0 || 1.0;
  const n = ticks || NODE_TICKS;
  for (let t = 0; t < n; t++) {
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

// ------------------------------------------------------------------- relax
// Settle the arrangement that is on screen *now*, rather than computing a new
// one. Every home comes from the current centroid of a hyperedge's members, so
// a cluster you dragged across the canvas stays where you put it and only the
// overlaps inside it come apart. Short and cool: this is a nudge, not a redo.
// The full layout runs 240 ticks from alpha 1 and ends cold, near 0.03. Relax
// starts at 0.15 and lands in the same place, so on an already-settled drawing
// it barely moves anything — reheating past that is not settling, it is a redo
// wearing the wrong label.
const RELAX_TICKS = 90, RELAX_ALPHA = 0.15;

function relaxLayout(pos) {
  const H = hyperedges(), centre = {};
  H.list.forEach(h => {
    let x = 0, y = 0, n = 0;
    h.members.forEach(m => { const p = pos[m]; if (p) { x += p.x; y += p.y; n++; } });
    if (n) centre[h.state] = { x: x / n, y: y / n };
  });
  const homes = {};
  DATA.record.nodes.forEach(n => {
    if (!pos[n.slug]) return;
    const owners = (H.memberOf[n.slug] || []).filter(st => centre[st]);
    if (!owners.length) return;
    let x = 0, y = 0;
    owners.forEach(st => { x += centre[st].x; y += centre[st].y; });
    homes[n.slug] = { x: x / owners.length, y: y / owners.length,
                      weight: owners.length > 1 ? 0.10 : 0.22 };
  });
  DATA.state.nodes.forEach(n => {
    if (pos[n.slug] && centre[n.slug])
      homes[n.slug] = { x: centre[n.slug].x, y: centre[n.slug].y, weight: 0.18 };
  });
  // A node no claim ever cited has no home to go to, and the sim's fallback is a
  // slow pull toward the origin — over 90 ticks that walks a far-out node a few
  // hundred px, which is exactly the "it moved my thing" this button avoids. So
  // anchor it where it already is, loosely enough that overlaps still come apart.
  for (const slug in pos) if (!homes[slug])
    homes[slug] = { x: pos[slug].x, y: pos[slug].y, weight: 0.06 };
  runSim(pos, homes, RELAX_TICKS, RELAX_ALPHA);
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
// Every field here is live: the Blob tuning sliders (tuning.js) write straight
// into this object, and each reach below is read at call time, so a slider moves
// the geometry with no re-plumbing. `fillOpacity` is a percentage.
const BLOB = { padding: 15, corridor: 10, smoothing: 18, clearance: 11,
               resolution: 5, tolerance: 1.4, maxPoints: 220, dragCoarsen: 2.5,
               fillOpacity: 14, strokeWidth: 1.2, labelSize: 10.5 };
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
// the honest choice. A drag no longer falls back to it — see blobFieldMode.
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
  // A drag traces on a coarser grid, so it has fewer real points to keep;
  // holding the full budget there would only preserve the grid's own steps.
  const maxPoints = blobDragging ? BLOB.maxPoints * 0.6 : BLOB.maxPoints;
  let simplified = douglasPeucker(open, BLOB.tolerance);
  let attempt = BLOB.tolerance;      // coarsen rather than emit hundreds of points
  while (simplified.length > maxPoints && attempt < 512) {
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
  // A drag keeps the real field — the shape it makes is the whole point — and
  // pays for the frame rate with a coarser grid instead of with a convex hull.
  // Sampling is quadratic in the pitch, so 2.5x here is about 1/6 of the work.
  const pitch = BLOB.resolution * (blobDragging ? BLOB.dragCoarsen : 1);
  // The field is positive everywhere outside this margin, which keeps the
  // contour off the edge of the grid and so keeps every loop closed. It is three
  // cells of whatever pitch this pass uses, so a coarse pass stays closed too.
  const margin = BLOB.padding + BLOB.corridor + BLOB.smoothing + pitch * 3;
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

  let resolution = pitch;
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
//
// `posEpoch` is in the key because a drag mutates `pos` in place: the node count
// and the layout signature both stay exactly what they were, so without it a
// node dragged into a cluster would never become an obstacle for that cluster.
let _avoidGrid = null, _avoidGridKey = "";
function avoidGrid(pos) {
  const key = Object.keys(pos).length + ":" + posEpoch + ":" + layoutKey();
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

// True when the distance field is worth computing. Only the zoom decides: below
// BLOB_FIELD_MIN_ZOOM the field's detail cannot be seen, so the cheap hull is
// honest there. A drag stays on the field and coarsens the grid instead —
// swapping in the hull mid-drag replaced the shape with a much larger one, which
// read as the blob breaking rather than as a deliberate saving.
let blobDragging = false;
function blobFieldMode() {
  return tfFor().k >= BLOB_FIELD_MIN_ZOOM;
}

// Cached per hyperedge so a re-render (theme flip, dim pass) does not recompute
// the field. Keyed by the positions the field was built from — *and* by
// `posEpoch`, because the outline also depends on where the non-members are:
// dragging one of those through a blob leaves every member position untouched,
// and a member-only key would then hand back the pre-drag shape.
const blobCache = new Map();
function blobGeometry(h, pos) {
  const key = posEpoch + "|" + h.state + "|" + h.members.map(s => {
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

// Anchoring every label reads every outline, and a drag repaints one or two
// blobs — computing the other twelve fields to place labels that are not moving
// would cost more than the drag itself. So a drag anchors on whatever geometry
// each blob last had; pointerup redraws the layer and the labels land exactly.
function labelLoops(h, pos) {
  if (!blobFieldMode()) return null;
  if (!blobDragging) return blobGeometry(h, pos);
  const hit = blobCache.get(h.state);
  return hit ? hit.value : null;
}

function blobLabelPositions(pos) {
  const placed = [], out = {};
  hyperedges().list.forEach(h => {
    const loops = labelLoops(h, pos);
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

// Which blobs a node at its current position can bend, whether or not it is a
// member of them. A non-member is subtracted from the field, so moving one into
// a cluster changes that cluster's outline — the repaint during a drag has to
// cover those, not only the blobs the dragged node belongs to.
function blobsTouching(slug, pos) {
  const p = pos[slug];
  if (!p) return [];
  const d = dimsOf(slug);
  const reach = BLOB.padding + BLOB.corridor + BLOB.smoothing + BLOB.clearance + 40;
  const x0 = p.x - d.w / 2 - reach, x1 = p.x + d.w / 2 + reach;
  const y0 = p.y - d.h / 2 - reach, y1 = p.y + d.h / 2 + reach;
  const out = [];
  hyperedges().list.forEach(h => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    h.members.forEach(m => {
      const q = pos[m];
      if (!q) return;
      const dm = dimsOf(m);
      minX = Math.min(minX, q.x - dm.w / 2); maxX = Math.max(maxX, q.x + dm.w / 2);
      minY = Math.min(minY, q.y - dm.h / 2); maxY = Math.max(maxY, q.y + dm.h / 2);
    });
    if (isFinite(minX) && minX <= x1 && maxX >= x0 && minY <= y1 && maxY >= y0)
      out.push(h.state);
  });
  return out;
}

// ------------------------------------------------------------------ tuning
// Live controls for the blob geometry, in the shape excaligraph's playground
// uses: one row per knob — label, current value, a dot when you have moved it
// off the default, and a line saying what it does.
//
// Every knob is a field of BLOB, and every reach in blob.js reads BLOB at call
// time, so writing the field *is* the plumbing. Nothing here touches `show`:
// activePreset() compares every key of that object against each preset, so a
// key the presets do not carry would darken every chip forever.
//
// Precedence: the hard defaults in blob.js, then the `viz.blob` block of
// .hypergraph/config.yml (baked into the page as DATA.settings.blob), then
// whatever this browser last saved. Reset drops the saved values and returns to
// what the config says — which is the point of putting the block in the config:
// a tuning you like travels with the repo instead of with your laptop.

const TUNE_STORE = "hypergraph.viz.blob";

const SLIDERS = [
  { key: "padding", group: "Shape", min: 0, max: 60, step: 1,
    hint: "Stand-off from each node's outline. It also rounds the outer corners." },
  { key: "corridor", group: "Shape", min: 0, max: 40, step: 1,
    hint: "Half-width of the band along the spanning tree — what keeps far-apart " +
          "members one body instead of separate islands." },
  { key: "smoothing", group: "Shape", min: 0, max: 60, step: 1,
    hint: "How softly the parts merge. This is the fillet: 0 gives hard seams " +
          "where two members meet." },
  { key: "clearance", group: "Shape", min: 0, max: 40, step: 1,
    hint: "How far the outline stays off a node that is not a member." },
  { key: "resolution", group: "Tracing", min: 2, max: 20, step: 1,
    hint: "Grid step for tracing the outline — smaller follows the true shape " +
          "and costs more." },
  { key: "tolerance", group: "Tracing", min: 0.2, max: 6, step: 0.1,
    hint: "How far a point may be dropped from the traced line. Higher is " +
          "simpler and flatter." },
  { key: "maxPoints", group: "Tracing", min: 40, max: 400, step: 10,
    hint: "Cap on points per outline. Past it, tracing coarsens rather than " +
          "emit hundreds." },
  { key: "dragCoarsen", group: "Tracing", min: 1, max: 5, step: 0.5,
    hint: "How much coarser the grid goes while you drag a node. Raise it if a " +
          "big cluster feels heavy." },
  { key: "fillOpacity", group: "Style", min: 0, max: 60, step: 1,
    hint: "Fill strength, in percent. Dark mode adds 4 on top." },
  { key: "strokeWidth", group: "Style", min: 0, max: 5, step: 0.5,
    hint: "Outline weight. 0 leaves the fill alone." },
  { key: "labelSize", group: "Style", min: 7, max: 20, step: 0.5,
    hint: "Type size of the claim slug drawn on the blob." },
];

// What Reset returns to: the hard defaults, overlaid by the config block. Filled
// in by initTuning before anything has had a chance to move.
const TUNE_BASE = {};

function tuneClamp(spec, value) {
  const n = Number(value);
  if (!isFinite(n)) return null;
  return Math.min(spec.max, Math.max(spec.min, n));
}

// localStorage is unavailable in some file:// sandboxes, and a page that throws
// there would be worse than one that simply does not remember.
function storedTuning() {
  try {
    return JSON.parse(localStorage.getItem(TUNE_STORE) || "{}") || {};
  } catch (err) { return {}; }
}
function saveTuning() {
  const out = {};
  SLIDERS.forEach(s => { if (BLOB[s.key] !== TUNE_BASE[s.key]) out[s.key] = BLOB[s.key]; });
  try {
    if (Object.keys(out).length) localStorage.setItem(TUNE_STORE, JSON.stringify(out));
    else localStorage.removeItem(TUNE_STORE);
  } catch (err) { /* no store: the sliders still work for this session */ }
}

function tuneFormat(spec, value) {
  return spec.step < 1 ? value.toFixed(1) : String(value);
}

function buildSliders() {
  const box = document.getElementById("sliders");
  if (!box) return;
  box.textContent = "";
  let group = null;
  SLIDERS.forEach(spec => {
    if (spec.group !== group) {
      group = spec.group;
      const head = document.createElement("div");
      head.className = "tunegroup";
      head.textContent = group;
      box.appendChild(head);
    }
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML =
      `<div class="rowhead"><span class="name">${spec.key}</span>` +
      `<span class="value" data-for="${spec.key}"></span></div>` +
      `<input type="range" min="${spec.min}" max="${spec.max}" step="${spec.step}">` +
      `<div class="hint">${esc(spec.hint)}</div>`;
    const input = row.querySelector("input");
    input.value = BLOB[spec.key];
    input.addEventListener("input", () => {
      const v = tuneClamp(spec, input.value);
      if (v === null) return;
      BLOB[spec.key] = v;
      markSlider(spec, v);
      saveTuning();
      applyTuning();
    });
    box.appendChild(row);
    markSlider(spec, BLOB[spec.key]);
  });
}

function markSlider(spec, value) {
  const cell = document.querySelector(`#sliders .value[data-for="${spec.key}"]`);
  if (!cell) return;
  cell.textContent = tuneFormat(spec, value);
  cell.classList.toggle("changed", value !== TUNE_BASE[spec.key]);
}

// Geometry and style both live in BLOB, so one repaint covers either. The cache
// is keyed on positions, which have not moved, so it has to be dropped by hand.
function applyTuning() {
  if (!show.blobs || !recVis()) return;
  blobCache.clear();
  redrawBlobs();
}

function resetTuning() {
  SLIDERS.forEach(spec => { BLOB[spec.key] = TUNE_BASE[spec.key]; });
  try { localStorage.removeItem(TUNE_STORE); } catch (err) { /* nothing to drop */ }
  buildSliders();
  applyTuning();
}

// The whole block, not only what moved: a config you paste should say what the
// page will do, without the reader holding the defaults in their head.
function tuningYaml() {
  const lines = ["viz:", "  blob:"];
  SLIDERS.forEach(spec => lines.push(`    ${spec.key}: ${tuneFormat(spec, BLOB[spec.key])}`));
  return lines.join("\n") + "\n";
}

function copyTuning(btn) {
  const text = tuningYaml();
  const done = ok => {
    btn.textContent = ok ? "Copied" : "Copy failed";
    setTimeout(() => { btn.textContent = "Copy as YAML"; }, 1400);
  };
  // A file:// page may have no clipboard API at all; the textarea route is the
  // old one and still works there.
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => done(true), () => done(fallbackCopy(text)));
    return;
  }
  done(fallbackCopy(text));
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
  ta.remove();
  return ok;
}

function initTuning() {
  const cfg = (DATA.settings && DATA.settings.blob) || {};
  SLIDERS.forEach(spec => {
    const fromConfig = tuneClamp(spec, cfg[spec.key]);
    TUNE_BASE[spec.key] = fromConfig === null ? BLOB[spec.key] : fromConfig;
    BLOB[spec.key] = TUNE_BASE[spec.key];
  });
  const saved = storedTuning();
  SLIDERS.forEach(spec => {
    const v = tuneClamp(spec, saved[spec.key]);
    if (v !== null) BLOB[spec.key] = v;
  });
  buildSliders();
  document.getElementById("tuneReset").addEventListener("click", resetTuning);
  const copy = document.getElementById("tuneCopy");
  copy.addEventListener("click", () => copyTuning(copy));
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
    // One opacity knob, plus the 4-point lift dark mode has always had: the same
    // fill reads weaker on a dark page than on a light one.
    const path = el("path", { d, fill: color,
      "fill-opacity": (BLOB.fillOpacity + (theme === "dark" ? 4 : 0)) / 100,
      stroke: color, "stroke-opacity": 0.45, "stroke-width": BLOB.strokeWidth,
      "data-state": h.state, "pointer-events": "none" });
    const tip = el("title");
    tip.textContent = bySlug[h.state].node.title + " (" + h.state + ")";
    path.appendChild(tip);
    const lp = lps[h.state];
    const label = el("text", { x: lp.x, y: lp.y, class: "bloblabel",
      "data-slug": h.state, cursor: "pointer", "font-family": MONO,
      "font-size": BLOB.labelSize, "text-anchor": "middle", fill: color }, h.state);
    layer.appendChild(path);
    layer.appendChild(label);
    blobEls[h.state] = { path, label };
  });
  return layer;
}

// Repaint the blobs one moved node can have changed: the ones it belongs to,
// and the ones it is now close enough to push away from as a non-member. Two
// blobs on a busy frame, against fourteen for a full redraw.
function updateBlobs(slug) {
  const pos = posFor(), H = hyperedges();
  const touched = new Set(H.memberOf[slug] || []);
  blobsTouching(slug, pos).forEach(st => touched.add(st));
  touched.forEach(st => {
    const be = blobEls[st];
    if (be && H.index[st]) be.path.setAttribute("d", blobPathFor(H.index[st], pos));
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
  // Tags narrow by OR within the selection: clicking two clusters asks for either,
  // which is what a reader clicking a second chip means. Search narrows on top (AND).
  if (activeTags.size) {
    const tags = node.tags || [];
    if (!tags.some(t => activeTags.has(t))) return false;
  }
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
  // Tags last, and in their own colours: they are annotation beside the protocol
  // facts above, not another one of them.
  (node.tags || []).forEach(name => {
    const def = (DATA.tag_defs || []).find(d => d.name === name);
    chips += `<span class="chip" style="background:${esc((def && def.bg_color) || "")};` +
             `color:${esc((def && def.text_color) || "")}">${esc(name)}</span>`;
  });
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
      <tr><td>high-water mark</td><td>${(DATA.reconciliation.high_water_frontier || []).length
        ? DATA.reconciliation.high_water_frontier.map(slugLink).join(", ") : "—"}</td></tr>
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
    <h3>Views</h3>
    <table class="stats">
      <tr><td><b>Timeline</b></td><td>what happened, in order — <code>git log</code>
        lanes with time along x. A rule marks the high-water mark; the tinted band
        past it is work not yet reconciled.</td></tr>
      <tr><td><b>Frontier</b></td><td>what is true now — a status board, broken and
        blocked and open first. An empty column keeps a labelled rail, because
        "nothing is broken" is an answer.</td></tr>
      <tr><td><b>Provenance</b></td><td>what each claim rests on — both graphs side
        by side. Cross-links start hidden; select or hover a node to see its own,
        or switch Links to <i>All</i> for one bundled ribbon per claim.</td></tr>
      <tr><td><b>Clusters</b></td><td>which work belongs to the same claim — each
        claim's record set as a blob, with a corridor holding far-apart members
        together and non-members pushing the outline away.</td></tr>
      <tr><td><b>Everything</b></td><td>the default: both graphs, blobs, and every
        cross-link at once. Busy on purpose — it shows what is there before it
        shows you a slice of it, and the four views above are one key away.</td></tr>
    </table>
    <h3>Marks worth knowing</h3>
    <table class="stats">
      <tr><td>lane rules</td><td>concurrent threads of work in the Timeline</td></tr>
      <tr><td>puck</td><td>a claim collapsed to one body; the number is how many
        record nodes it holds. Open the claim to expand it again.</td></tr>
      <tr><td>Window</td><td>keeps only the most recent N record nodes, so a long
        history shrinks the drawing instead of scrolling past it</td></tr>
    </table>
    <p class="hint"><b>Keys</b> — <code>1</code>–<code>5</code> pick a view ·
    <code>/</code> search · <code>f</code> fit · <code>Esc</code> deselect.
    Scroll to zoom · drag the background to pan · drag nodes to rearrange ·
    click a node for its full content · drag the divider to resize this panel.
    <b>Arrange</b> moves the whole drawing — spread, tighten, relax from where
    things are, shuffle to another seeded arrangement, or reset. <b>Blob tuning</b>
    edits the outline geometry live and copies it as a <code>viz:</code> block for
    <code>.hypergraph/config.yml</code>.
    No view shrinks below 0.45 — one that does not fit scrolls instead. The
    layout is deterministic: the same graph always draws the same way. Use the
    export menu for SVG or PDF.</p>`;
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
let drag = null, blobRaf = 0;
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
    // Keep the real outline while dragging — a blob that turns into a big hull
    // the moment you touch it reads as breakage. `blobDragging` now only picks
    // the coarse grid (BLOB.dragCoarsen), and one repaint per animation frame
    // means a fast pointer costs frames, not recomputes.
    if (show.blobs && recVis()) {
      blobDragging = true;
      if (!blobRaf) blobRaf = requestAnimationFrame(() => {
        blobRaf = 0;
        posEpoch++;          // positions moved in place; invalidate what caches them
        updateBlobs(drag ? drag.slug : null);
      });
    }
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
  if (blobRaf) { cancelAnimationFrame(blobRaf); blobRaf = 0; }
  drag = null;
  blobDragging = false;
  // Full quality, once, from the final positions.
  if (wasDragging && show.blobs && recVis()) { posEpoch++; redrawBlobs(); }
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
// Keyboard: 1-5 pick a view, / searches, f fits, Esc clears. Nothing fires while
// you are typing, and nothing shadows a browser shortcut (no modifiers here).
const VIEW_KEYS = ["timeline", "frontier", "provenance", "clusters", "everything"];
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    if (document.activeElement === searchBox) searchBox.blur();
    deselect();
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const typing = document.activeElement === searchBox;
  if (e.key === "/" && !typing) { e.preventDefault(); searchBox.focus(); return; }
  if (typing) return;
  const view = VIEW_KEYS[Number(e.key) - 1];
  if (view) { applyPreset(view); return; }
  if (e.key === "f" || e.key === "F") fit();
});

const searchBox = document.getElementById("search");
searchBox.addEventListener("input", e => {
  query = e.target.value.trim().toLowerCase();
  updateDim();
});

// Tag chips. A filter and nothing else: a tag is annotation, no invariant reads
// one, so it must never change how a node is *drawn* — that would give a tag the
// standing in the picture that it does not have in the protocol.
function buildTagChips() {
  const box = document.getElementById("tagchips");
  const defs = DATA.tag_defs || [];
  if (!defs.length) { box.hidden = true; return; }   // a repo that tags nothing
  box.hidden = false;
  box.innerHTML = defs.map(d =>
    `<button data-tag="${esc(d.name)}" title="${d.count} node${d.count === 1 ? "" : "s"}"` +
    ` style="background:${esc(d.bg_color)};color:${esc(d.text_color)}">` +
    `${esc(d.name)}<i>${d.count}</i></button>`).join("");
  box.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => {
    const name = btn.dataset.tag;
    if (activeTags.has(name)) activeTags.delete(name); else activeTags.add(name);
    btn.classList.toggle("active", activeTags.has(name));
    updateDim();
  }));
}

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
  // Spread, Tighten and Reset mean something in any layout. Shuffle and Relax
  // are the force sim's own, so outside it they are hidden rather than dimmed.
  const force = show.layout === "force";
  document.getElementById("arShuffle").hidden = !force;
  document.getElementById("arRelax").hidden = !force;
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

// ------------------------------------------------------------------ arrange
// Five ways to move the whole drawing, none of them random. Spread and Tighten
// scale about the centroid, so the structure is preserved exactly and only the
// breathing room changes. Relax settles from where things are now, keeping your
// drags. Shuffle asks the layout for another arrangement, by seed. Reset throws
// the current arrangement away and recomputes it.
const ARRANGE_STEP = 1.15;

function scaleLayout(factor) {
  const pos = posFor(), slugs = Object.keys(pos);
  if (!slugs.length) return;
  let cx = 0, cy = 0;
  slugs.forEach(s => { cx += pos[s].x; cy += pos[s].y; });
  cx /= slugs.length; cy /= slugs.length;
  slugs.forEach(s => {
    pos[s].x = cx + (pos[s].x - cx) * factor;
    pos[s].y = cy + (pos[s].y - cy) * factor;
  });
}

// Every arrangement change moves nodes in place, which no other cache key sees.
function arranged() {
  posEpoch++;
  renderAll();
}

const ARRANGE = {
  arSpread:  () => { scaleLayout(ARRANGE_STEP); arranged(); },
  arTighten: () => { scaleLayout(1 / ARRANGE_STEP); arranged(); },
  arRelax:   () => { relaxLayout(posFor()); arranged(); },
  // The seed is part of layoutKey, so each shuffle's arrangement is kept under
  // its own key, drags and all. Shuffle only walks forward; Reset puts the seed
  // back to 0, which is what makes any earlier one reachable again — shuffle
  // twice from there and you get exactly the arrangement you had.
  arShuffle: () => { forceSeed++; posEpoch++; rerender(); },
  arReset:   () => {
    forceSeed = 0;
    const k = layoutKey();
    delete positions[k];
    delete fitDone[k];
    posEpoch++;
    rerender();
  },
};
document.getElementById("arrange").addEventListener("click", e => {
  const btn = e.target.closest("button");
  if (btn && ARRANGE[btn.id]) ARRANGE[btn.id]();
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
// The exported SVG is standalone: every mark is styled by attribute, not by a
// stylesheet, so it survives being dropped into a document or an editor.
function exportSvg() {
  // worldBounds already accounts for each layout's own scenery — lane rules and
  // the date gutter, board column headers, the two-column captions — so every
  // view exports whole instead of only the four that predate them.
  const { minX, minY, maxX, maxY } = worldBounds();
  if (minX > maxX) return null;
  // A file has no zoom, so it gets full detail regardless of the current one.
  const k = tfFor().k;
  applyLod(Infinity);
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
  applyLod(k);
  return new XMLSerializer().serializeToString(out);
}

document.getElementById("svgBtn").addEventListener("click", () => {
  exportMenu.hidden = true;
  const text = exportSvg();
  if (!text) return;
  const blob = new Blob([text], { type: "image/svg+xml" });
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
          (data.reconciliation.high_water_frontier || []).join(",")].join("|");
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
// DATA.settings is deliberately *not* swapped: it carries the config's blob
// tuning, which belongs to the page rather than to the graph. A refresh that
// reset it would pull a slider out from under you mid-adjustment.
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
// Deep links: #timeline | #frontier | #provenance | #clusters | #everything
// selects that view (the pre-rename hashes #record #state #combo #combination
// #hyper still work, see VIEW_ALIASES); #<slug> jumps to a node.
document.body.dataset.theme = theme;
applySide();
registerPucks();   // synthetic entries for collapsed hyperedges
buildTagChips();   // no-op on a graph that carries no tags
initTuning();      // BLOB gets its config/stored values before anything is drawn
const boot = decodeURIComponent(location.hash.slice(1));
const bootView = VIEW_ALIASES[boot] || boot;
// Default to everything on: show what is in the graph first, then let the four
// focused views take things away. One click, or one number key, gets there.
applyPreset(PRESETS[bootView] ? bootView : "everything");
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
    parser.add_argument("--version", action="version",
                        version=f"hypergraph-protocol {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="validate protocol invariants over graph exports")
    p_check.add_argument("--record", type=Path, required=True, help="record-graph export JSON")
    p_check.add_argument("--state", type=Path, required=True, help="state-graph export JSON")
    p_check.add_argument("--config", type=Path, help=".hypergraph/config.yml")
    p_check.add_argument("--since", metavar="REF",
                         help="also fail when REF...HEAD changes files but adds no record "
                              "node (I1 across a branch — for pull-request CI)")
    p_check.set_defaults(func=cmd_check)

    p_hwm = sub.add_parser("hwm", help="report the reconciliation frontier (read-only)")
    p_hwm.add_argument("--record", type=Path, required=True, help="record-graph export JSON")
    p_hwm.add_argument("--state", type=Path, required=True, help="state-graph export JSON")
    p_hwm.add_argument("--config", type=Path, help=".hypergraph/config.yml")
    p_hwm.add_argument("--suggest", action="store_true",
                       help="print the frontier a pre-0.0.5 graph needs after upgrading")
    p_hwm.set_defaults(func=cmd_hwm)

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
    p_import.add_argument("--force", action="store_true",
                          help="overwrite differing node files. Note: since tags "
                               "travel, re-importing the same export into a repo "
                               "imported by an older release changes the rendered "
                               "bytes and needs this flag — loudly and correctly")
    p_import.add_argument("--no-tags", action="store_true",
                          help="do not carry the source graph's tags (the vocabulary "
                               "or the per-node assignments)")
    p_import.add_argument("--tags-file", type=Path, metavar="PATH",
                          help=f"where to write the vocabulary (default: {DEFAULT_TAGS_FILE})")
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
    p_new.add_argument("--tag", action="append", metavar="NAME",
                       help="a tag name for this node (repeatable). Annotation only — "
                            "no invariant reads a tag, and a claim that lives only as "
                            "a tag is invisible to the protocol")
    p_new.add_argument("--tags-file", type=Path, metavar="PATH",
                       help=f"tag vocabulary (default: {DEFAULT_TAGS_FILE})")
    p_new.set_defaults(func=cmd_new)

    p_tags = sub.add_parser(
        "tags", help="show or edit this project's tag vocabulary (.hypergraph/tags.yml)")
    p_tags.add_argument("action", choices=["list", "add", "rm"],
                        help="list: the vocabulary plus usage counts. add/rm: declare "
                             "or undeclare a name — never hand-edit the file")
    p_tags.add_argument("name", nargs="?", help="add/rm: the tag name")
    graph_args(p_tags)
    p_tags.add_argument("--tags-file", type=Path, metavar="PATH",
                        help=f"vocabulary path (default: {DEFAULT_TAGS_FILE})")
    p_tags.add_argument("--graph", choices=list(GRAPH_KINDS), default="record",
                        help="which graph's vocabulary (default: record) — "
                             "`tags:create` is per graph root and there are two")
    p_tags.add_argument("--bg-color", help="add: chip background (default: from the name's digest)")
    p_tags.add_argument("--text-color", help="add: chip text colour")
    p_tags.add_argument("--one-only", action="store_true",
                        help="add: at most one node may carry this tag (a pointer tag)")
    p_tags.add_argument("--track-history", action="store_true",
                        help="add: ask the backend to keep the pointer's move history. "
                             "Declarative input to `tags:create` only — this protocol "
                             "does not model the chain; a move with a reason is a "
                             "record node")
    p_tags.add_argument("--force", action="store_true",
                        help="rm: undeclare even though nodes still carry the name")
    p_tags.add_argument("--json", action="store_true", help="list: machine-readable output")
    p_tags.set_defaults(func=cmd_tags)

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
    p_skills.add_argument("--link", action="store_true",
                          help="symlink instead of copy, so editing the source edits "
                               "the live skill (dev checkouts only — a copy is what "
                               "an installed wheel should hand out)")
    p_skills.set_defaults(func=cmd_skills)

    p_upgrade = sub.add_parser(
        "upgrade", help="refresh an adopted repo's copies (skills, AGENTS.md block, "
                        "workflows) to this CLI's release")
    p_upgrade.add_argument("--repo", type=Path, help="repo root (default: cwd)")
    p_upgrade.add_argument("--config", type=Path, help=".hypergraph/config.yml")
    p_upgrade.add_argument("--user", action="store_true",
                           help="refresh the skills in ~/.claude/skills instead of "
                                "./.claude/skills (mirrors `skills install --user`)")
    p_upgrade.add_argument("--workflows", action="store_true",
                           help="also overwrite drifted .github/workflows/hypergraph-*"
                                " (default: report them — adopters customize these)")
    p_upgrade.add_argument("--agents-block", action="store_true",
                           help="also overwrite an AGENTS.md block carrying local edits"
                                " (default: report it — adopt writes per-project"
                                " content inside the sentinels)")
    p_upgrade.add_argument("--dry-run", action="store_true",
                           help="print what would change and write nothing")
    p_upgrade.set_defaults(func=cmd_upgrade)


    # ---- optional one-way mirror: backend/mirror.md. Nothing below here runs on a
    # project whose config declares no `mirror:` — `push` exits 0 as a no-op, which
    # is what lets the reconcile skill call it unconditionally.
    def mirror_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--transport", choices=["auto", "cli", "rest"], default="auto",
                       help="auto: the `flywheel` CLI if present, else REST (default)")
        p.add_argument("--rate", type=float, metavar="PER_MIN", default=100.0,
                       help="minimum write pacing (default 100/min vs a 120/min ceiling)")
        p.add_argument("--journal", type=Path, metavar="FILE",
                       help="crash journal path (default: <cache_dir>/push-journal.jsonl)")
        p.add_argument("--allow-any-branch", action="store_true",
                       help="publish from a branch other than `publish_branch:` (default: main)")
        p.add_argument("--require-mirror", action="store_true",
                       help="fail instead of standing down when the mirror cannot be "
                            "published — for CI, where a silent no-op is a broken deploy")

    p_push = sub.add_parser("push", help="publish committed node files to the mirror")
    graph_args(p_push)
    mirror_args(p_push)
    p_push.add_argument("--dry-run", action="store_true",
                        help="print what would be written and stop")
    p_push.add_argument("--batch", type=int, default=20, metavar="N",
                        help="fold results into the node files every N writes (default 20)")
    p_push.add_argument("--limit", type=int, metavar="N",
                        help="execute at most N ops this run (resumable)")
    p_push.add_argument("--yes", action="store_true",
                        help=f"proceed without confirming a plan above {PUSH_CREATE_WARN} creates")
    p_push.add_argument("--no-legend", action="store_true",
                        help="skip refreshing the mirror-only slug legend")
    p_push.add_argument("--no-tags", action="store_true",
                        help="skip the tag vocabulary and per-node assignments")
    p_push.add_argument("--no-verify", action="store_true",
                        help="skip the drift check after publishing")
    p_push.add_argument("--skip-preflight", action="store_true",
                        help="skip the reachability/roots/account checks")
    p_push.add_argument("--plan", action="store_true",
                        help="emit the ordered push plan and exit — network-free, the "
                             "fallback for machines without the CLI binary")
    p_push.add_argument("--record-result", type=Path, metavar="RESULTS.JSON",
                        help="fold executed-push ids back into the node frontmatter")
    p_push.add_argument("--verify", action="store_true",
                        help="read-only drift check against a fresh mirror export (exit 1 on drift)")
    p_push.add_argument("--against", type=Path, metavar="EXPORT.JSON",
                        help="the mirror export to verify against")
    p_push.add_argument("--strict", action="store_true",
                        help="--verify: also compare title, parents and tags. Off by "
                             "default because each fires on a correct graph — mirror "
                             "root titles differ by doctrine and mirror parents are "
                             "mirror ids, which --strict maps before comparing")
    p_push.add_argument("--legend", action="store_true",
                        help="emit the mirror-only slug-legend node body")
    p_push.add_argument("--lineage", action="store_true",
                        help="emit the archive-lineage body for the mirror record root "
                             "(needs an `archive:` block in the config)")
    p_push.add_argument("-o", "--output", type=Path, help="plan output path (default: stdout)")
    p_push.set_defaults(func=cmd_push)

    p_sync = sub.add_parser("sync", help="export → render → check → push, in one step")
    graph_args(p_sync)
    mirror_args(p_sync)
    p_sync.add_argument("--out-dir", type=Path,
                        help=f"where to write the exports (default: {DEFAULT_CACHE_DIR})")
    p_sync.add_argument("--state-md", type=Path, help="STATE.md path (default: from config)")
    p_sync.add_argument("--no-push", action="store_true",
                        help="stop after export/render/check")
    p_sync.add_argument("--no-verify", action="store_true",
                        help="skip the drift check after publishing")
    p_sync.add_argument("--no-tags", action="store_true",
                        help="skip the tag vocabulary and per-node assignments")
    p_sync.add_argument("--skip-preflight", action="store_true")
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--batch", type=int, default=20, metavar="N")
    p_sync.add_argument("--yes", action="store_true")
    p_sync.set_defaults(func=cmd_sync)

    p_mirror = sub.add_parser("mirror", help="mirror diagnostics, roots and pulls")
    p_mirror.add_argument("action", choices=["doctor", "roots", "pull"],
                          help="doctor: preflight the mirror. roots: show or --mint "
                               "them. pull: export a hosted graph to importable JSON")
    graph_args(p_mirror)
    mirror_args(p_mirror)
    p_mirror.add_argument("--no-write-probe", action="store_true",
                          help="doctor: skip the write probe (scope is not otherwise "
                               "introspectable — a key can authenticate and still 403)")
    p_mirror.add_argument("--mint", action="store_true",
                          help="roots: mint both mirror roots and append them to config")
    p_mirror.add_argument("--force", action="store_true",
                          help="roots: re-mint even though `mirror_roots:` already exists")
    p_mirror.add_argument("--node-id", action="append", metavar="ID",
                          help="pull: record-graph anchor (repeatable)")
    p_mirror.add_argument("--record-node-id", action="append", metavar="ID",
                          help="pull: record-graph anchor (repeatable)")
    p_mirror.add_argument("--state-node-id", action="append", metavar="ID",
                          help="pull: state-graph anchor (repeatable)")
    p_mirror.add_argument("--out-dir", type=Path,
                          help="pull: where to write record.json/state.json")
    p_mirror.set_defaults(func=cmd_mirror)

    def heal_args(p: argparse.ArgumentParser) -> None:
        # Dry run is the DEFAULT here and opt-in everywhere else in this CLI. Heal is
        # human-initiated, sits in no commit flow, rewrites the whole graph at once,
        # and spends mirror writes that cannot be un-spent — `upgrade`'s effects are
        # all `git checkout`-reversible and heal's are not.
        p.add_argument("--apply", action="store_true",
                       help="actually write. Without it heal detects and reports only")
        p.add_argument("--all", action="store_true", help="every applicable healer")
        p.add_argument("--offline", action="store_true",
                       help="repo only: no mirror reads and no mirror writes")
        p.add_argument("--source", type=Path, metavar="PATH",
                       help="the source graph export to repair against (default: the "
                            "cached mirror pull, else a live read-only export)")
        p.add_argument("--repo", type=Path, help="repo root (default: cwd)")
        p.add_argument("--allow-dirty", action="store_true",
                       help="heal even with uncommitted changes under the graph dir")
        p.add_argument("--limit", type=int, metavar="N",
                       help="address at most N finding(s); the rest are reported as "
                            "left alone, never silently dropped")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument("--fail-on-drift", action="store_true",
                       help="exit 1 when drift is found. Off by default: unhealed "
                            "drift is a capability that landed after your adoption, "
                            "not a broken invariant")
        p.add_argument("--yes", action="store_true",
                       help="proceed without confirming a large repair")

    p_heal = sub.add_parser(
        "heal", help="carry a capability backwards into a repo that adopted before it "
                     "existed (detect-only unless --apply)")
    p_heal.add_argument("healer", nargs="*",
                        help=f"which repair(s) to run (have: "
                             f"{', '.join(h.name for h in HEALERS)}). "
                             "With none named, lists the registry and exits 0")
    graph_args(p_heal)
    mirror_args(p_heal)
    heal_args(p_heal)
    p_heal.set_defaults(func=cmd_heal)

    # ---- adoption: compute the facts an adopting agent would otherwise gather by
    # hand. Never the claims — see the module comment above `cmd_adopt`.
    p_adopt = sub.add_parser("adopt", help="survey a repo, pull a legacy graph, "
                                           "mint roots, resolve id prefixes")
    graph_args(p_adopt)
    mirror_args(p_adopt)
    p_adopt.add_argument("--repo", type=Path, help="repo root (default: cwd)")
    p_adopt.add_argument("--json", action="store_true", help="machine-readable output")
    p_adopt.add_argument("--survey", action="store_true",
                         help="git shape, timeline signals, churn, docs, tests, and "
                              "AGENTS.md/CLAUDE.md symlink status")
    p_adopt.add_argument("--pull", action="store_true",
                         help="export a legacy hosted graph (same as `mirror pull`)")
    p_adopt.add_argument("--init", action="store_true",
                         help="mint (or adopt) both graph roots and write a valid config")
    p_adopt.add_argument("--marker", metavar="SLUG",
                         help="record the adoption epoch, after checking it resolves")
    p_adopt.add_argument("--resolve-prefixes", action="store_true",
                         help="map raw node-id prefixes cited in tracked docs to slugs")
    p_adopt.add_argument("--against", type=Path, metavar="EXPORT.JSON",
                         help="--resolve-prefixes: the legacy export to resolve against")
    p_adopt.add_argument("--project", help="--init: project name (default: repo dir name)")
    p_adopt.add_argument("--record-body", type=Path, help="--init: record root body file")
    p_adopt.add_argument("--state-body", type=Path, help="--init: state root body file")
    p_adopt.add_argument("--force", action="store_true",
                         help="--init: overwrite an existing config")
    p_adopt.add_argument("--out-dir", type=Path, help="--pull: where to write the exports")
    p_adopt.add_argument("--node-id", action="append", metavar="ID")
    p_adopt.add_argument("--record-node-id", action="append", metavar="ID")
    p_adopt.add_argument("--state-node-id", action="append", metavar="ID")
    p_adopt.set_defaults(func=cmd_adopt)

    args = parser.parse_args(argv)
    if getattr(args, "command", None) == "import" and not (args.record or args.state):
        parser.error("import needs --record and/or --state")
    if getattr(args, "command", None) == "tags" and args.action in ("add", "rm") \
            and not args.name:
        parser.error(f"tags {args.action} needs a tag name")
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
