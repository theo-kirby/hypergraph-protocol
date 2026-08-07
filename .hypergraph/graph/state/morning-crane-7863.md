---
node_id: 5683b425-7e64-5829-8b78-6a69b75220f2
slug: morning-crane-7863
title: Adoption
created_at: '2026-08-07T20:01:01+00:00'
parents:
- cool-king-8586
summary: 'Adoption thrust open: epoch mechanism, hypergraph-adopt skill (modes A/B), push --verify, 0.0.2 skills install — decided, M1–M7 pending.'
flywheel:
  node_id: 67d32718-3dcf-5321-978a-212599c531b4
  slug: long-hall-1227
  revision: 0
  pushed_at: '2026-08-07T20:03:23+00:00'
  content_sha256: a6d92e2ad789fc69de2b2741b708bb314cdf339dbeed7e07868ce52078deea25
---
Status: open

## Current

Status: open

## Current

- The adoption path for projects with a past is decided but unbuilt [rec: vast-sky-3964]: an epoch mechanism (record nodes created strictly before an "Adopted Hypergraph" marker are exempt from I2/template compliance in `check`; authoring-time validation is never exempted), a `hypergraph-adopt` skill (mode A: import an existing Flywheel graph; mode B: author prehistory from repo history), `push --verify` drift detection with a mirror-only slug legend, and release 0.0.2 carrying `hypergraph skills install`.
- Storage default is all-local import of legacy graphs; epoch-split (marker as a parentless local root recording the archive lineage) is offered only as the scale option for huge graphs; truncation rejected outright [rec: vast-sky-3964].
- Fork = import: Flywheel has no native graph fork (slugs are generated-on-create, immutable), so `hypergraph import` preserving node_ids/slugs verbatim is the fork; the original graph stays untouched as the frozen archive [rec: vast-sky-3964].
- Milestones pending [rec: vast-sky-3964]: M1 epoch checker support, M2 push --verify + slug legend, M3 adopt skill + AGENTS.md sentinel block, M4 release 0.0.2, M5 a3go adoption (mode A), M6 tbinn adoption (mode B), M7 fresh-agent acceptance loop.

## Negative knowledge

- [scope: importing legacy Flywheel graphs into the local backend | confidence: high | evidence: vast-sky-3964 | decision: vast-sky-3964] Artifacts do not survive import — the local backend has no artifact operation, so archived artifacts stay on the legacy Flywheel graph; the `archive:` config reference is mandatory in mode A for this reason.

## Provenance

- vast-sky-3964 — Operator directive opening the adoption thrust; settled epoch design, fork-by-import, storage default, mirror policy, AGENTS.md approach, and both dogfooding targets

## Negative knowledge

None yet.

## Provenance

- vast-sky-3964 — Operator directive opening the adoption thrust
