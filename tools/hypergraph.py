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

check exits 1 on any I2/I4/I5/I6/I7 violation (see SPEC.md). Warnings (I1 proxies)
and info lines never affect the exit code.

Visualization lives outside this file: external tooling (hypergraph-viz, built on
excaligraph) consumes the very same JSON exports. `viz` remains as a signpost only.

The local (git-native) backend keeps both graphs as committed markdown files under
.hypergraph/graph/{record,state}/<slug>.md and produces the very same export JSON
(backend/local-adapter.md):

    hypergraph.py export [--config config.yml] [--graph-dir D] [--out-dir cache/]
    hypergraph.py import --record record.json --state state.json [--graph-dir D]
    hypergraph.py new record|state --title T --body body.md [--tag NAME] ...
    hypergraph.py update SLUG --body new.md --expect <sha256> --reconcile
    hypergraph.py tags list|add|rm [NAME]
    hypergraph.py skills install [--user | --link | --target DIR]
    hypergraph.py upgrade --graph [tags] [--apply] [--offline]

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

`upgrade` has two halves with opposite polarities, and `--graph` names the boundary.
Bare `upgrade` refreshes this project's *copies* of shipped files (skills, AGENTS.md
block, workflows) and writes by default — every effect is `git checkout`-reversible.
`upgrade --graph` repairs *graph content*: a registry of typed repairs that carry a
capability backwards into a repo that adopted before it existed. It rewrites node
files and may spend mirror writes that cannot be un-spent, so it is **detect-only
until `--apply`** — the one inverted default in this file. `heal` survives as a
deprecated alias for the 0.9.x series.
"""
from __future__ import annotations

# Kept in step with pyproject.toml's `version` by tests/test_packaging.py. It is
# duplicated rather than read from the installed metadata because this file also
# runs directly as a `uv run` script, where no distribution metadata exists.
__version__ = "0.0.9"

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
    artifacts: list[str] = field(default_factory=list)

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
            # Strings only, and for a sharper reason than the `tags`/`tag_ids` note
            # above. A mirror export also has an `artifacts` key, and its entries are
            # attachment **objects** — ids, titles, urls for bytes the host holds.
            # Ours are repo-relative *paths*, which is op 9's whole identity rule
            # (backend/INTERFACE.md). Reading one as the other would put a store's
            # bookkeeping where a path belongs, and every consumer downstream would
            # believe it.
            artifacts=[a for a in (raw.get("artifacts") or [])
                       if isinstance(a, str)] if isinstance(
                           raw.get("artifacts"), list) else [],
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


def check_artifact_placement(state: Graph, report: Report) -> None:
    """`artifacts:` on a state node is a violation (SPEC: Evidence lives on record nodes).

    Evidence hangs off the record node whose work produced it. A state node claiming
    its own would give the same file two homes — and the state graph is rewritten on
    every reconcile, so that home has no stable owner. The one-hop path already
    exists and is the right one: `## Provenance` cites the record node, and the
    record node enumerates the files."""
    for node in state.nodes.values():
        if not node.artifacts:
            continue
        report.add("violation", "-", node.ref,
                   f"state node declares `artifacts:` ({len(node.artifacts)} path(s)). "
                   "Evidence lives on the record node whose work produced it — cite "
                   "that node from `## Provenance` and attach the files there.")


def git_tracked_paths(repo_root: Path) -> set[str] | None:
    """Every path git tracks under `repo_root`, in one call. None when it cannot say.

    One `git ls-files` for the whole graph, never one per artifact: the untracked
    report is a single collapsed line, and a per-file `git` invocation over a few
    hundred paths is the kind of cost nobody notices until a large repo adopts.
    Returns None rather than an empty set outside a checkout, because "git tracks
    nothing here" would flag every artifact in the project."""
    out = _git(Path(repo_root), "ls-files", "-z")
    if not out:
        return None
    return {p for p in out.split("\0") if p}


def check_artifact_paths(record: Graph, config: dict, report: Report, *,
                         repo_root: Path | str | None = None) -> None:
    """Do the declared evidence paths still point at something? Warnings and infos.

    **Never a violation, and `check` still exits 0.** An artifact can legitimately be
    a gitignored 40 GB dataset that a fresh clone was never going to have; failing CI
    over its absence would make the feature useless for exactly the evidence it
    exists to hold. What this catches is the other case — a `git mv` that left the
    pointer behind, or a spelling that only resolves on a case-insensitive
    filesystem.

    Silent when no node declares an artifact: a project that never uses this hears
    nothing at all, the same bargain `check_tag_vocabulary` makes."""
    declared = [node for node in record.nodes.values() if node.artifacts]
    if not declared:
        return
    root = Path(repo_root) if repo_root is not None else repo_root_for(
        config, Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR))
    tracked = git_tracked_paths(root)
    untracked: list[str] = []
    for node in sorted(declared, key=lambda n: n.ref):
        seen: set[str] = set()
        for raw in node.artifacts:
            stored, abs_path, outside = read_artifact_path(root, raw)
            if stored in seen:
                report.add("warning", "-", node.ref,
                           f"artifact `{stored}` is listed twice")
                continue
            seen.add(stored)
            if outside:
                report.add("warning", "-", node.ref,
                           f"artifact `{raw}` resolves outside the repo (`{stored}`) — "
                           "it cannot survive a clone, and `push` refuses to upload it")
                continue
            if not abs_path.exists():
                report.add("warning", "-", node.ref,
                           f"artifact `{stored}` is not in the working tree. If the "
                           "file moved, `hypergraph artifacts mv` repoints the record; "
                           "if it is gitignored, this is expected on a fresh clone.")
                continue
            if abs_path.is_symlink():
                import os  # deferred, matching the rest of this file's os usage

                target = Path(os.path.realpath(str(abs_path)))
                try:
                    target.relative_to(Path(os.path.realpath(str(root))))
                except ValueError:
                    report.add("info", "-", node.ref,
                               f"artifact `{stored}` is a symlink leaving the repo "
                               f"({target}) — the pointer travels, the bytes do not")
            if miscased := artifact_case_mismatch(abs_path):
                report.add("warning", "-", node.ref,
                           f"artifact `{stored}` differs from the on-disk spelling "
                           f"({miscased}) — this resolves here and fails on a "
                           "case-sensitive filesystem such as Linux CI")
            if tracked is not None and stored not in tracked:
                untracked.append(f"{node.ref}: {stored}")
    if untracked:
        # One collapsed line, never one per file. Untracked is a legitimate choice
        # (decision 6: the agent decides what gets committed) — this is a note about
        # where the only copy will live, not a complaint.
        sample = ", ".join(untracked[:3]) + ("…" if len(untracked) > 3 else "")
        report.add("info", "-", "artifacts",
                   f"{len(untracked)} artifact(s) are not tracked by git ({sample}). "
                   "They upload normally; the mirror will be the only published copy.")


def run_check(record_path: Path, state_path: Path, config: dict | None = None,
              *, config_given: bool | None = None,
              repo_root: Path | str | None = None) -> Report:
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
        # Gated with the vocabulary warning and for the same reason: it reads files
        # outside the export, so it needs to know where the project actually lives.
        check_artifact_paths(record, config, report, repo_root=repo_root)
    check_conflict_markers(record, report)
    check_conflict_markers(state, report)
    check_artifact_placement(state, report)
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
    # `getattr`, not `args.repo`: `cmd_sync` hand-builds this Namespace, and a
    # required attribute added here would break it silently at the next release.
    report = run_check(args.record, args.state, config,
                       config_given=args.config is not None,
                       repo_root=getattr(args, "repo", None))
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
# Visualization moved out of core. External tooling (hypergraph-viz, built on
# excaligraph) consumes the same JSON exports as `check` and `render`; the stub
# below is a signpost, not a capability.


def cmd_viz(args: argparse.Namespace) -> int:
    print("viz moved out of hypergraph-protocol core.", file=sys.stderr)
    print("Visualization consumes the JSON exports (.hypergraph/cache/*.json):", file=sys.stderr)
    print("see hypergraph-viz (excaligraph-based) — https://github.com/theo-kirby", file=sys.stderr)
    return 2


# ----------------------------------------------------------------- local backend
# The git-native adapter (backend/local-adapter.md): markdown files under
# .hypergraph/graph/{record,state}/<slug>.md are the source of truth, and `export`
# turns them into exactly the JSON that check/render already consume — so the
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
# The same gate, one noun over. An artifact upload is a mirror write *and* bytes
# leaving the machine, so both the count and the volume are worth stopping on —
# `--yes` says you meant it.
PUSH_ARTIFACT_WARN = 200
PUSH_ARTIFACT_BYTES_WARN = 256 * 1024 * 1024
# `tags` sits between `summary` and `origin`: it is annotation the author writes,
# not provenance bookkeeping a tool stamps. Omitted entirely when empty — writing
# `tags: []` into every node would rewrite every file in every adopting repo for
# nothing.
#
# `artifacts` follows it on the same reasoning and one step further: it is the last
# key an author writes, and the first whose value can be *wrong about the world* —
# every other key means whatever it says, while a path can stop pointing at anything.
# So it sits at the boundary, after the annotation an author owns and before the
# bookkeeping a tool stamps. Omitted when empty, for the same reason `tags` is.
FM_ORDER = ("node_id", "slug", "title", "created_at", "parents", "summary", "tags",
            "artifacts", "origin", "flywheel")
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
    def artifacts(self) -> list:
        """Declared evidence paths, **verbatim** — never normalized on read.

        `render_node_file` has to round-trip a node file byte-for-byte, so a
        normalization here would silently rewrite the author's spelling the next time
        anything touched the file. Entries are returned unconverted so
        `artifact_path_problems` can still see a non-string for what it is."""
        raw = self.meta.get("artifacts")
        if raw is None:
            return []
        return list(raw) if isinstance(raw, list) else [raw]

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
        # Shape only, and deliberately *not* the record-only rule: a graph that
        # cannot load cannot be checked, so "artifacts on a state node" is a `check`
        # violation rather than a load failure.
        for problem in artifact_path_problems(node.artifacts):
            raise LocalGraphError(f"{path}: {problem}")
        seen_ids[node.node_id] = str(path)
        nodes[node.slug] = node
    return nodes


def local_graph(nodes: dict[str, LocalNode], kind: str) -> Graph:
    """Resolve parent *slugs* to node_ids and build the same Graph load_graph builds.

    Also the one place a **cycle** is caught. `push_plan` calls this before planning any
    write for exactly that reason: a cyclic parent set is not something the mirror
    should be asked to reproduce edge by edge, and by the time the host refuses the
    add, half of a two-edge move has already landed."""
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
                                 created_at=node.created_at, tags=node.tags,
                                 artifacts=[str(a) for a in node.artifacts])
    pending = {slug: {p for p in node.parents} for slug, node in nodes.items()}
    while pending:
        ready = [s for s, ps in pending.items() if not ps]
        if not ready:
            raise LocalGraphError(
                f"the {kind} graph has a parent cycle among "
                f"{', '.join(sorted(pending))} — no node in that set can be reached "
                "from a root")
        for slug in ready:
            pending.pop(slug)
        for remaining in pending.values():
            remaining.difference_update(ready)
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


