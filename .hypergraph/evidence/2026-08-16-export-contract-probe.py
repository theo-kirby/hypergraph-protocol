#!/usr/bin/env python3
"""Measure the JSON-export contract of a Hypergraph project.

The viz cut (loyal-tide-3608) made `.hypergraph/cache/{record,state}.json` the
whole integration surface for external renderers. This probe pins that contract
down empirically: it reads both exports read-only, derives the observed schema
(key presence, value types), and checks the structural guarantees a consumer
would have to rely on — uniqueness, referential integrity, acyclicity, single
root, timestamp and slug formats, and the state-only `Status:` convention.

Stdlib-only, read-only, repo-independent.

Usage:
    python3 2026-08-16-export-contract-probe.py <cache-dir> [--json OUT]

<cache-dir> must contain record.json and state.json (an `export` output dir,
normally .hypergraph/cache). Exit 0 always; findings live in the report — this
is a measurement, not a gate.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z]+(?:-[a-z]+)+-\d{4}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
STATUS_RE = re.compile(r"^Status:\s*(\S+)", re.MULTILINE)
SPEC_STATUSES = {"working", "open", "broken", "blocked", "superseded"}


def iso_ok(value):
    try:
        datetime.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def probe_file(path, kind):
    doc = json.loads(Path(path).read_text())
    findings = []
    report = {"file": str(path), "kind": kind, "findings": findings}

    top_keys = sorted(doc)
    report["top_level_keys"] = top_keys
    report["version"] = doc.get("version")
    report["exported_at"] = doc.get("exported_at")
    if top_keys != ["exported_at", "nodes", "version"]:
        findings.append(f"unexpected top-level keys: {top_keys}")
    if not iso_ok(doc.get("exported_at", "")):
        findings.append(f"exported_at not ISO-8601: {doc.get('exported_at')!r}")

    nodes = doc.get("nodes", [])
    report["node_count"] = len(nodes)

    # Key census: presence count and observed JSON types per key.
    census = {}
    for node in nodes:
        for key, value in node.items():
            entry = census.setdefault(key, {"present": 0, "types": set()})
            entry["present"] += 1
            entry["types"].add(type(value).__name__)
    report["key_census"] = {
        key: {
            "present": entry["present"],
            "always": entry["present"] == len(nodes),
            "types": sorted(entry["types"]),
        }
        for key, entry in sorted(census.items())
    }

    # Structural guarantees a consumer would rely on.
    ids = [n.get("node_id") for n in nodes]
    slugs = [n.get("slug_name") for n in nodes]
    if len(set(ids)) != len(ids):
        findings.append("node_id values are not unique")
    if len(set(slugs)) != len(slugs):
        findings.append("slug_name values are not unique")
    for n in nodes:
        sid = n.get("slug_name", "?")
        if not UUID_RE.match(n.get("node_id") or ""):
            findings.append(f"{sid}: node_id not a lowercase UUID")
        if not SLUG_RE.match(n.get("slug_name") or ""):
            findings.append(f"{sid}: slug_name not words-####")
        if not iso_ok(n.get("created_at", "")):
            findings.append(f"{sid}: created_at not ISO-8601")
        for listkey in ("tags", "artifacts", "parent_ids"):
            value = n.get(listkey)
            if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
                findings.append(f"{sid}: {listkey} not a list of strings")

    # Referential integrity + topology: parents resolve in-file, DAG, one root.
    by_id = {n["node_id"]: n for n in nodes}
    roots = [n["slug_name"] for n in nodes if not n.get("parent_ids")]
    report["roots"] = roots
    if len(roots) != 1:
        findings.append(f"expected exactly one parentless root, found {len(roots)}")
    for n in nodes:
        for pid in n.get("parent_ids", []):
            if pid not in by_id:
                findings.append(f"{n['slug_name']}: dangling parent_id {pid}")

    seen, done = set(), set()

    def acyclic(nid, stack):
        if nid in done:
            return True
        if nid in stack:
            return False
        stack.add(nid)
        ok = all(
            acyclic(pid, stack)
            for pid in by_id[nid].get("parent_ids", [])
            if pid in by_id
        )
        stack.discard(nid)
        done.add(nid)
        return ok

    if not all(acyclic(nid, set()) for nid in by_id):
        findings.append("parent graph contains a cycle")

    # Content conventions the exports carry through from the node files.
    if kind == "state":
        statuses = {}
        for n in nodes:
            match = STATUS_RE.search(n.get("content", ""))
            if match:
                statuses[match.group(1)] = statuses.get(match.group(1), 0) + 1
                if match.group(1) not in SPEC_STATUSES:
                    findings.append(f"{n['slug_name']}: status {match.group(1)!r} outside SPEC I6")
            elif n.get("parent_ids"):
                findings.append(f"{n['slug_name']}: non-root state node without Status: line")
        report["status_histogram"] = dict(sorted(statuses.items()))
    else:
        impact_re = re.compile(r"^## State Impact\s*$", re.MULTILINE)
        with_impact = sum(1 for n in nodes if impact_re.search(n.get("content", "")))
        report["nodes_with_state_impact_section"] = with_impact
        report["nodes_without_state_impact_section"] = [
            n["slug_name"]
            for n in nodes
            if not impact_re.search(n.get("content", "")) and n.get("parent_ids")
        ]
    return report


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cache = Path(argv[0])
    out = None
    if "--json" in argv:
        out = Path(argv[argv.index("--json") + 1])
    report = {
        "probe": Path(__file__).name,
        "measured_at": datetime.now().astimezone().isoformat(),
        "exports": [
            probe_file(cache / "record.json", "record"),
            probe_file(cache / "state.json", "state"),
        ],
    }
    report["total_findings"] = sum(len(e["findings"]) for e in report["exports"])
    text = json.dumps(report, indent=2, sort_keys=False)
    if out:
        out.write_text(text + "\n")
        print(f"wrote {out} ({report['total_findings']} finding(s))")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
