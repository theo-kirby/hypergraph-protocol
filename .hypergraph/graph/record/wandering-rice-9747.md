---
node_id: d55fdaca-9e20-5151-9065-800d4b505553
slug: wandering-rice-9747
title: Project initialized under Hypergraph (self-hosted)
created_at: '2026-08-06T21:41:00.746691+00:00'
parents:
- autumn-tooth-6046
summary: Created both Hypergraph roots for this repo and seeded a five-component state skeleton.
flywheel:
  node_id: d55fdaca-9e20-5151-9065-800d4b505553
  slug: wandering-rice-9747
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 8d21cb6f55288035126e87eab8f49ff31da74467d087d233f02befd013dfe349
  parents_sha256: b2e5a46860b07ca823ed056badfe662ae46bf2cbc7a5d3a67330b3939fff7600
  parents:
  - cdbea53e-8865-5138-b033-948b4690daf3
---
## What

Initialized the hypergraph repo under its own protocol: created the record root (autumn-tooth-6046) and state root (cool-king-8586), chose the state-graph architecture, and seeded the state skeleton.

## Why

v0.0.1 milestone M5 (dogfood): the protocol repo must be its own first user. First child of the record root — the project's opening workstream.

## Method

Followed skills/hypergraph-init/SKILL.md against live Flywheel MCP. Architecture chosen to mirror the repo layout, five components: protocol-spec (SPEC.md + templates), backend-adapter (backend/INTERFACE.md + flywheel-adapter.md), checker-tooling (tools/hypergraph.py + tests), skills (skills/hypergraph-* + install.sh), dogfooding (this M5 cycle: self-hosted graphs, STATE.md, cold-start orient test).

## Result

Both roots exist and are disjoint DAGs; state skeleton seeded with Status: open nodes; .hypergraph/config.yml written to the repo.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: d87733881f9c0fb5063b047ab6bb9498cdd7e558

## State Impact

- target: NEW protocol-spec — seeded, status open: SPEC.md invariants I1–I8 + node templates
- target: NEW backend-adapter — seeded, status open: abstract backend interface + Flywheel MCP adapter recipes
- target: NEW checker-tooling — seeded, status open: invariant checker + STATE.md renderer + fixture tests
- target: NEW skills — seeded, status open: init/record/reconcile/orient skills + installer
- target: NEW dogfooding — seeded, status open: self-hosting cycle incl. cold-start orient test