# --------------------------------------------------------------------- artifacts
# INTERFACE op 9, implemented as **paths**. A record node's `artifacts:` list names
# files in this repo that its claims rest on: a training log, a plot, a captured
# transcript. The repo holds the bytes and stays canonical; a mirror may hold a copy,
# and a store's artifact id is bookkeeping, never identity.
#
# A repo-relative path is the portable identity, for the same reason a tag's *name*
# and a node's *slug* are: it survives a clone, a fork, a re-home, and a backend that
# mints its own ids. Input is cwd-relative (like `git add`); storage is
# repo-root-relative.
#
# Two rules that are easy to get backwards, so they are stated here once:
#
# 1. **Prose and the list are both required, and they are not the same thing.**
#    `## Method` / `## Result` is where a path is *explained*; `artifacts:` is where
#    it is *enumerated* so a tool can find it. Prose is the claim, the list is its
#    index. Neither replaces the other.
# 2. **A path outside the repo is stored and warned locally, and refused at upload.**
#    `artifacts: ../../.ssh/id_rsa` is a strange but legal thing to write in a
#    markdown file. It must never become an instruction to send that file anywhere,
#    so `resolve_artifacts` is the gate and it is a hard skip there.

ARTIFACT_PATH_MAX = 4096


def artifact_path_problems(paths: list) -> list[str]:
    """Structural complaints about artifact paths, in order. Empty list = fine.

    Shape only, and the split matters: **load time rejects what cannot be a path at
    all**, and `check` reports what is a path and is wrong about the world. A graph
    that cannot load cannot be checked, so nothing here touches the filesystem."""
    problems: list[str] = []
    for raw in paths:
        if not isinstance(raw, str):
            problems.append(
                f"artifact {raw!r} is not a string — `artifacts:` is a list of "
                "repo-relative paths. (A mirror export's `artifacts` are attachment "
                "objects; those are not what this key holds.)")
            continue
        if not raw.strip():
            problems.append("an `artifacts:` entry is empty")
            continue
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw):
            problems.append(f"artifact {raw!r} contains a control character")
        if len(raw) > ARTIFACT_PATH_MAX:
            problems.append(
                f"artifact {raw!r} is longer than {ARTIFACT_PATH_MAX} characters")
    return problems


def repo_root_for(config: dict, graph_dir: Path | None = None,
                  explicit: Path | str | None = None, *,
                  cwd: Path | str | None = None) -> Path:
    """What a stored artifact path is relative to: `--repo`, then git, then cwd.

    **Deliberately not a config key.** A `repo_root:` in config.yml is an absolute
    path committed into the repo; it goes stale the moment the checkout moves, and
    then every artifact path in the graph is wrong at once. Git already knows the
    answer and cannot go stale.

    Only ever called once at least one artifact is declared, so a project that never
    uses this pays nothing — not even a `git` invocation."""
    if explicit is not None:
        return Path(explicit)
    base = Path(cwd) if cwd is not None else Path.cwd()
    probes = [Path(graph_dir)] if graph_dir is not None else []
    probes.append(base)
    for probe in probes:
        if not probe.is_dir():
            continue
        top = _git(probe, "rev-parse", "--show-toplevel").strip()
        if top:
            return Path(top)
    return base


def normalize_artifact_path(raw: str, repo_root: Path | str, *,
                            cwd: Path | str | None = None) -> tuple[str, Path, bool]:
    """One authored path → (stored form, absolute path, is it outside the repo).

    Input is **cwd-relative**, exactly as `git add` is, because that is how a person
    or an agent types a path. Storage is **repo-root-relative** with POSIX
    separators, because that is the form that survives a clone.

    Containment is tried lexically first and only then through `realpath`. That order
    is the point: a symlink pointing at `/Volumes/big/runs` is the pointer the author
    meant, and resolving past it would rewrite their path into one that means
    something else on every other machine. The `realpath` fallback exists for the
    reverse case — macOS handing out `/tmp/...` for a repo that really lives at
    `/private/tmp/...` — where the two spellings are the same directory."""
    import os  # deferred, matching the rest of this file's os usage

    base = Path(cwd) if cwd is not None else Path.cwd()
    text = str(raw).strip().replace("\\", "/")
    given = Path(text)
    absolute = given.is_absolute()
    abs_path = Path(os.path.normpath(str(given if absolute else base / given)))
    root = Path(os.path.normpath(str(repo_root)))

    try:                                   # 1. lexical: follows nothing
        return abs_path.relative_to(root).as_posix(), abs_path, False
    except ValueError:
        pass
    try:                                   # 2. realpath: the /tmp → /private/tmp case
        real = Path(os.path.realpath(str(abs_path)))
        stored = real.relative_to(Path(os.path.realpath(str(root)))).as_posix()
        return stored, abs_path, False
    except (ValueError, OSError):
        pass
    # 3. outside the repo. An absolute input stays absolute — rewriting it as a pile
    # of `../` would hide how far outside it reaches. A relative input is re-expressed
    # from the repo root so the stored form still means one thing from one place.
    if absolute:
        return abs_path.as_posix(), abs_path, True
    return Path(os.path.relpath(str(abs_path), str(root))).as_posix(), abs_path, True


def read_artifact_path(repo_root: Path | str, stored: str) -> tuple[str, Path, bool]:
    """A path *read back* from frontmatter → (stored form, absolute path, outside).

    The read-side counterpart of `normalize_artifact_path`, and the distinction is
    not cosmetic: input *there* is cwd-relative because a person or an agent typed
    it, and input *here* is repo-relative because a node file holds it. Confusing the
    two makes `check` report every artifact as missing the moment it runs from a
    subdirectory."""
    return normalize_artifact_path(stored, repo_root, cwd=repo_root)


def artifact_is_outside(stored: str) -> bool:
    """Does a *stored* path point out of the repo? Read from the string alone."""
    text = str(stored)
    return (text.startswith("/") or text == ".." or text.startswith("../")
            or (len(text) > 1 and text[1] == ":"))


def artifact_abspath(repo_root: Path | str, stored: str) -> Path:
    """A stored path back to an absolute one. The inverse of `normalize_artifact_path`."""
    import os  # deferred, matching the rest of this file's os usage

    path = Path(str(stored))
    if path.is_absolute():
        return path
    return Path(os.path.normpath(str(Path(repo_root) / path)))


def artifact_case_mismatch(abs_path: Path | str) -> str | None:
    """The on-disk spelling when it differs from the given one only in case, else None.

    One `os.scandir` per path segment, and the only detector there is for
    works-on-macOS-fails-on-Linux-CI. `Plots/Loss.PNG` opens fine on a
    case-insensitive filesystem and is a dead pointer the moment the repo is cloned
    onto ext4 — which is where CI runs. A segment that is genuinely absent returns
    None: that is "missing", a different finding with different wording."""
    import os  # deferred, matching the rest of this file's os usage

    path = Path(abs_path)
    if not path.is_absolute():
        return None
    parts = path.parts
    current = Path(parts[0])
    rebuilt = [parts[0]]
    for segment in parts[1:]:
        try:
            names = {entry.name for entry in os.scandir(current)}
        except OSError:
            return None
        if segment in names:
            actual = segment
        else:
            actual = {n.lower(): n for n in names}.get(segment.lower())
            if actual is None:
                return None
        rebuilt.append(actual)
        current = current / actual
    real = str(Path(*rebuilt))
    return real if real != str(path) else None


def write_node_artifacts(node: LocalNode, paths: list[str]) -> bool:
    """Rewrite one node file's `artifacts:` list, and nothing else. → did it change?

    The narrowness is the guarantee. `LocalNode.sha256` hashes the **body**, so
    append-only is a property of the body — and this function cannot reach it, nor
    the title, nor the summary. Same boundary that already lets `push` stamp
    `flywheel:` and `heal tags` rewrite `tags:` on a record node the graph froze
    long ago."""
    meta = dict(node.meta)
    if paths:
        meta["artifacts"] = list(paths)
    else:
        meta.pop("artifacts", None)   # omitted when empty, exactly as `tags` is
    text = render_node_file(meta, node.content)
    if node.path.exists() and node.path.read_text() == text:
        return False
    node.path.write_text(text)
    node.meta = meta
    return True


