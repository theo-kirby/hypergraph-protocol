---
node_id: 6efe06c3-744b-535d-be9e-ca44a4de9c9c
slug: spring-pine-7256
title: 'Decision: two-graph protocol design settled'
created_at: '2026-08-06T21:41:54.449860+00:00'
parents:
- wandering-rice-9747
summary: Settled record-first, impact-declaration/single-writer-reconcile, markdown pointers, HWM, and audit-grade rebuildability.
flywheel:
  node_id: 6efe06c3-744b-535d-be9e-ca44a4de9c9c
  slug: spring-pine-7256
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: b2ab0fbd136343485cc0d896058076e007a1b692cba3c24d5143588c09d74278
  parents_sha256: be55eee15b7eb4a104dc07d1c1283331c1988f6a962f7abe9f0b53a104303ea2
  parents:
  - d55fdaca-9e20-5151-9065-800d4b505553
---
## What

Settled the core Hypergraph protocol design with the user before implementation.

## Why

Flywheel records history well but orients fresh agents badly; the design had open questions (derivability, write contention, cross-graph linking) that had to be decided before writing SPEC.md. Follows directly from project init.

## Method

Design discussion against the Flywheel contract (flywheel_get_contract + graph/stage_commit sections) and its skill ecosystem.

## Result

Decisions: (1) record-first — state is a projection, never the primary home of knowledge; (2) impact declaration on every record node + a single-writer reconcile pass, instead of inline state writes, to avoid stage-lease contention and weakest-agent drift; (3) cross-graph pointers are structured markdown slugs, never graph edges (edges would topologically merge the DAGs); (4) append-only record graph enables a high-water mark for idempotent reconciliation; (5) "rebuildable" means audit-grade semantic equivalence on re-derivation, not byte determinism; (6) negative-knowledge generalizations require their own decision record; (7) state topology mirrors architecture, record topology stays causal.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: d87733881f9c0fb5063b047ab6bb9498cdd7e558

## State Impact

- target: young-wave-9364 — design settled; SPEC.md can encode decisions 1–7 as invariants I1–I8