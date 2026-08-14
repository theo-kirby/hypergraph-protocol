---
node_id: 31dc7dde-666d-527e-806f-4ba4dd119cc1
slug: crimson-dawn-7137
title: 'M2: backend interface + Flywheel adapter written'
created_at: '2026-08-06T21:42:19.541675+00:00'
parents:
- empty-cherry-5305
summary: Abstract backend ops + concrete Flywheel MCP recipes incl. lease/409/429 handling.
flywheel:
  node_id: 31dc7dde-666d-527e-806f-4ba4dd119cc1
  slug: crimson-dawn-7137
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 6de499cc16354ac346056ac6da9abebcc83152a34266df04fd697cad80568094
  parents_sha256: 9f344c17316cf00f0774ac2b3c7e34c7abc2c4e31b63474bbeca2b7bafa7bd6f
  parents:
  - ab4e2f97-9989-5366-813e-827466807faf
---
## What

Wrote backend/INTERFACE.md (10 abstract operations the skills are written against) and backend/flywheel-adapter.md (operation → Flywheel MCP call recipes).

## Why

SPEC.md (empty-cherry-5305) leaves the graph store abstract so a git-native backend can be a drop-in second adapter; v0.0.1 needs the one concrete mapping to Flywheel.

## Method

Ops: create_root, append_record_node, read_node, list_children, get_tree, resolve_slug, update_state_node, export_graph, attach_artifact (opt), tag (opt). Recipes verified against the live Flywheel contract (flywheel_get_contract sections graph + stage_commit): commit_new_node payload shape incl. six required repo_context keys; update_state_node = get → acquire_stage_lease → commit_node (full staged payload, base_committed_revision) → release; export via flywheel_export_subgraph include_descendants; 409 and 429 handling; write limits (120 creates/min, 2000/day, 120 graph-writes/min).

## Result

Both documents landed in commit d877338. Notable constraint recorded: cross-graph pointers must stay markdown — no adapter op creates edges between the two roots.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: d87733881f9c0fb5063b047ab6bb9498cdd7e558

## State Impact

- target: blue-sun-8921 — status open → working; INTERFACE.md (10 ops) + flywheel-adapter.md recipes landed