def cmd_artifacts(args: argparse.Namespace) -> int:
    """`hypergraph artifacts {ls,add,rm,mv}` — the evidence index on a record node.

    **Editing `artifacts:` on a committed record node is legal, and this is where
    that reasoning lives permanently.** The record graph is append-only in its
    *bodies*: `LocalNode.sha256` hashes the body alone, `push` compares that hash,
    and `verify_mirror` rests on body byte-identity. Frontmatter that a tool owns has
    always been outside that — `push` stamps `flywheel:` into frozen nodes on every
    run, and `heal tags` rewrites `tags:` on nodes years old. The boundary that makes
    it true here is that this command never touches the title, the summary or the
    body. `hypergraph update` keeps refusing record nodes exactly as it did: a
    correction to a *claim* is still a new child node, never an edit.

    Why a command rather than hand-editing the file: the same reason `tags` is one.
    A path typed into YAML by hand is normalized against nothing, checked against
    nothing, and wrong in a way that only surfaces on someone else's machine."""
    config = load_config(args.config)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)
    nodes = {k: load_local_nodes(graph_dir, k, missing_ok=True) for k in GRAPH_KINDS}
    repo = repo_root_for(config, graph_dir, getattr(args, "repo", None))

    if args.action == "ls":
        return artifacts_ls(args, nodes, repo)

    slug = args.slug
    if slug in nodes["state"]:
        raise LocalGraphError(
            f"`{slug}` is a state node. Evidence attaches to the record node whose "
            "work produced it, never to a claim distilled from it — cite that record "
            "node from `## Provenance` and attach the files there (SPEC: Evidence "
            "lives on record nodes).")
    node = nodes["record"].get(slug)
    if node is None:
        raise LocalGraphError(f"`{slug}` is not a record node under {graph_dir}")
    current = list(node.artifacts)

    if args.action == "add":
        added: list[str] = []
        for raw in args.path:
            for problem in artifact_path_problems([raw]):
                raise LocalGraphError(problem)
            stored, abs_path, outside = normalize_artifact_path(raw, repo)
            if outside:
                print(f"warning   `{stored}` is outside the repo — it cannot survive "
                      "a clone, and `push` refuses to upload it", file=sys.stderr)
            elif not abs_path.exists() and not args.allow_missing:
                raise LocalGraphError(
                    f"{raw}: no such file. This is the last moment a typo is still "
                    "cheap to fix — pass --allow-missing if the file is genuinely "
                    "meant to arrive later.")
            elif not abs_path.exists():
                print(f"warning   `{stored}` is not in the working tree "
                      "(--allow-missing)", file=sys.stderr)
            if stored in current:
                print(f"artifacts: `{stored}` is already on `{slug}`")
                continue
            # **Appended in argument order, never sorted.** An evidence list has a
            # reading order — the log, then the plot it explains — and appending
            # keeps the git diff to the one line that changed. A deliberate
            # divergence from `new --tag`, which sorts: a tag set is a set, an
            # evidence list is a sequence.
            current.append(stored)
            added.append(stored)
        if write_node_artifacts(node, current):
            for stored in added:
                print(f"artifacts: `{stored}` attached to `{slug}`")
            if tracked := git_tracked_paths(repo):
                loose = [p for p in added if not artifact_is_outside(p)
                         and p not in tracked]
                if loose:
                    print(f"           {len(loose)} of these are untracked by git — "
                          "if you never commit them, the mirror becomes the only "
                          "published copy", file=sys.stderr)
        return 0

    if args.action == "rm":
        removed: list[str] = []
        for raw in args.path:
            stored, _abs, _outside = normalize_artifact_path(raw, repo)
            if stored not in current:
                # Loud, never a silent no-op: "rm reported success" and "the pointer
                # is gone" have to mean the same thing.
                raise LocalGraphError(
                    f"`{stored}` is not on `{slug}` (it declares: "
                    f"{', '.join(current) if current else 'nothing'}). Refusing to "
                    "report a no-op as a removal.")
            current.remove(stored)
            removed.append(stored)
        write_node_artifacts(node, current)
        for stored in removed:
            print(f"artifacts: `{stored}` removed from `{slug}`")
        print(f"           this detaches the pointer; it did not delete {removed[0]}")
        return 0

    if args.action == "mv":
        old_raw, new_raw = args.path
        for problem in artifact_path_problems([new_raw]):
            raise LocalGraphError(problem)
        old, _old_abs, _old_out = normalize_artifact_path(old_raw, repo)
        new, new_abs, new_outside = normalize_artifact_path(new_raw, repo)
        if old not in current:
            raise LocalGraphError(
                f"`{old}` is not on `{slug}` (it declares: "
                f"{', '.join(current) if current else 'nothing'})")
        if new in current:
            raise LocalGraphError(f"`{slug}` already declares `{new}`")
        # **In position.** That is the whole reason this exists rather than `rm`
        # followed by `add`: a rename must not reshuffle the reading order of the
        # evidence, and it must not turn a one-line diff into two.
        current[current.index(old)] = new
        write_node_artifacts(node, current)
        print(f"artifacts: `{old}` → `{new}` on `{slug}` (in position)")
        if new_outside:
            print(f"warning   `{new}` is outside the repo", file=sys.stderr)
        elif not new_abs.exists():
            print(f"warning   `{new}` is not in the working tree yet", file=sys.stderr)
        print("           this repoints the record only — it never touches the "
              "working tree. Run `git mv` yourself if the file has not moved.")
        return 0

    raise LocalGraphError(f"unknown artifacts action: {args.action}")


def artifacts_ls(args: argparse.Namespace, nodes: dict, repo: Path) -> int:
    """Every declared path, with what is wrong with it stated inline."""
    tracked = git_tracked_paths(repo)
    rows: list[dict] = []
    for slug, node in sorted(nodes["record"].items()):
        if args.slug and slug != args.slug:
            continue
        for raw in node.artifacts:
            stored, abs_path, outside = read_artifact_path(repo, raw)
            flags: list[str] = []
            if outside:
                flags.append("outside repo")
            elif not abs_path.exists():
                flags.append("missing")
            elif tracked is not None and stored not in tracked:
                flags.append("untracked")
            rows.append({"slug": slug, "path": stored, "flags": flags})
    if args.json:
        print(json.dumps({"repo_root": str(repo), "artifacts": rows}, indent=2,
                         ensure_ascii=False))
        return 0
    if not rows:
        where = f" on `{args.slug}`" if args.slug else ""
        print(f"no artifacts declared{where} — "
              "`hypergraph artifacts add <record-slug> <path>` starts one.")
        return 0
    for row in rows:
        marks = "".join(f"   [{flag}]" for flag in row["flags"])
        print(f"{row['slug']:<24} {row['path']}{marks}")
    return 0


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
            # Repo-relative paths, never a store's ids — a consumer of this export
            # can find the evidence with nothing but the repo (INTERFACE op 9).
            "artifacts": [str(a) for a in node.artifacts],
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


def prior_artifacts(path: Path) -> list:
    """The `artifacts:` an existing node file already carries, or [].

    Tolerant of an unreadable file on purpose: this is a *preservation* read, and
    failing the whole import over frontmatter that is about to be replaced anyway
    would be the wrong trade."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        meta, _body = split_frontmatter(path.read_text(), str(path))
    except (LocalGraphError, OSError):
        return []
    raw = meta.get("artifacts")
    return list(raw) if isinstance(raw, list) else []


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
            target = directory / f"{node.slug}.md"
            # Artifacts are local-only by construction: no export can supply them, so
            # `meta` — rebuilt from scratch on every import — has no way to know about
            # them. Without this a re-import with --force would silently delete an
            # author's entire evidence index, and `--force` is exactly what a
            # re-import after an upgrade needs.
            if prior := prior_artifacts(target):
                meta["artifacts"] = prior
            text = render_node_file(meta, node.content)
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

    if args.artifact:
        if kind != "record":
            raise LocalGraphError(
                "--artifact is record-only: evidence attaches to the record node "
                "whose work produced it, never to a state node (SPEC: Evidence lives "
                "on record nodes).")
        for problem in artifact_path_problems(list(args.artifact)):
            raise LocalGraphError(problem)
        repo = repo_root_for(config, graph_dir, getattr(args, "repo", None))
        stored_paths: list[str] = []
        for raw in args.artifact:
            stored, abs_path, outside = normalize_artifact_path(raw, repo)
            if stored in stored_paths:
                continue
            if outside:
                print(f"warning   artifact `{stored}` is outside the repo — it cannot "
                      "survive a clone, and `push` refuses to upload it",
                      file=sys.stderr)
            elif not abs_path.exists():
                # Warn, never refuse. A whole node has been composed and validated by
                # this line; throwing it away over a path would be absurd when
                # `hypergraph artifacts rm` fixes it a second later. `artifacts add`
                # refuses instead, because there the typo is all there is to lose.
                print(f"warning   artifact `{stored}` is not in the working tree",
                      file=sys.stderr)
            stored_paths.append(stored)
        meta["artifacts"] = stored_paths     # omitted when empty: see FM_ORDER
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

    # `--body` is optional so that a pure re-parent is not forced to rewrite a body it
    # is not changing; absent, the current content is kept verbatim.
    content = node.content if args.body is None else read_body(args.body)
    if not content.endswith("\n"):
        content += "\n"

    parents = update_parents(node, existing["state"], args)
    meta = dict(node.meta)
    if parents is not None:
        meta["parents"] = parents
    if args.title:
        meta["title"] = args.title
    if args.summary is not None:
        meta["summary"] = args.summary

    # Validate against the graph as it will be, not as it was: a re-parent changes
    # which node is the root, and `validate_node_content` reads that.
    node.meta.update(meta)
    record = local_graph(existing["record"], "record")
    state = local_graph(existing["state"], "state")
    is_root = not node.parents
    _report_and_raise(
        validate_node_content("state", node.slug, args.title or node.title, content,
                              node.created_at, record, state, is_root),
        f"update to state node `{args.slug}`")

    node.path.write_text(render_node_file(meta, content))
    moved = f", parents → {', '.join(parents) or 'root'}" if parents is not None else ""
    print(f"updated {node.path} ({node.sha256[:12]} → {body_sha256(content)[:12]}){moved}")
    return 0


def update_parents(node: LocalNode, state: dict, args: argparse.Namespace
                   ) -> list[str] | None:
    """The new parent slug list for `hypergraph update --parent/--root`, or None.

    None means "leave the parents alone" — the flag was not passed — and is distinct
    from `[]`, which is a node being promoted to root.

    **State nodes only.** `cmd_update` already refuses record nodes outright, and this
    is why that refusal is not a warning: record topology *is* causal history, and a
    parent edge there says "this happened after that". Distillation moves; history
    does not."""
    if not args.parent and not args.root:
        return None
    if args.parent and args.root:
        raise LocalGraphError("--root nodes are parentless; drop --parent or --root")
    parents = list(dict.fromkeys(args.parent or []))
    for parent in parents:
        if parent not in state:
            raise LocalGraphError(f"parent `{parent}` is not a state node")
        if parent == node.slug:
            raise LocalGraphError(f"`{node.slug}` cannot be its own parent")
    if args.root:
        others = [s for s, n in state.items() if not n.parents and s != node.slug]
        if others:
            raise LocalGraphError(
                f"the state graph already has a root: {', '.join(others)}. A second "
                "parentless node would split the graph, not re-home it.")
    # Walk up from each new parent: reaching this node means the edge would close a
    # cycle. `local_graph` resolves parent slugs but does not detect one, and a cycle
    # is unrecoverable through this command — the file that would fix it no longer
    # loads.
    seen, stack = set(), list(parents)
    while stack:
        current = stack.pop()
        if current == node.slug:
            raise LocalGraphError(
                f"parenting `{node.slug}` under `{', '.join(parents)}` would create a "
                f"cycle — `{node.slug}` is already an ancestor of it")
        if current in seen or current not in state:
            continue
        seen.add(current)
        stack.extend(state[current].parents)
    return parents


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
                 has_summary: bool = True, has_artifacts: bool = True,
                 node: object = None, raw: dict | None = None) -> dict:
    return {"ref": ref, "kind": kind, "key": key, "body": body, "title": title,
            "summary": summary, "revision": revision, "parents": parents,
            "tags": tags, "created_at": created_at, "node_id": node_id, "slug": slug,
            "artifacts": artifacts, "has_summary": has_summary,
            "has_artifacts": has_artifacts, "node": node, "raw": raw}


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
                # **Off the keyed block, never `node.artifacts`.** The comparator
                # compares artifact *id* sets, because that is what the other side —
                # a mirror or archive export — holds: attachment objects, not paths.
                # This block is the path→id translation table that makes the two
                # comparable with no mapping step anywhere. Wiring `node.artifacts`
                # here would diff repo paths against store ids and report every node
                # as drifted, forever.
                artifacts = list(block.get("artifacts") or [])
            elif key == "node_id":
                match, revision, artifacts = node.node_id or None, None, []
            elif key == "slug":
                match, revision, artifacts = node.slug or None, None, []
            else:
                raise LocalGraphError(f"unknown match key for a local side: {key!r}")
            side.records.append(_side_record(
                ref=node.slug, kind=kind, key=match, body=node.content,
                title=node.title, summary=str(node.meta.get("summary") or ""),
                revision=revision, parents=node.parents, tags=node.tags,
                created_at=node.created_at, node_id=node.node_id, slug=node.slug,
                artifacts=artifacts, node=node))
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
            has_summary="summary" in raw,
            # An export that never mentions `artifacts` is not asserting there are
            # none — the `summary` reading, and deliberately the *opposite* of the
            # `graph_tags`-absent rule. Absence is "no assertion" when it drives a
            # report, and a hard raise when it drives a write.
            has_artifacts="artifacts" in raw, raw=raw))
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


def plan_op_counts(plan: dict) -> tuple[int, int, int, int]:
    """(creates, body updates, tag assignments, artifact uploads).

    **Counted by op, never by subtraction.** A tag assignment is not an update, and
    reporting it as one overstates what the push does to the record graph — and the
    moment a third op kind exists, a subtraction reintroduces that bug one noun
    later. Which is why this is a 4-tuple rather than a 3-tuple with a wider middle."""
    ops = plan.get("ops") or []
    creates = sum(1 for o in ops if o.get("op") == "create")
    updates = sum(1 for o in ops if o.get("op") == "update")
    tags = sum(1 for o in ops if o.get("op") == "tags")
    artifacts = sum(1 for o in ops if o.get("op") == "artifacts")
    return creates, updates, tags, artifacts


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
    # Read by `HEAL_ARTIFACTS` and by `push --verify --strict`. It was written
    # speculatively — "a new comparison costs one entry in this table" — and the
    # artifact feature is what turned that claim into evidence: it added **zero** new
    # comparator entries and one registry entry, and the only real work was teaching
    # `side_from_local` which block to read the ids out of.
    #
    # Ids, never paths. The other side is always an export holding attachment
    # *objects*; the local side reads `flywheel.artifacts` / `origin.artifacts`,
    # which is precisely the path→id table that makes the two comparable.
    "artifacts": FieldComparator(
        extract=lambda r: sorted(
            str(a.get("artifact_id") or a.get("id") or a) if isinstance(a, dict)
            else str(a) for a in r["artifacts"]),
        applies=lambda left, right: right.get("has_artifacts", True)),
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


def artifacts_sha256(entries) -> str:
    """A stamp for a node's evidence set: sorted `(path, file digest)` pairs.

    A **sibling** of `content_sha256`, never folded into it, for exactly the two
    reasons `tags_sha256` gives: `verify_mirror` and `push_legend` both rest on body
    byte-identity, and folding a third input in would re-push every existing
    adopter's whole graph the first time this shipped.

    A missing file contributes no pair — and the caller must then **withhold this
    stamp entirely** rather than write the hash of what is left. Otherwise "one file
    is missing" would hash to a perfectly stable value, and every later push would
    read it as "everything matches" and never retry."""
    joined = "\n".join(f"{path}\t{digest}" for path, digest in sorted(entries))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def parents_sha256(slugs: list[str]) -> str:
    """A stamp for a node's parent set — the third sibling of `content_sha256`.

    Over **local slugs**, not mirror ids, for the same reason `parents:` frontmatter
    holds slugs: a name survives a fork, a re-home, and a mirror that mints its own
    ids. The mirror ids that set resolved to on the last push are bookkeeping and live
    beside it as `flywheel.parents`, exactly as `flywheel.artifacts` is the path→id
    table next to `artifacts_sha256`.

    Never folded into the body hash, for the two reasons `tags_sha256` gives:
    `verify_mirror` and `push_legend` both rest on body byte-identity, and folding a
    fourth input in would re-push every existing adopter's whole graph."""
    return hashlib.sha256("\n".join(sorted(slugs)).encode("utf-8")).hexdigest()


