#!/usr/bin/env python3
"""Measure the size and shape of a Hypergraph state graph.

Evidence tool for soft-hill-6082 (State graph): the deferred `check` rule for
state-graph size and shape needs measured baselines, and prose conventions
measured by nothing are not constraints (late-sage-5549). This script turns
"readable in one sitting" into numbers, from the node files alone.

Stdlib only, read-only, no repo imports — runs on any checkout:

    python3 2026-08-16-state-shape-measure.py <state-root-dir> [--json OUT]

Per node: body bytes (content after frontmatter), file bytes, bullet count
(list items at any indent), word count, status, depth from the graph root,
provenance/negative-knowledge entry counts. Aggregates: totals, means, maxima,
depth histogram, status histogram, frontier share, and an estimated reading
time at 200 wpm — the "one sitting" proxy.
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

BULLET_RE = re.compile(r"^\s*[-*] ")
STATUS_RE = re.compile(r"^Status:\s*(\S+)", re.MULTILINE)
READING_WPM = 200


def split_frontmatter(text):
    """Return (frontmatter_lines, body_text). Body = content after closing ---."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return [], text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1:])
    return [], text


def parse_parents(fm_lines):
    parents, in_parents = [], False
    for line in fm_lines:
        if line.startswith("parents:"):
            in_parents = True
            continue
        if in_parents:
            m = re.match(r"^- (\S+)$", line.strip())
            if m and not line.startswith(" " * 2 + " "):  # top-level list item
                parents.append(m.group(1))
                continue
            if not line.startswith("-") and not line.startswith(" -"):
                in_parents = False
    return parents


def section_entry_count(body, heading):
    """Count top-level bullets inside a given ## section."""
    in_section, count = False, 0
    for line in body.split("\n"):
        if line.startswith("## "):
            in_section = line.strip() == f"## {heading}"
            continue
        if in_section and BULLET_RE.match(line) and not line.startswith("  "):
            count += 1
    return count


def measure_node(path):
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    m = STATUS_RE.search(body)
    words = len(body.split())
    return {
        "slug": path.stem,
        "file_bytes": len(text.encode("utf-8")),
        "body_bytes": len(body.encode("utf-8")),
        "words": words,
        "bullets": sum(1 for l in body.split("\n") if BULLET_RE.match(l)),
        "status": m.group(1) if m else None,
        "parents": parse_parents(fm),
        "provenance_entries": section_entry_count(body, "Provenance"),
        "negative_knowledge_entries": section_entry_count(body, "Negative knowledge"),
    }


def depths(nodes):
    """Depth from the root (node with no parents inside the graph)."""
    by_slug = {n["slug"]: n for n in nodes}
    memo = {}

    def depth(slug, seen=()):
        if slug in memo:
            return memo[slug]
        node = by_slug.get(slug)
        if node is None or slug in seen:
            return 0
        internal = [p for p in node["parents"] if p in by_slug]
        d = 0 if not internal else 1 + min(depth(p, seen + (slug,)) for p in internal)
        memo[slug] = d
        return d

    for n in nodes:
        n["depth"] = depth(n["slug"])
    return nodes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state_root", type=Path)
    ap.add_argument("--json", type=Path, help="write full JSON report here")
    args = ap.parse_args()

    files = sorted(args.state_root.glob("*.md"))
    if not files:
        sys.exit(f"no .md node files under {args.state_root}")
    nodes = depths([measure_node(p) for p in files])

    body_kb = [n["body_bytes"] / 1024 for n in nodes]
    total_words = sum(n["words"] for n in nodes)
    statuses = {}
    depth_hist = {}
    for n in nodes:
        statuses[n["status"]] = statuses.get(n["status"], 0) + 1
        depth_hist[n["depth"]] = depth_hist.get(n["depth"], 0) + 1
    frontier = [n for n in nodes if n["status"] in ("open", "broken", "blocked")]

    report = {
        "state_root": str(args.state_root),
        "node_count": len(nodes),
        "total_body_kb": round(sum(body_kb), 1),
        "total_file_kb": round(sum(n["file_bytes"] for n in nodes) / 1024, 1),
        "total_words": total_words,
        "reading_minutes_at_200wpm": round(total_words / READING_WPM, 1),
        "body_kb_mean": round(statistics.mean(body_kb), 2),
        "body_kb_median": round(statistics.median(body_kb), 2),
        "body_kb_max": round(max(body_kb), 2),
        "bullets_max": max(n["bullets"] for n in nodes),
        "status_histogram": statuses,
        "frontier_count": len(frontier),
        "frontier_share": round(len(frontier) / len(nodes), 2),
        "depth_histogram": {str(k): v for k, v in sorted(depth_hist.items())},
        "max_depth": max(depth_hist),
        "top_nodes_by_body_kb": [
            {"slug": n["slug"], "body_kb": round(n["body_bytes"] / 1024, 2),
             "bullets": n["bullets"], "status": n["status"], "depth": n["depth"]}
            for n in sorted(nodes, key=lambda n: -n["body_bytes"])[:5]
        ],
        "nodes": sorted(nodes, key=lambda n: -n["body_bytes"]),
    }

    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    summary = {k: v for k, v in report.items() if k != "nodes"}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
