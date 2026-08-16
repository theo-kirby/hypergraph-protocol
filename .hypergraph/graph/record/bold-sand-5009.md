---
node_id: 60bea394-a44a-5e90-9d1c-07fdcb84c29c
slug: bold-sand-5009
title: 'Export contract measured: 0 findings, nine keys always present, topology closed in-file'
created_at: '2026-08-16T18:18:02+00:00'
parents:
- ancient-key-8524
summary: 'First empirical baseline of the JSON-export contract (.hypergraph/cache/{record,state}.json): stdlib-only probe finds 0 violations across 89 record + 25 state nodes; all nine node keys always present, parents resolve in-file, one root per export, statuses within SPEC I6.'
artifacts:
- .hypergraph/evidence/2026-08-16-export-contract-probe.py
- .hypergraph/evidence/2026-08-16-export-contract-baseline.json
flywheel:
  node_id: 24c8a8ac-ef82-5527-9f1f-42f071863922
  slug: summer-frost-3785
  revision: 1
  pushed_at: '2026-08-16T18:25:11+00:00'
  content_sha256: bf12de0a5cafabc274c3013682f8f639043040e30fed47d23d5eacdcda219b8c
  parents_sha256: 7e6443d1aa76c2c3fef74f05563b538681ae7a9d4a6f964d986bbc48d63139fe
  parents:
  - 90db657c-7c28-58f7-b039-042bf8baefc9
  artifacts_sha256: 4361c3f4fff134250c638d03372fc594d44100e412a582a2d5f6aab752281ee9
  artifacts:
  - path: .hypergraph/evidence/2026-08-16-export-contract-probe.py
    sha256: 9232583da1e6e6e1969927e1a74660069524cbe9048d8b6ffbec6bbf505e0946
    artifact_id: 073aecc0-18b2-5fa5-a552-74e1cec20e53
    uploaded_at: '2026-08-16T18:25:07.206219+00:00'
  - path: .hypergraph/evidence/2026-08-16-export-contract-baseline.json
    sha256: ad82c608e36758525633286e4a7dbe595972a074527e3f0782fa39f3bc50db05
    artifact_id: a00b7ba0-8a84-58ea-9f4c-8b6f567e8297
    uploaded_at: '2026-08-16T18:25:07.359588+00:00'
---
## What

Measured the JSON-export contract — `.hypergraph/cache/{record,state}.json`, the
integration surface the viz cut left behind as the whole seam — with a
reproducible, stdlib-only probe, and committed both the probe and the full JSON
baseline as evidence. The contract `polished-pond-2718` holds open now exists as
measured structure, not only as prose in backend/local-adapter.md.

## Why

Child of the dispatch claim `ancient-key-8524` (lane `falling-glacier-9058`,
target chosen: `polished-pond-2718`). The Visualization node is open because "the
capability is currently a contract whose consumer does not exist yet" — but a
consumer built against prose has nothing to conform to and nothing to detect
drift against. Pinning the observed schema and the structural guarantees down as
committed evidence gives hypergraph-viz a concrete baseline and gives future
exporter changes something to diff.

## Method

`python3 .hypergraph/evidence/2026-08-16-export-contract-probe.py
.hypergraph/cache --json
.hypergraph/evidence/2026-08-16-export-contract-baseline.json` at the lane commit
of this node. The probe is read-only, stdlib-only, and repo-independent: it reads
both exports, derives a key census (presence counts, observed JSON types), and
checks the guarantees a consumer would rely on — node_id/slug uniqueness and
format, ISO-8601 timestamps, in-file parent resolution, acyclicity, exactly one
parentless root, list-of-strings typing for tags/artifacts/parent_ids, the
state-only `Status:` convention against SPEC I6, and the record-side
`## State Impact` heading. Exit 0 always: it is a measurement, not a gate. The
JSON carries the full report; the probe is the definition of every number below.

## Result

**Both exports conform: 0 findings across 89 record nodes and 25 state nodes
(export version 1).** The measured contract, as a consumer can now rely on it:

- **Top level**: exactly `{version, exported_at, nodes}`; `version` is `1` in
  both files; `exported_at` is ISO-8601.
- **Every node carries all nine keys** — `node_id`, `slug_name`, `title`,
  `content`, `summary`, `tags`, `artifacts`, `parent_ids`, `created_at` — with
  stable types; no key is optional in either export. `node_id` is a lowercase
  UUID, `slug_name` matches `words-####`, both unique per file.
- **Topology is closed and clean in each file**: every `parent_ids` entry
  resolves within the same export, the parent graph is acyclic, and each export
  has exactly one parentless root. A renderer needs no cross-file joins to draw
  either graph.
- **Content conventions survive export**: all 24 non-root state nodes open with a
  `Status:` line and every status is inside the SPEC I6 set (17 working, 5 open,
  2 superseded, 1 root); 88 of 89 record nodes carry a `## State Impact` heading
  (the root is exempt).
- One probe defect found and fixed while measuring: a substring test for the
  impact section false-positives on the record root, whose *prose describes* the
  section template in backticks — the committed probe matches the markdown
  heading at line start instead. Structural claims about markdown bodies need
  line-anchored matches; the exports carry prose that mentions the very
  conventions being checked.

Evidence committed: `.hypergraph/evidence/2026-08-16-export-contract-probe.py`
(method), `.hypergraph/evidence/2026-08-16-export-contract-baseline.json` (full
report with per-key census). No core code was touched by this unit.

Dispatch closed: 1 unit(s) — JSON-export contract measured and baselined: 0 findings, nine always-present keys, closed in-file topology; the seam hypergraph-viz consumes is now empirical, not prose

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: lane/falling-glacier-9058
- commit: 54a0e9c6a32ea80f7f36de19800dad038e2f52c6

## State Impact

- target: polished-pond-2718 — new claim: the export contract the viz cut left as the seam is now measured, not prose — a committed stdlib-only probe plus JSON baseline (0 findings, 89+25 nodes, export version 1) shows nine always-present node keys, unique lowercase-UUID node_ids and words-#### slugs, in-file parent resolution with acyclic topology and exactly one root per export, SPEC-I6 statuses on all non-root state nodes; hypergraph-viz can conform to and drift-check against this baseline
