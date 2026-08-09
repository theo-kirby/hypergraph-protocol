#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# ///
"""Generate the `large` fixture: a synthetic graph at the viz's scale target.

~500 record nodes and ~60 state nodes, shaped like a real project rather than
like a random graph: a mostly-linear spine with a handful of concurrent branches
and the occasional merge, claims that cite the work they rest on, and an
unreconciled tail behind the high-water mark.

Deterministic (fixed seed), so regenerating produces byte-identical output and
the browser timing baseline stays comparable.

    tools/fixtures/large/generate.py        # rewrites record.json / state.json
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECORDS, STATES = 500, 60
SEED = 20260809

ADJ = ["ancient", "brisk", "calm", "damp", "eager", "faint", "gentle", "hollow",
       "idle", "jolly", "keen", "lively", "mellow", "noble", "old", "patient",
       "quiet", "rough", "still", "tender", "upper", "vast", "warm", "young"]
NOUN = ["anchor", "birch", "cliff", "dawn", "elm", "field", "grove", "harbor",
        "isle", "jetty", "kiln", "lake", "moss", "north", "orchard", "pine",
        "quarry", "ridge", "sound", "tide", "union", "vale", "willow", "yard"]


def slugger(rng, taken):
    def mint(n):
        while True:
            s = f"{ADJ[rng.randrange(len(ADJ))]}-{NOUN[rng.randrange(len(NOUN))]}-{n:04d}"
            if s not in taken:
                taken.add(s)
                return s
    return mint


def build():
    rng = random.Random(SEED)
    mint = slugger(rng, set())
    record_slugs = [mint(i) for i in range(RECORDS)]
    state_slugs = [mint(1000 + i) for i in range(STATES)]

    # State graph: a root, ~8 areas, the rest hung under an area.
    state_nodes = []
    statuses = ["working"] * 12 + ["open", "broken", "blocked", "superseded"]
    areas = state_slugs[1:9]
    for i, slug in enumerate(state_slugs):
        if i == 0:
            parents, status = [], None
        elif slug in areas:
            parents, status = [state_slugs[0]], statuses[rng.randrange(len(statuses))]
        else:
            parents, status = [areas[rng.randrange(len(areas))]], \
                statuses[rng.randrange(len(statuses))]
        state_nodes.append({"slug": slug, "parents": parents, "status": status,
                            "title": f"Component {i}" if i else "large fixture — state",
                            "prov": []})

    # Record graph: a spine with branches; every node declares an impact.
    hwm_at = int(RECORDS * 0.95)
    record_nodes = []
    tips = [0]
    for i, slug in enumerate(record_slugs):
        if i == 0:
            parents = []
        elif rng.random() < 0.10 and len(tips) > 1:          # merge two threads
            a, b = rng.sample(tips, 2)
            parents = [record_slugs[a], record_slugs[b]]
        elif rng.random() < 0.12:                            # branch off older work
            parents = [record_slugs[rng.randrange(max(1, i - 30), i)]]
        else:
            parents = [record_slugs[i - 1]]
        tips = ([t for t in tips if record_slugs[t] not in parents] + [i])[-6:]

        targets = rng.sample(state_slugs[1:], rng.choice([1, 1, 1, 2, 3]))
        impacts = "\n".join(f"- target: {t} — component {t[-4:]} advanced at step {i}"
                            for t in targets)
        record_nodes.append({
            "node_id": f"30000000-0000-4000-8000-{i:012d}",
            "slug_name": slug,
            "title": f"Step {i}: " + rng.choice([
                "measured the harness", "fixed a parser defect", "ran the sweep",
                "recorded a dead end", "landed the adapter", "tightened a bound",
                "reproduced the baseline", "cut the retry storm"]),
            "content": (f"## What\n\nUnit of work {i} in the synthetic fixture.\n\n"
                        f"## Why\n\nFollows the previous step.\n\n"
                        f"## Method\n\nSynthetic; see generate.py.\n\n"
                        f"## Result\n\nStep {i} completed.\n\n"
                        f"## State Impact\n\n{impacts}\n"),
            "parent_ids": [f"30000000-0000-4000-8000-{record_slugs.index(p):012d}"
                           for p in parents],
            # Monotonic in i: ~3 units of work a day over about six months.
            "created_at": f"2026-{1 + (i // 3) // 28:02d}-{1 + (i // 3) % 28:02d}T"
                          f"{9 + (i % 3) * 4:02d}:{(i * 7) % 60:02d}:00+00:00",
        })
        for t in targets:
            entry = next(s for s in state_nodes if s["slug"] == t)
            if len(entry["prov"]) < 14:
                entry["prov"].append(slug)

    out_state = []
    for i, s in enumerate(state_nodes):
        body = []
        if s["status"]:  # SPEC I6: the status line comes first, before any heading
            body.append(f"Status: {s['status']}")
        cites = "".join(f" [rec: {p}]" for p in s["prov"][:2])
        body.append(f"## Current\n\nComponent {i} of the synthetic fixture "
                    f"behaves as described.{cites}")
        body.append("## Negative knowledge\n\nNone yet.")
        if s["prov"]:
            body.append("## Provenance\n\n" + "\n".join(
                f"- {p} — contributed step evidence" for p in s["prov"]))
        if i == 0:
            body.append(f"## Reconciliation\n\n- high_water_mark: "
                        f"{record_nodes[hwm_at]['slug_name']}\n"
                        f"- reconciled_at: 2026-08-01T00:00:00+00:00")
        out_state.append({
            "node_id": f"40000000-0000-4000-8000-{i:012d}",
            "slug_name": s["slug"], "title": s["title"],
            "content": "\n\n".join(body) + "\n",
            "parent_ids": [f"40000000-0000-4000-8000-"
                           f"{state_slugs.index(p):012d}" for p in s["parents"]],
            "created_at": f"2026-01-{1 + i % 28:02d}T00:00:00+00:00",
        })
    return record_nodes, out_state


def main() -> int:
    record, state = build()
    for name, nodes in (("record", record), ("state", state)):
        (HERE / f"{name}.json").write_text(json.dumps(
            {"version": 1, "exported_at": "2026-08-09T00:00:00+00:00", "nodes": nodes},
            separators=(",", ":")) + "\n")
        print(f"wrote {name}.json ({len(nodes)} nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
