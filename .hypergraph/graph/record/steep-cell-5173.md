---
node_id: 62e98e5a-a54f-5eea-bfbf-d646a6b0b085
slug: steep-cell-5173
title: 'M5: dogfood cycle completed; cold-start orient test passed (4/6 calls)'
created_at: '2026-08-06T21:48:10.894067+00:00'
parents:
- spring-fog-0600
summary: Full self-host cycle green; cold-start orient in 4 calls; two integration fixes folded back.
flywheel:
  node_id: 62e98e5a-a54f-5eea-bfbf-d646a6b0b085
  slug: steep-cell-5173
  revision: 1
  pushed_at: '2026-08-07T18:12:00.956635+00:00'
  content_sha256: e13d270b2dc892c8f21c7b8714cbb5eee5e8625e4cb32fe939b19e6760d119b4
---
## What

Completed the M5 dogfood cycle on this repo: live init (both roots), retro-recording of design + M1–M4, a full reconcile pass, checker green over real exports, STATE.md committed, and a fresh-session cold-start orient test.

## Why

Acceptance milestone for v0.0.1, following directly from M4 (spring-fog-0600): the protocol had to survive contact with its own backend before we dogfood it on real research projects.

## Method

Init + record via commit_new_node (incl. one add_parent multi-parent edge); reconcile via get → acquire_stage_lease → commit_node (full payload, base_committed_revision) → release on four state nodes + the state root HWM advance; exports saved to .hypergraph/cache/ and fed to tools/hypergraph.py check + render. Cold-start test: a fresh agent with no prior context followed skills/hypergraph-orient/SKILL.md against the live graph.

## Result

Checker: 0 violations, 0 warnings, 0 unreconciled on the live project. Cold-start test passed with 4 Flywheel MCP calls against the ≤6 budget; frontier and provenance pointers correctly identified. Two integration findings: (1) flywheel_export_subgraph encodes parent edges as incoming_ids (not parent_ids) — checker normalization fixed in commit 9ecaa3b; (2) flywheel_get_node_tree with projection=full returns topology-only payloads — orient should use one flywheel_get_node_children page for component bodies instead (skill updated). Lease → commit → release recipes worked first try; no 409s or 429s observed.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: 9ecaa3b133222579967e5dfd6373fba66948872e

## State Impact

- target: bold-field-1268 — status open → working; full self-host cycle done, cold-start test passed 4/6 calls
- target: wandering-sun-8831 — new claim: checker normalizes the real export edge encoding (incoming_ids)
- target: dry-wildflower-2260 — new negative knowledge: get_node_tree projection=full is topology-only for orient; use get_node_children