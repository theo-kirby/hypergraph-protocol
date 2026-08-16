---
node_id: 1c02dca8-cf41-5140-aa4b-25dc180a95f2
slug: vast-birch-5192
title: 'Operator directive: the release is 0.0.11, not 0.9.0'
created_at: '2026-08-16T18:33:38+00:00'
parents:
- shady-garden-2130
summary: ''
flywheel:
  node_id: cffd8cd9-d1f4-5414-9784-6aeb4ba6e412
  slug: bitter-truth-5079
  revision: 0
  pushed_at: '2026-08-16T18:35:51+00:00'
  content_sha256: 5dffa7ff5fba5f25baad3035eb468995bf9a37d64d69a6fe2861e4b56e3a6030
  parents_sha256: a049161df22931401574c3d950cef6df2f815be9742484b3cdd8096f298bd639
  parents:
  - e37eab9a-7362-53d9-959b-eb69d77222e7
---
## What

Operator directive: the clean-slate release ships as **0.0.11**, not 0.9.0.
Every stamp and mention outside the append-only graph history moved in one
commit: pyproject, `__version__`, the SPEC header, both config stamps, the
`heal`-alias deprecation text (now "through the 0.0.x series"), the
`SHIPPED_BLOCK_DIGESTS` comment, both healers' `since=`, and the test-section
comments. Record nodes that say 0.9.0 stay as written — they are history, and
this node is the correction that supersedes their version label.

## Why

The Operator named the version. 0.0.11 keeps the release inside the 0.0.x
series the project has published all along (0.0.1–0.0.8 are live on the index;
0.0.9 was staged and never published, 0.0.10 was never used). Everything else
about the release — dispatch, the mirror split, the upgrade fold — is
unchanged; only the label moves.

## Method

Scripted replace with per-site assertions (pyproject.toml, SPEC.md,
tools/hypergraph.py, tests/test_heal.py, .hypergraph/config.yml,
templates/config.example.yml), then a grep proving no `0.9.0`/`0.9.x` remains
outside `.hypergraph/graph/`. The four version-parity tests enforce the stamps
agree.

## Result

`uv run pytest tests/` — 302 passed, 2 skipped. `hypergraph --version` →
`hypergraph-protocol 0.0.11`.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 17ca716bb98628a9ae8c2e3ae5b618ccf9ee4b98

## State Impact

- target: odd-birch-3808 — the staged release is 0.0.11 (0.9.0 was a label that never shipped; 0.0.9 and 0.0.10 were never published); every state-node mention of 0.9.0 reads as 0.0.11
- target: wandering-sun-8831 — version label: the fold, split and dispatch ship at 0.0.11; the heal alias lives through the 0.0.x series
- target: retroactive-repair-5104 — version label 0.9.0 → 0.0.11 in the fold claim
- target: fond-sail-3288 — version label 0.9.0 → 0.0.11 (upgrade --graph, block digest)
- target: empty-forest-6305 — version label 0.9.0 → 0.0.11 (mirror module)
- target: gilded-vale-8087 — version label 0.9.0 → 0.0.11 (dispatch and lanes)
- target: dry-wildflower-2260 — version label 0.9.0 → 0.0.11 (sixth skill)
- target: hollow-rain-8997 — version label 0.9.0 → 0.0.11 (dispatch falsifies the no-auto-run-skill claim)