def artifact_title(path: str, sha256: str) -> str:
    """`<repo-relative path>@<first 12 of the file digest>` — the upload's identity.

    `artifacts:upload` is an **append** with no natural idempotency key: its success
    schema says nothing, and re-running it attaches a second copy. What comes back
    from `artifacts:list` is the title — so putting the digest in it turns *"this
    title is already attached"* into exactly *"these bytes, for this path, are
    already attached"*. That equivalence is what `push_artifacts` dedupes on before
    every batch, and what a crashed run is resolved by.

    **This is the design's weakest joint, and it is written down rather than
    hidden**: `title` is contractually a *display label*, and we read it as identity.
    The same digest also goes into `metadata.hypergraph`, which is preferred whenever
    it round-trips — but nothing in the contract promises that it does, so the title
    is the guarantee. `test_live_artifact_round_trip_preserves_the_title_and_metadata`
    is what makes the assumption checkable against the real host."""
    return f"{path}@{str(sha256)[:12]}"


# Host ceilings, enforced client-side so our error beats theirs — a 51-item batch
# rejected by the server has already spent the writes for the first 50.
ARTIFACT_MAX_BYTES = 100 * 1024 * 1024       # per file
ARTIFACT_BATCH_ITEMS = 50                    # per batch
ARTIFACT_BATCH_BYTES = 128 * 1024 * 1024     # per batch, ours: keeps one PUT run bounded
# `artifacts:list --limit` is clamped to 200 server-side (measured), and the CLI
# exposes no `--offset` — see `FlywheelCliTransport.artifacts` for what that forces.
ARTIFACT_LIST_LIMIT = 200

# Compound suffixes are matched first, because `.plotly.html` and `.vega.json` *are*
# the convention — a plain-suffix table would classify both as their base type and
# the host would render a plot as markup.
#
# Deliberately never inferred: `checkpoint`, `banner`, `diff_carousel`, and bare
# `plotly_html` / `vega`. A `.html` that is really a Plotly export cannot be told from
# a path, and guessing wrong is worse than the honest default. `artifact_item_for`
# takes an `override` so that letting `artifacts:` carry an explicit type later costs
# this half nothing.
ARTIFACT_KIND_BY_SUFFIX: tuple = (
    (".plotly.html", ("plotly_html", "text/html")),
    (".vega.json", ("vega", "application/json")),
    (".md", ("text", "text/markdown")),
    (".txt", ("text", "text/plain")),
    (".log", ("text", "text/plain")),
    (".csv", ("table", "text/csv")),
    (".tsv", ("table", "text/tab-separated-values")),
    (".jsonl", ("json", "application/x-ndjson")),
    (".ndjson", ("json", "application/x-ndjson")),
    (".json", ("json", "application/json")),
    (".png", ("image", "image/png")),
    (".jpg", ("image", "image/jpeg")),
    (".jpeg", ("image", "image/jpeg")),
    (".gif", ("image", "image/gif")),
    (".webp", ("image", "image/webp")),
    (".svg", ("image", "image/svg+xml")),
    (".html", ("html", "text/html")),
    (".htm", ("html", "text/html")),
)
ARTIFACT_KIND_DEFAULT = ("binary", "application/octet-stream")


def artifact_kind_for(path: str) -> tuple[str, str]:
    """A stored path → (host `artifact_type`, media type). One table, both transports.

    REST's prepare step *requires* `media_type`; the CLI is sent it too rather than
    depending on whatever it infers internally, so the two transports cannot
    disagree about what was uploaded."""
    lowered = str(path).lower()
    for suffix, kind in ARTIFACT_KIND_BY_SUFFIX:
        if lowered.endswith(suffix):
            return kind
    return ARTIFACT_KIND_DEFAULT


def artifact_item_for(path: str, sha256: str, *, abs_path: Path | str | None = None,
                      override: dict | None = None) -> dict:
    """One `items[]` entry for `artifacts:upload`.

    `local_path` is **absolute**: the host resolves it against the subprocess cwd,
    which is not this process's and is not the repo root."""
    kind, media = artifact_kind_for(path)
    if override:
        kind = str(override.get("artifact_type") or kind)
        media = str(override.get("media_type") or media)
    return {
        "local_path": str(abs_path if abs_path is not None else path),
        "artifact_type": kind,
        "media_type": media,
        "title": artifact_title(path, sha256),
        "note": f"Hypergraph evidence: {path}",
        # Corroborating, and preferred when it round-trips. The title stays the
        # guarantee because nothing promises this does.
        "metadata": {"hypergraph": {"path": path, "sha256": sha256}},
    }


def file_sha256(path: Path, *, cache: dict | None = None) -> str:
    """A file's digest, memoized on `(size, mtime_ns)` in `cache`.

    This is why `push_plan` stopped being a pure function of the graph directory: a
    repo carrying 400 MB of evidence would otherwise re-read all of it on every
    `push --plan`, including the ones that only wanted to see the op list. The cache
    key is the pair that any rewrite changes."""
    import os  # deferred, matching the rest of this file's os usage

    path = Path(path)
    stat = os.stat(path)
    key = str(path)
    entry = cache.get(key) if cache is not None else None
    if entry and entry.get("size") == stat.st_size \
            and entry.get("mtime_ns") == stat.st_mtime_ns:
        return str(entry["sha256"])
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    if cache is not None:
        cache[key] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                      "sha256": value}
    return value


def load_artifact_hash_cache(path: Path) -> dict:
    """The stat cache, or {}. A corrupt file is {} — it is a cache, not a record."""
    try:
        loaded = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save_artifact_hash_cache(path: Path, cache: dict) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    except OSError:
        pass   # a cache that cannot be written is slow, never wrong


def resolve_artifacts(repo: Path, node: LocalNode, *, cache: dict | None = None
                      ) -> tuple[list[dict], list[str]]:
    """A node's declared paths → (uploadable refs, problems), in declaration order.

    **The path-safety gate, and the only place a path becomes an upload
    instruction.** In order, per path: inside the repo → a regular file → within the
    host's per-file ceiling → hashed. `artifacts: ../../.ssh/id_rsa` is a warning in
    `check` (a path list in a markdown file is a strange but legal thing to write)
    and a hard refusal here, because only here does it turn into bytes leaving the
    machine.

    Untracked files pass with no complaint at all (decision 6): what gets committed
    is the agent's call, and this is not the place to have an opinion about it."""
    refs: list[dict] = []
    problems: list[str] = []
    seen: set[str] = set()
    for raw in node.artifacts:
        stored, abs_path, outside = read_artifact_path(repo, str(raw))
        if stored in seen:
            continue
        seen.add(stored)
        if outside:
            problems.append(
                f"{stored}: resolves outside the repo. The repo is what travels — a "
                "path list in a markdown file must never become an instruction to "
                "upload something from elsewhere on this machine.")
            continue
        if not abs_path.exists():
            problems.append(f"{stored}: not in the working tree")
            continue
        if not abs_path.is_file():
            problems.append(f"{stored}: not a regular file")
            continue
        size = abs_path.stat().st_size
        if size > ARTIFACT_MAX_BYTES:
            problems.append(
                f"{stored}: {size} bytes is over the host's "
                f"{ARTIFACT_MAX_BYTES // (1024 * 1024)} MiB per-file ceiling")
            continue
        refs.append({"path": stored, "abs_path": str(abs_path), "size": size,
                     "sha256": file_sha256(abs_path, cache=cache)})
    return refs, problems


