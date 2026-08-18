---
node_id: b1395120-e8a8-5a28-a431-ef93d8a66b90
slug: falling-snow-3475
title: 'U2: guarded export loading and chronological timestamp ordering'
created_at: '2026-08-18T11:47:49+00:00'
parents:
- humble-mist-8524
summary: ''
flywheel:
  node_id: 5d2c9096-1fbd-5d20-85d2-578505175e58
  slug: old-limit-4068
  revision: 0
  pushed_at: '2026-08-18T11:47:52+00:00'
  content_sha256: b81b3df3d987cdd7b8374d195d59a0d40aadaea5fe0e01afaf5b32beb4f98195
  parents_sha256: 76a2caf4e4fb7dd8f442467c751da7277f821a271a7fe2cf9c04ebd03c730c68
  parents:
  - 81d8d133-363b-5dae-8564-8ceec0c3f036
---
## What

U2 of the 0.1.0 gate: export loading is guarded, and every ordering over `created_at` is chronological rather than lexicographic.

## Why

The audit found two silent-failure paths. First: `check` against a missing or truncated export died with a raw traceback out of `read_text`/`json.loads` — the same failure shape that cost two arm-C benchmark runs their config, since nothing named the gitignored cache as the problem. Second: `created_at` sorts compared raw strings, so `Z` and `+00:00` spellings of the same instant — or a non-UTC offset — shuffled siblings in the export, the unreconciled enumeration, topological order, and STATE.md rendering.

## Method

- New `load_export_json(path, *, what)` raises `LocalGraphError` (main's existing handler → exit 2) naming the file, noting the cache is gitignored, and printing the regenerating command — message modeled on `load_config`. Used by `load_graph`, `_load_export_nodes`, and `side_from_export`; the three duplicated export-shape normalizations fold into `_normalize_export_nodes`.
- New `created_key(created_at, tiebreak)` = `(parse_ts(...) or datetime.min-UTC, created_at, tiebreak)` — chronological, total, deterministic; unparseable stamps sort first by raw text. Applied at the five sites: `export_graph_json`, `unreconciled_nodes`, `topo_order`, `render_state` child sort, `suggest_frontier`.

## Result

5 new tests: missing and truncated exports exit 2 with the actionable message; `created_key` unit-pinned; a `+09:00`-spelled sibling orders correctly through both `export_graph_json` and `unreconciled_nodes` where raw strings sort the other way. Suite 313 → 318 passed, 2 skipped; `sync` 0 violations, `push --verify` 0 drift.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: d8dd8af553e0ba0a1edac84afeb89193ce970eae

## State Impact

- target: wandering-sun-8831 — export loading fails with an instruction (exit 2) instead of a traceback; all created_at orderings are chronological across Z/+00:00/offset spellings