def artifact_batches(refs: list[dict]) -> list[list[dict]]:
    """Split one node's refs into batches the host will accept.

    **One batch is one revision bump** — finalize appends the whole batch atomically —
    so the split is also the unit of recovery, and every batch gets its own journal
    intent."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for ref in refs:
        if current and (len(current) >= ARTIFACT_BATCH_ITEMS
                        or size + int(ref.get("size") or 0) > ARTIFACT_BATCH_BYTES):
            batches.append(current)
            current, size = [], 0
        current.append(ref)
        size += int(ref.get("size") or 0)
    if current:
        batches.append(current)
    return batches


def push_plan(graph_dir: Path, *, do_tags: bool = True, do_artifacts: bool = True,
              do_parents: bool = True, repo: Path | str | None = None) -> dict:
    """Diff local files against their `flywheel:` frontmatter → an ordered op list.

    This tool never calls MCP; the skill layer executes the plan and feeds the
    returned ids back via `push --record-result` (backend/local-adapter.md)."""
    ops: list[dict] = []
    violations: list[str] = []
    tag_ops: list[dict] = []
    parent_ops: list[dict] = []
    artifact_ops: list[dict] = []
    # Resolved lazily, and only once a node actually declares an artifact: a project
    # with none must not pay a `git rev-parse`, let alone a filesystem walk.
    artifact_repo: list = []
    hash_cache: dict = {}
    cache_path = Path(graph_dir).parent / "cache" / "artifact-hashes.json"

    def repo_for_artifacts() -> Path:
        if not artifact_repo:
            artifact_repo.append(Path(repo) if repo is not None
                                 else repo_root_for({}, graph_dir))
            hash_cache.update(load_artifact_hash_cache(cache_path))
        return artifact_repo[0]

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
            # `flywheel.node_id` in the guard: a node that has never been pushed gets
            # its topology from the `create` op, which carries `parent_flywheel_ids`
            # and stamps `parents_sha256` on the way back. Planning an edge move for it
            # as well would be a second write for an edge the create just made.
            if do_parents and flywheel.get("node_id") \
                    and (node.parents or flywheel.get("parents_sha256")):
                stamp = flywheel.get("parents_sha256")
                want = parents_sha256(node.parents)
                # The same `or` clause the tag and artifact stamps carry, and the same
                # reason: with no stamp and no parents there is nothing to do, but a
                # stamp with an empty set is a node whose parents were *cleared*
                # locally, which without this would stay attached on the mirror forever.
                if (node.parents and stamp != want) or (stamp and not node.parents):
                    if kind == "record" and stamp:
                        # A *stamped* record node whose parent set moved is an edit to
                        # causal history. An unstamped one is only this feature's first
                        # run seeding its bookkeeping, which is not a change at all.
                        violations.append(
                            f"{node.slug}: record node parents changed since it was "
                            "pushed — causal history is immutable; do not mirror this "
                            "edit")
                    desired = [str(pfw) for pfw in
                               ((nodes[p].meta.get("flywheel") or {}).get("node_id")
                                for p in node.parents) if pfw]
                    was = [str(p) for p in (flywheel.get("parents") or [])]
                    # The intent, not the authority. `nodes:get` reports `has_parents`
                    # and no parent ids at any projection, so what the mirror actually
                    # holds is only knowable from an export — `push_parents` takes one
                    # and re-derives these two sets from it before writing anything.
                    parent_ops.append({
                        "graph": kind, "slug": node.slug, "op": "parents",
                        "parent_slugs": list(node.parents), "parents": desired,
                        "add": [p for p in desired if p not in was],
                        "remove": [p for p in was if p not in desired],
                        "parents_sha256": want,
                        "flywheel_node_id": flywheel.get("node_id"),
                        "base_revision": flywheel.get("revision")})
            if do_artifacts and (node.artifacts or flywheel.get("artifacts_sha256")):
                refs, problems = resolve_artifacts(
                    repo_for_artifacts(), node, cache=hash_cache)
                stamp = flywheel.get("artifacts_sha256")
                # Withheld entirely when anything is wrong (see `artifacts_sha256`):
                # a partial set must never hash to a stable value that later reads as
                # "matches". `problems` therefore also forces the op, so a broken
                # path is reported on every run instead of hashing to None twice and
                # comparing equal.
                want = None if problems else artifacts_sha256(
                    [(r["path"], r["sha256"]) for r in refs])
                # The `or` clause is the same one the tag test has, and here it lets a
                # node whose last path was removed re-stamp to empty — an op that
                # performs **no mirror write at all** (nothing is ever un-attached).
                if problems or (node.artifacts and stamp != want) \
                        or (stamp and not node.artifacts):
                    artifact_ops.append({
                        "graph": kind, "slug": node.slug, "op": "artifacts",
                        "artifacts": refs, "problems": problems,
                        "artifacts_sha256": want,
                        "declared": [str(a) for a in node.artifacts],
                        "flywheel_node_id": flywheel.get("node_id"),
                        "base_revision": flywheel.get("revision")})
            if not flywheel.get("node_id"):
                parent_fw = []
                for parent in node.parents:
                    pfw = (nodes[parent].meta.get("flywheel") or {}).get("node_id")
                    parent_fw.append(pfw)
                ops.append({**payload, "op": "create", "parent_slugs": node.parents,
                            "parent_flywheel_ids": parent_fw,
                            "parents_sha256": parents_sha256(node.parents),
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
    if artifact_repo:
        save_artifact_hash_cache(cache_path, hash_cache)
    # Three later passes, appended after every node op: each needs the node to exist,
    # and a node created in this same run only gets its mirror id from `minted` partway
    # through the loop above. Parents go before tags (an edge change bumps the child,
    # and a tag assignment locks against that revision); artifacts go **last** — see
    # `execute_push` for why the immune phase is the one that runs at the end.
    return {"version": EXPORT_VERSION, "graph_dir": str(graph_dir),
            "generated_at": utc_now(),
            "ops": ops + parent_ops + tag_ops + artifact_ops,
            "violations": violations}


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


VERIFY_FIELDS = ("body", "summary", "revision", "parents")
# `parents` is in the **default** set, and that is a deliberate move out of `--strict`.
# Topology is the one thing a node file asserts that `push` used to be unable to
# change: an `update` op fires only when `content_sha256` moves and carries no parents,
# so a pure re-parent produced no mirror op at all and forked local topology from
# mirror topology silently, forever. Closing that (`push_parents`) without also
# checking it by default would leave the same class of drift undetectable — an
# unmeasured category is invisible to every check by construction [rec: fresh-spire-9002].
# The slug→mirror-id mapping this needs is therefore unconditional too.
#
# Still off by default and opt-in through `push --verify --strict`, because each of
# these would fire on correct graphs: mirror root titles differ from local ones by
# doctrine, and a re-homed node's created_at is the mirror's. `artifacts` is here and
# **never in VERIFY_FIELDS**: a human attaching an artifact through the host UI is a
# correct graph state, not drift.
VERIFY_STRICT_FIELDS = ("body", "summary", "revision", "title", "parents", "tags",
                        "artifacts")


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
    # Local parents are slugs, mirror parents are mirror ids: map before comparing, or
    # every node reports drift over a difference in vocabulary rather than in topology.
    # Both sides sort — parent *order* is not meaning. Unconditional since `parents`
    # joined VERIFY_FIELDS; without it the default run would report every node.
    by_slug = {r["slug"]: r["key"] for r in local.records if r["slug"] and r["key"]}
    for record in local.records:
        record["parents"] = sorted(str(by_slug.get(p) or p) for p in record["parents"])
    # A mirror root a local root hangs off by design: exempt *and* with no local node
    # claiming it. Both halves are load-bearing. Without the first, real drift onto a
    # stray parent would be hidden; without the second, this repo — which mirrors into
    # the very roots its node files declare — would have its whole first generation
    # report drift, because those roots are exempt and do have local counterparts.
    mirror_only_roots = exempt_ids - {r["key"] for r in local.records if r["key"]}
    for record in mirror.records:
        record["parents"] = sorted(str(p) for p in record["parents"]
                                   if str(p) not in mirror_only_roots)
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
        "artifacts": "artifact set differs between local file and mirror",
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
        "Artifacts did not survive the import: what travels is a repo-relative path,",
        "and the archive holds bytes on a store this repo does not own. They remain on",
        "the archive roots above. Evidence recorded here since adoption travels with",
        "the repo and is published alongside these nodes.",
    ]
    return "\n".join(lines) + "\n"


def merge_artifact_records(existing: object, incoming: list) -> list[dict]:
    """Fold one batch's uploaded artifacts into a node's `flywheel.artifacts`, by path.

    A **merge**, not a replace, for two reasons that both matter:

    - a node's evidence uploads in batches of 50, so a replace would leave the last
      batch as the whole record;
    - **nothing is ever deleted** (decision 5). New bytes for a path push the previous
      `artifact_id` into `superseded:` and keep it, so regenerating a plot stays
      ordinary repo work and the evidence is versioned rather than frozen. A path
      dropped from `artifacts:` keeps its entry too — the mirror still holds it, and
      a record that pretended otherwise would be a lie about a published graph."""
    by_path: dict[str, dict] = {}
    order: list[str] = []
    for record in (existing if isinstance(existing, list) else []):
        if isinstance(record, dict) and record.get("path"):
            by_path[str(record["path"])] = dict(record)
            order.append(str(record["path"]))
    for record in incoming:
        if not isinstance(record, dict) or not record.get("path"):
            continue
        path = str(record["path"])
        prior = by_path.get(path)
        merged = dict(record)
        superseded = list((prior or {}).get("superseded") or [])
        if prior and prior.get("artifact_id") \
                and prior["artifact_id"] != record.get("artifact_id") \
                and prior["artifact_id"] not in superseded:
            superseded.append(prior["artifact_id"])
        if superseded:
            merged["superseded"] = superseded
        by_path[path] = merged
        if path not in order:
            order.append(path)
    return [by_path[p] for p in order]


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
        # Only ever *overwritten* by a result that carries one. An artifact result
        # carries none — its write never touched the body — and stamping the current
        # body hash there would mark a pending body edit as published.
        if entry.get("content_sha256"):
            fw["content_sha256"] = str(entry["content_sha256"])
        elif not fw.get("content_sha256"):
            fw["content_sha256"] = node.sha256
        # Siblings of content_sha256, never folded into it: the body hash is what
        # `verify_mirror` and `push_legend` rest on, and moving it would re-push every
        # existing adopter's whole graph the first time this shipped.
        if entry.get("tags_sha256") is not None:
            fw["tags_sha256"] = str(entry["tags_sha256"])
        if entry.get("artifacts_sha256") is not None:
            fw["artifacts_sha256"] = str(entry["artifacts_sha256"])
        if entry.get("parents_sha256") is not None:
            fw["parents_sha256"] = str(entry["parents_sha256"])
            # Replaced whole, never merged: the mirror ids this node's parent slugs
            # resolved to *as of that stamp*. Merging would keep a detached edge in the
            # table forever and make the next plan re-issue its removal on every run.
            fw["parents"] = [str(p) for p in (entry.get("parents") or [])]
        if entry.get("artifacts") is not None:
            fw["artifacts"] = merge_artifact_records(fw.get("artifacts"),
                                                     entry["artifacts"])
        meta = dict(node.meta)
        meta["flywheel"] = fw
        node.path.write_text(render_node_file(meta, node.content))
        applied += 1
    return applied


# Config/git introspection the offline commands need — deliberately this side of
# the module boundary: `push` must gate on them *before* deciding whether to load
# the mirror module at all.

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
            raise LocalGraphError(
                f"no mirror root for the {kind} graph — set `mirror_roots.{kind}.node_id` "
                f"in the config (mint them with `hypergraph mirror roots --mint`)")
        roots[kind] = node_id

    archive_ids = {str(r.get("node_id")) for r in (config.get("archive") or {}).get("roots", [])
                   if isinstance(r, dict) and r.get("node_id")}
    clash = archive_ids & set(roots.values())
    if clash:
        raise LocalGraphError(
            f"mirror root {sorted(clash)[0]} is also an `archive:` root. The archive is "
            "frozen and this project never writes to it; splicing it in makes "
            "`push --verify` pass while the mirror holds almost none of the graph "
            "(backend/mirror.md).")
    return roots


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


# ------------------------------------------------------------------- upgrading
# An adopted repo carries *copies* of things this package ships: the skills
# under `.claude/skills/`, the sentinel-delimited AGENTS.md block, and sometimes the
# CI workflows. `uv tool upgrade` refreshes the CLI and cannot see any of them, so
# before this command the only way a fix reached an adopter's skill was for someone
# to remember to say so. That is how the 0.0.6 adoption fixes shipped into a package
# whose *installed* skill still described the step order they fixed.
#
# The contract is deliberately narrow: **refresh what is already there, never
# install what is not.** An upgrade that quietly adds CI to a repo that never wanted
# it is a worse failure than a stale file.

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
    """Same relative paths, same bytes. Cheap enough for the small skill trees."""
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
    """Bring an adopted repo's *copies* up to the running CLI's release.

    With `--graph`, delegate to the graph-repair half instead (formerly `heal`):
    detect-only until `--apply`, because it rewrites node files rather than
    refreshing `git checkout`-reversible copies."""
    if getattr(args, "graph", None) is not None:
        args.healer = args.graph
        return cmd_heal(args)
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
            print(f"  --graph {healer.name:<10} {healer.summary} (since {healer.since})")
        print("\nThese rewrite graph content, not copies, so they stay behind "
              "--graph\nand detect-only until --apply:\n"
              f"  hypergraph upgrade --graph {applicable[0].name}")
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
# Bare `upgrade` answers "are this repo's *copies* current". `upgrade --graph`
# answers "is this repo's *graph content* current" — one verb, two polarities,
# because the answers cost different things. Every effect of the copies half is a
# file we shipped and `git checkout` undoes it. The graph half rewrites the graph
# itself and spends an irreversible mirror-write budget, so it cannot share the
# copies half's "just run it" posture: it stays detect-only until `--apply`.
# (`heal` survives as a deprecated alias for the 0.9.x series.)
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
        ctx.session = _mirror().mirror_session(ctx.config, ctx.args)
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
    if reason := _mirror().mirror_not_ours(ctx.config, transport):
        changes.append(Change("blocked", "mirror", reason))
        return changes
    assigned = _mirror().push_tags(ctx.graph_dir, ctx.config,
                                   mirror_root_ids(ctx.config),
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

# ---------------------------------------------------------- healer 2: artifacts

def artifacts_blocked_by(config: dict, repo: Path) -> str | None:
    """→ why `heal artifacts` does not apply here, or None when it does.

    **The normal case needs no healer at all, and that difference from tags is the
    point.** A repo that adopted before tags existed *lost the names* — they were on
    the archive and nothing local held them. A repo that adopted before artifacts
    existed lost nothing, because there was nothing local to lose. Adding paths to old
    record nodes today is served by `hypergraph artifacts add` plus `push`, which
    plans on the absent stamp. This healer exists only for the one thing that is
    genuinely unrecoverable by hand: an inventory of what the *frozen archive* still
    holds, per node."""
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
                "so there is no archive inventory to record. To attach evidence to "
                "existing record nodes, use `hypergraph artifacts add` and push; the "
                "plan fires on the absent stamp and there is nothing to heal")
    return None


def _archive_artifact_record(raw: object) -> dict:
    """One archive attachment → the compact inventory entry recorded under `origin:`."""
    if not isinstance(raw, dict):
        return {"artifact_id": str(raw)}
    out = {"artifact_id": artifact_id_of(raw)}
    for key in ("title", "artifact_type", "media_type", "created_at"):
        if raw.get(key):
            out[key] = str(raw[key])
    return out


def artifacts_detect(ctx: HealContext) -> list[Drift]:
    """What the frozen archive holds against what `origin:` records, on `origin.node_id`."""
    data, where = heal_source_export(ctx)
    ctx.out(f"heal artifacts: reading the source graph from {where}")
    local = side_from_local(ctx.graph_dir, key="origin", name="repo")
    archive = side_from_export(data, key="node_id", name="archive")
    drifts = diff_graphs(local, archive, fields=("artifacts",))
    return [d for d in drifts if d.kind == "field" and d.field == "artifacts"]


def artifacts_apply(ctx: HealContext, drifts: list[Drift]) -> list[Change]:
    """Frontmatter only, and deliberately **no mirror phase at all**.

    What lands is an *inventory*: which attachments the frozen archive still holds for
    each imported node, under `origin.artifacts`. It records where the bytes are; it
    does not fetch them, and it must not publish them. Those bytes are not in this
    repo, so re-uploading them would leave the mirror holding evidence the repo cannot
    regenerate — the one property `backend/mirror.md` will not trade away.

    Because every write here is a frontmatter edit, this healer never needs
    `heal_write_targets`, works offline, and is fully `git checkout`-reversible."""
    data, _where = heal_source_export(ctx)
    archive = side_from_export(data, key="node_id", name="archive")
    local: dict[str, LocalNode] = {}
    for kind in GRAPH_KINDS:
        local.update(load_local_nodes(ctx.graph_dir, kind, missing_ok=True))

    changes: list[Change] = []
    for drift in drifts:
        node = local.get(drift.left_ref)
        if node is None:
            changes.append(Change("skipped", drift.left_ref,
                                  "no longer a node in this repo"))
            continue
        source = archive.nodes.get(drift.key) or {}
        records = [_archive_artifact_record(a) for a in (source.get("artifacts") or [])]
        if not records:
            changes.append(Change("unchanged", drift.left_ref,
                                  "no artifacts on the archive node"))
            continue
        origin = dict(node.meta.get("origin") or {})
        origin["artifacts"] = records
        meta = dict(node.meta)
        meta["origin"] = origin
        text = render_node_file(meta, node.content)
        # Byte-compare before writing: a no-op heal must touch zero files, or the
        # idempotence claim is unverifiable.
        if text == node.path.read_text():
            changes.append(Change("unchanged", node.path, ""))
            continue
        if ctx.args.apply:
            node.path.write_text(text)
        changes.append(Change("healed", node.path,
                              f"{len(records)} archive artifact(s) inventoried"))
    changes.append(Change("skipped", "mirror",
                          "by design: the archive's bytes are not in this repo, so "
                          "publishing them would make the mirror the only holder of "
                          "evidence the repo cannot regenerate"))
    return changes


HEAL_ARTIFACTS = Healer(
    name="artifacts",
    summary="record what the frozen archive still holds per node, under "
            "`origin.artifacts` (an inventory, never a repatriation)",
    since="0.0.9",
    reads="archive",
    writes=("frontmatter",),
    detect=artifacts_detect,
    apply=artifacts_apply,
    blocked_by=artifacts_blocked_by,
)

# The registry. A new healer is one entry here plus, if it compares a new field, one
# entry in FIELD_COMPARATORS. Nothing else — and `artifacts` is what makes that a
# measured claim rather than a hopeful one: it needed the entry that was already
# there, and nothing besides this line.
HEALERS: tuple = (HEAL_TAGS, HEAL_ARTIFACTS)


# ------------------------------------------------------------- the heal driver
# Generic over the registry: ordering, applicability, the dirty-tree guard, and
# the detect/apply loop `upgrade --graph` drives. Nothing here is healer-specific.

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
    if getattr(args, "_heal_alias", False):
        print("note: `heal` is deprecated — it folded into `upgrade --graph` at "
              "0.9.0, and the alias goes away after the 0.9.x series.",
              file=sys.stderr)
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
            "rewrite the reference graph the tests read. Run `upgrade --graph` in an "
            "adopted repo, or pass --repo.")

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
                          f"`hypergraph upgrade --graph {healer.name} --apply` acts.")
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
    """`upgrade --graph` with no healer named: the registry and what applies here."""
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
        print(f"\n  hypergraph upgrade --graph {applicable[0].name}            "
              "# detect only (the default)\n"
              f"  hypergraph upgrade --graph {applicable[0].name} --apply    "
              "# rewrite the graph and publish")
    return 0


# -------------------------------------------------------- the mirror module
# The mirror's networked half lives in a sibling file (tools/hypergraph_mirror.py;
# installed as hypergraph_protocol_mirror.py). The split sits at the network
# boundary, not at the word "mirror": offline mirror *bookkeeping* — push_plan,
# verify_mirror, apply_push_results, legend/lineage — stays above, because
# `push --plan` and friends must work with no mirror module at all. What moved is
# everything that resolves a credential, looks for a binary, or opens a socket.
# The docstring promise gets mechanical this way: offline commands never import
# the mirror module — tests/test_mirror_split.py asserts it by subprocess.

def _mirror():
    """Load the mirror sibling exactly once and return it.

    Not a plain `import`: core runs under three module names — `__main__` (uv run),
    `hypergraph_protocol` (installed wheel), and the test fixture's spec-load — so
    an `import hypergraph_core` inside the sibling would create a *second* copy of
    this module and fork every class identity (a MirrorError raised there would
    not be caught by an `except LocalGraphError` here). Registering this very
    module object as `hypergraph_core` before exec makes the sibling's import
    resolve to us, whichever name we are running under."""
    module = sys.modules.get("hypergraph_mirror")
    if module is not None:
        return module
    import importlib.util
    here = Path(__file__).resolve().parent
    path = next((p for p in (here / "hypergraph_mirror.py",
                             here / "hypergraph_protocol_mirror.py") if p.exists()),
                None)
    if path is None:
        raise LocalGraphError(
            f"the mirror module is missing beside {Path(__file__).name} — expected "
            "hypergraph_mirror.py (dev checkout) or hypergraph_protocol_mirror.py "
            "(installed wheel). Reinstall, or run the offline commands only.")
    sys.modules.setdefault("hypergraph_core", sys.modules[__name__])
    spec = importlib.util.spec_from_file_location("hypergraph_mirror", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["hypergraph_mirror"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("hypergraph_mirror", None)
        raise
    return module


# ----------------------------------------------------- push / sync entry points
# The commands stay in core because most of what they do is offline: `push`'s
# plan/verify/record-result/legend/lineage modes and its stand-down gates never
# need a transport, and `sync` is export → render → check before it ever thinks
# about publishing. Only the executing tail (`run_push`) lives in the mirror
# module, loaded at the last possible moment.

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
        plan = push_plan(graph_dir, do_artifacts=not args.no_artifacts,
                         repo=getattr(args, "repo", None))
        text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            Path(args.output).write_text(text)
            print(f"wrote {args.output}")
        else:
            print(text, end="")
        creates, updates, tags, artifacts = plan_op_counts(plan)
        print(f"push plan: {creates} create(s), {updates} update(s)"
              + (f", {tags} tag assignment(s)" if tags else "")
              + (f", {artifacts} artifact upload(s)" if artifacts else ""),
              file=sys.stderr)
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
    # The first two gates are transport-free and deliberately sit on this side of
    # the module boundary: a mirror-less project or a feature branch stands down
    # without the mirror module ever being imported.
    if not mirror_configured(config):
        print("push: no mirror configured — nothing to publish")
        return 0

    if not args.allow_any_branch:
        if blocked := publish_branch_block(config):
            if args.require_mirror:
                raise LocalGraphError(f"{blocked} (--require-mirror)")
            print(f"push: {blocked} — nothing published")
            return 0

    return _mirror().run_push(args, config, graph_dir)


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
                                    config=args.config,
                                    repo=getattr(args, "repo", None))
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
        no_legend=False, no_tags=args.no_tags, no_artifacts=args.no_artifacts,
        no_verify=args.no_verify, skip_preflight=args.skip_preflight,
        transport=args.transport, rate=args.rate, journal=args.journal,
        repo=getattr(args, "repo", None),
        allow_any_branch=args.allow_any_branch, require_mirror=args.require_mirror)
    return cmd_push(push_args)


def cmd_mirror(args: argparse.Namespace) -> int:
    """Every `mirror` action needs a transport, so the body lives in the module."""
    return _mirror().run_mirror(args)


# ------------------------------------------------------- dispatch: local lanes
# The local lane provider (backend/lanes.md): a git worktree on a `lane/<slug>`
# branch, minted here — the agent never names its own lane. Config, all optional,
# read by this CLI only (the hypergraph-dispatch skill may name these verbs but
# never a provider's internals — the mirror's isolation pattern):
#
#   dispatch:
#     lanes_dir: .hypergraph/lanes   # where worktrees are provisioned
#     agent: "my-agent --cwd {lane_dir}"   # command template; {lane_dir} is the
#                                          # ONLY placeholder. The dispatch brief
#                                          # (target, budget, attribution) travels
#                                          # on stdin, never argv — argv is
#                                          # world-readable process state.
#
# With no `agent:` configured, `open` provisions the lane and stands down at
# exit 0, printing the manual steps — the push/no-mirror posture.

DEFAULT_LANES_DIR = ".hypergraph/lanes"
LANE_BRANCH_PREFIX = "lane/"


def _lane_git(repo: Path, *args: str) -> str:
    """git that raises: lane bookkeeping must never mistake failure for empty."""
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, timeout=60)
    if proc.returncode != 0:
        raise LocalGraphError(
            f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


def dispatch_repo(args: argparse.Namespace) -> Path:
    repo = getattr(args, "repo", None)
    if repo:
        return Path(repo).resolve()
    top = _git(Path.cwd(), "rev-parse", "--show-toplevel").strip()
    if not top:
        raise LocalGraphError("dispatch needs a git repository (lanes are worktrees)")
    return Path(top)


def dispatch_lanes(repo: Path) -> list[dict]:
    """Every lane worktree: [{slug, path, branch, dirty, merged}]."""
    lanes = []
    entry: dict = {}
    for line in (_git(repo, "worktree", "list", "--porcelain") + "\n").splitlines():
        if line.startswith("worktree "):
            entry = {"path": Path(line.split(" ", 1)[1])}
        elif line.startswith("branch refs/heads/" + LANE_BRANCH_PREFIX):
            branch = line.split("refs/heads/", 1)[1]
            entry["branch"] = branch
            entry["slug"] = branch[len(LANE_BRANCH_PREFIX):]
        elif not line and entry.get("slug"):
            entry["dirty"] = bool(_git(entry["path"], "status", "--porcelain").strip())
            merged = _git(repo, "branch", "--merged", "HEAD",
                          "--format=%(refname:short)")
            entry["merged"] = entry["branch"] in merged.split()
            lanes.append(entry)
            entry = {}
        elif not line:
            entry = {}
    return lanes


def live_dispatch_claims(graph_dir: Path) -> list[dict]:
    """Unreconciled `Dispatch:` record nodes with no `Dispatch closed:` descendant.

    Advisory by design (SPEC: Dispatch and lanes): this is how a second dispatch
    avoids a first one's target. It reads only the local node files, so a claim on
    an unmerged lane branch is invisible until harvest — the merge story absorbs
    that window, as it does every other concurrent-contributor race."""
    nodes = load_local_nodes(graph_dir, "record", missing_ok=True)
    state = load_local_nodes(graph_dir, "state", missing_ok=True)
    reconciled: set[str] = set()
    state_root = next((n for n in state.values() if not n.parents), None)
    if state_root is not None:
        frontier, _err = read_hwm(Node(node_id="", slug=state_root.slug,
                                       title=state_root.title,
                                       content=state_root.content,
                                       parent_ids=[], created_at=""))
        if frontier:
            graph = local_graph(nodes, "record")
            ids = ancestors_of(graph, [s for s in frontier if s in graph.by_slug])
            reconciled = {graph.nodes[i].slug for i in ids if i in graph.nodes}

    children: dict[str, list[str]] = {}
    for slug, node in nodes.items():
        for parent in node.parents:
            children.setdefault(parent, []).append(slug)

    claims = []
    for slug, node in nodes.items():
        if not str(node.title).startswith("Dispatch:") or slug in reconciled:
            continue
        closed, queue, seen = False, list(children.get(slug, [])), set()
        while queue and not closed:
            child = queue.pop()
            if child in seen:
                continue
            seen.add(child)
            if "Dispatch closed:" in nodes[child].content:
                closed = True
            queue.extend(children.get(child, []))
        if not closed:
            claims.append({"slug": slug, "title": node.title})
    return claims


def dispatch_open(args: argparse.Namespace, config: dict, repo: Path) -> int:
    lanes_dir = Path((config.get("dispatch") or {}).get("lanes_dir")
                     or DEFAULT_LANES_DIR)
    if not lanes_dir.is_absolute():
        lanes_dir = repo / lanes_dir
    taken = {lane["slug"] for lane in dispatch_lanes(repo)}
    taken |= {b[len(LANE_BRANCH_PREFIX):] for b in
              _git(repo, "branch", "--format=%(refname:short)").split()
              if b.startswith(LANE_BRANCH_PREFIX)}
    slug = mint_slug(taken)
    lane_dir = lanes_dir / slug
    lane_dir.parent.mkdir(parents=True, exist_ok=True)
    _lane_git(repo, "worktree", "add", "-b", LANE_BRANCH_PREFIX + slug,
              str(lane_dir), "HEAD")
    print(f"lane {slug}: {lane_dir} on {LANE_BRANCH_PREFIX}{slug}")

    # The brief travels on stdin, never argv (backend/lanes.md op 2/3): argv is
    # world-readable process state, and the channel must not fork on a judgment
    # call about which parts of a brief are sensitive.
    brief = {"lane": slug, "lane_dir": str(lane_dir),
             "branch": LANE_BRANCH_PREFIX + slug,
             "target": args.at, "budget": args.budget,
             "skill": "hypergraph-dispatch",
             "close": f"hypergraph dispatch harvest {slug} && "
                      f"hypergraph dispatch close {slug}"}

    agent = str((config.get("dispatch") or {}).get("agent") or "").strip()
    if not agent:
        # The push posture: exit 0, say why, name the manual path.
        print(f"\ndispatch open: no `dispatch.agent` configured — standing down; "
              "the lane is yours to drive:\n"
              f"  1. cd {lane_dir}\n"
              f"  2. follow the hypergraph-dispatch skill at the target "
              f"({args.at or 'orient and choose'}), budget {args.budget} unit(s)\n"
              f"  3. record + commit on {LANE_BRANCH_PREFIX}{slug}, then from "
              f"{repo}:\n"
              f"       hypergraph dispatch harvest {slug}\n"
              f"       hypergraph dispatch close {slug}")
        return 0

    import shlex
    argv = [part.replace("{lane_dir}", str(lane_dir))
            for part in shlex.split(agent)]
    proc = subprocess.run(argv, input=json.dumps(brief, ensure_ascii=False),
                          text=True, cwd=lane_dir)
    # Exit status attests the harness ran, never that the work succeeded
    # (backend/lanes.md op 3): what the work found is in the arrived nodes.
    print(f"dispatch open: agent exited {proc.returncode} in lane {slug} — "
          f"harvest with `hypergraph dispatch harvest {slug}`")
    return proc.returncode


def dispatch_harvest(args: argparse.Namespace, config: dict, repo: Path,
                     graph_dir: Path) -> int:
    lane = next((l for l in dispatch_lanes(repo) if l["slug"] == args.lane), None)
    if lane is None:
        raise LocalGraphError(f"no lane named {args.lane!r} — `hypergraph dispatch ls`")
    if lane["dirty"]:
        raise LocalGraphError(
            f"lane {args.lane} has uncommitted changes — commit them in the lane "
            "first. Harvest brings home commits; it must never leave work behind.")
    if _git(repo, "status", "--porcelain").strip():
        raise LocalGraphError(
            "this checkout has uncommitted changes — commit or stash before "
            "merging a lane, so the harvest is one clean merge.")
    record_dir = graph_dir if graph_dir.is_absolute() else repo / graph_dir
    before = {p.name for p in (record_dir / "record").glob("*.md")}
    _lane_git(repo, "merge", "--no-edit", lane["branch"])
    arrived = sorted({p.stem for p in (record_dir / "record").glob("*.md")
                      if p.name not in before})
    print(f"harvest {args.lane}: merged {lane['branch']}"
          + (f" — {len(arrived)} record node(s) arrived: {', '.join(arrived)}"
             if arrived else " — no new record nodes"))
    if arrived:
        print("reconcile pending — the maintainer folds these on the default branch")
    return 0


def dispatch_close(args: argparse.Namespace, repo: Path) -> int:
    lane = next((l for l in dispatch_lanes(repo) if l["slug"] == args.lane), None)
    if lane is None:
        raise LocalGraphError(f"no lane named {args.lane!r} — `hypergraph dispatch ls`")
    # Teardown refuses while unharvested (backend/lanes.md op 5): destroying work
    # that was never brought home is the one irreversible provider mistake.
    if (lane["dirty"] or not lane["merged"]) and not args.force:
        why = "uncommitted changes" if lane["dirty"] else "unmerged commits"
        raise LocalGraphError(
            f"lane {args.lane} has {why} — `hypergraph dispatch harvest "
            f"{args.lane}` first, or --force to abandon the work.")
    _lane_git(repo, "worktree", "remove", *( ["--force"] if args.force else []),
              str(lane["path"]))
    _lane_git(repo, "branch", "-D" if args.force else "-d", lane["branch"])
    print(f"closed lane {args.lane}"
          + (" (forced — its work is abandoned)" if args.force else ""))
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = dispatch_repo(args)
    graph_dir = args.graph_dir or Path(config.get("graph_dir") or DEFAULT_GRAPH_DIR)

    if args.action == "open":
        return dispatch_open(args, config, repo)
    if args.action == "ls":
        lanes = dispatch_lanes(repo)
        for lane in lanes:
            state = ("dirty" if lane["dirty"]
                     else "merged" if lane["merged"] else "unmerged")
            print(f"  {lane['slug']:<20} {state:<9} {lane['path']}")
        if not lanes:
            print("  no lanes")
        # claims are graph facts, not lane facts: a claim outlives its lane
        claims = live_dispatch_claims(
            graph_dir if graph_dir.is_absolute() else repo / graph_dir)
        for claim in claims:
            print(f"  claim  {claim['slug']:<20} {claim['title']}")
        if not claims:
            print("  no live dispatch claims")
        return 0
    if args.action == "harvest":
        if not args.lane:
            raise LocalGraphError("dispatch harvest needs a lane slug")
        return dispatch_harvest(args, config, repo, graph_dir)
    if args.action == "close":
        if not args.lane:
            raise LocalGraphError("dispatch close needs a lane slug")
        return dispatch_close(args, repo)
    raise LocalGraphError(f"unknown dispatch action: {args.action}")


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
        mirror = _mirror()
        transport, _journal, _pacer, cache_dir = mirror.mirror_session(config, args)
        return mirror.mirror_pull(transport, args, out_dir=args.out_dir or cache_dir)

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


# -------------------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hypergraph.py", description=__doc__)
    parser.add_argument("--version", action="version",
                        version=f"hypergraph-protocol {__version__}")
    # metavar hides unlisted aliases (the deprecated `heal`) from the usage line's
    # brace enumeration; parsers added without help= already stay out of the table.
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p_check = sub.add_parser("check", help="validate protocol invariants over graph exports")
    p_check.add_argument("--record", type=Path, required=True, help="record-graph export JSON")
    p_check.add_argument("--state", type=Path, required=True, help="state-graph export JSON")
    p_check.add_argument("--config", type=Path, help=".hypergraph/config.yml")
    p_check.add_argument("--repo", type=Path, metavar="PATH",
                         help="repo root that `artifacts:` paths are relative to "
                              "(default: `git rev-parse --show-toplevel`, else cwd)")
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

    p_viz = sub.add_parser("viz", help="moved out of core; see hypergraph-viz")
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
    p_new.add_argument("--artifact", action="append", metavar="PATH",
                       help="record only: a file this node's claims rest on "
                            "(repeatable). Given cwd-relative like `git add`, stored "
                            "repo-relative. Explain it in `## Method`/`## Result` too "
                            "— the prose is the claim, this list is its index")
    p_new.add_argument("--repo", type=Path, metavar="PATH",
                       help="repo root that --artifact paths are stored relative to "
                            "(default: `git rev-parse --show-toplevel`, else cwd)")
    p_new.set_defaults(func=cmd_new)

    p_artifacts = sub.add_parser(
        "artifacts", help="list or edit the evidence a record node points at")
    p_artifacts.add_argument("action", choices=["ls", "add", "rm", "mv"],
                             help="ls: every declared path with what is wrong with "
                                  "it. add/rm: attach or detach a pointer — never "
                                  "the file itself. mv OLD NEW: repoint in place")
    p_artifacts.add_argument("slug", nargs="?", help="the record node (ls: optional)")
    p_artifacts.add_argument("path", nargs="*", help="repo path(s); mv takes OLD NEW")
    graph_args(p_artifacts)
    p_artifacts.add_argument("--repo", type=Path, metavar="PATH",
                             help="repo root paths are stored relative to (default: "
                                  "`git rev-parse --show-toplevel`, else cwd)")
    p_artifacts.add_argument("--allow-missing", action="store_true",
                             help="add: attach a path that is not in the working tree "
                                  "yet (a gitignored dataset, a run still going)")
    p_artifacts.add_argument("--json", action="store_true", help="ls: machine-readable")
    p_artifacts.set_defaults(func=cmd_artifacts)

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
    p_update.add_argument("--body",
                          help="new full markdown body, or `-` for stdin (omit to "
                               "keep the current body — a re-parent need not rewrite it)")
    p_update.add_argument("--title")
    p_update.add_argument("--summary")
    p_update.add_argument("--parent", action="append", metavar="SLUG",
                          help="re-home this state node under SLUG (repeatable, "
                               "replaces the whole parent set). State nodes only: "
                               "record parents are causal history and immutable")
    p_update.add_argument("--root", action="store_true",
                          help="promote this state node to the parentless graph root")
    p_update.add_argument("--expect", help="sha256 of the body you read (optimistic lock)")
    p_update.add_argument("--print-sha", action="store_true",
                          help="print the current body sha256 and exit (the read half of the CAS)")
    p_update.add_argument("--reconcile", action="store_true",
                          help="required: assert this is a reconcile pass (SPEC I3)")
    p_update.set_defaults(func=cmd_update)

    p_skills = sub.add_parser("skills", help="manage the shipped Claude skills")
    p_skills.add_argument("action", choices=["install"],
                          help="install: copy the hypergraph-* skills")
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
                        "workflows) to this CLI's release; --graph repairs graph "
                        "content instead (detect-only until --apply)")
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

    def artifact_repo_arg(p: argparse.ArgumentParser) -> None:
        # Not folded into `mirror_args`: `heal` and `adopt` already declare a `--repo`
        # of their own, and argparse refuses a second one on the same parser.
        p.add_argument("--repo", type=Path, metavar="PATH",
                       help="repo root that `artifacts:` paths resolve against "
                            "(default: `git rev-parse --show-toplevel`, else cwd)")

    p_push = sub.add_parser("push", help="publish committed node files to the mirror")
    graph_args(p_push)
    mirror_args(p_push)
    artifact_repo_arg(p_push)
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
    p_push.add_argument("--no-artifacts", action="store_true",
                        help="skip uploading the files record nodes point at")
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
    artifact_repo_arg(p_sync)
    p_sync.add_argument("--out-dir", type=Path,
                        help=f"where to write the exports (default: {DEFAULT_CACHE_DIR})")
    p_sync.add_argument("--state-md", type=Path, help="STATE.md path (default: from config)")
    p_sync.add_argument("--no-push", action="store_true",
                        help="stop after export/render/check")
    p_sync.add_argument("--no-verify", action="store_true",
                        help="skip the drift check after publishing")
    p_sync.add_argument("--no-tags", action="store_true",
                        help="skip the tag vocabulary and per-node assignments")
    p_sync.add_argument("--no-artifacts", action="store_true",
                        help="skip uploading the files record nodes point at")
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
    artifact_repo_arg(p_mirror)
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

    # Deprecated alias for `upgrade --graph` (0.9.0). No help= → absent from the
    # commands table; the subparsers metavar keeps it out of the usage brace list.
    # Works through the 0.9.x series, then goes away.
    p_heal = sub.add_parser("heal")
    p_heal.add_argument("healer", nargs="*",
                        help=f"which repair(s) to run (have: "
                             f"{', '.join(h.name for h in HEALERS)}). "
                             "With none named, lists the registry and exits 0")
    graph_args(p_heal)
    mirror_args(p_heal)
    heal_args(p_heal)
    p_heal.add_argument("--repo", type=Path, help="repo root (default: cwd)")
    p_heal.set_defaults(func=cmd_heal, _heal_alias=True)

    # The graph-repair half of `upgrade` (formerly `heal`): bare `--graph` lists the
    # registry, `--graph <healer>` detects, `--apply` makes it act. p_upgrade already
    # declares --repo/--config, so the shared helpers that would re-add those
    # (graph_args, a --repo of heal's own) are not applied wholesale.
    p_upgrade.add_argument("--graph", nargs="*", metavar="HEALER", default=None,
                           help="repair graph content instead of refreshing copies: "
                                f"typed retroactive repairs (have: "
                                f"{', '.join(h.name for h in HEALERS)}). Bare --graph "
                                "lists the registry. Detect-only until --apply")
    p_upgrade.add_argument("--graph-dir", type=Path,
                           help=f"node-file root (default: {DEFAULT_GRAPH_DIR})")
    mirror_args(p_upgrade)
    heal_args(p_upgrade)

    # ---- local lane provider: backend/lanes.md
    p_dispatch = sub.add_parser(
        "dispatch", help="local lanes: open/ls/harvest/close a git-worktree lane "
                         "for a dispatched agent (backend/lanes.md)")
    p_dispatch.add_argument("action", choices=["open", "ls", "harvest", "close"],
                            help="open: mint a lane and launch (or print the manual "
                                 "steps). ls: lanes + live dispatch claims. harvest: "
                                 "merge a lane's commits home. close: tear the lane "
                                 "down (refuses while unharvested)")
    p_dispatch.add_argument("lane", nargs="?",
                            help="lane slug (harvest/close)")
    graph_args(p_dispatch)
    p_dispatch.add_argument("--at", metavar="TARGET",
                            help="open: the dispatch target — a frontier state "
                                 "slug, a prose goal, or `within <state-slug>`")
    p_dispatch.add_argument("--budget", type=int, default=1, metavar="N",
                            help="open: units of work (default 1)")
    p_dispatch.add_argument("--force", action="store_true",
                            help="close: tear down even with unmerged or "
                                 "uncommitted work (abandons it)")
    p_dispatch.add_argument("--repo", type=Path, help="repo root (default: the "
                                                      "enclosing git toplevel)")
    p_dispatch.set_defaults(func=cmd_dispatch)

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
    if getattr(args, "command", None) == "upgrade" and args.graph is not None \
            and args.dry_run:
        parser.error("--dry-run belongs to the copies half; --graph is already "
                     "detect-only, and `--apply` is what makes it write")
    if getattr(args, "command", None) == "import" and not (args.record or args.state):
        parser.error("import needs --record and/or --state")
    if getattr(args, "command", None) == "tags" and args.action in ("add", "rm") \
            and not args.name:
        parser.error(f"tags {args.action} needs a tag name")
    if getattr(args, "command", None) == "artifacts":
        if args.action != "ls" and not args.slug:
            parser.error(f"artifacts {args.action} needs a record node slug")
        if args.action in ("add", "rm") and not args.path:
            parser.error(f"artifacts {args.action} needs at least one path")
        if args.action == "mv" and len(args.path) != 2:
            parser.error("artifacts mv needs exactly two paths: OLD NEW")
    if getattr(args, "command", None) == "update" and not args.print_sha:
        if not any((args.body, args.parent, args.root, args.title,
                    args.summary is not None)):
            parser.error("update needs --body, --parent/--root, --title or --summary "
                         "(or --print-sha)")
        if not args.expect:
            parser.error("update needs --expect <sha256> — get it with --print-sha first")
    try:
        return args.func(args)
    except LocalGraphError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
