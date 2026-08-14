---
node_id: ab4e2f97-9989-5366-813e-827466807faf
slug: empty-cherry-5305
title: 'M1: SPEC.md and node templates written'
created_at: '2026-08-06T21:42:07.550698+00:00'
parents:
- spring-pine-7256
summary: Protocol spec with invariants I1-I8 and checker-parseable node templates.
flywheel:
  node_id: ab4e2f97-9989-5366-813e-827466807faf
  slug: empty-cherry-5305
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: d98b283c7848328a52b7c143ea0485a6ed052a1ecac6440ffe35fde6c049c119
  parents_sha256: c5d05b9e91d876a30d82f13c026b2ea6f7cfac873d86f59556f219948e972fec
  parents:
  - 6efe06c3-744b-535d-be9e-ca44a4de9c9c
---
## What

Wrote SPEC.md — the protocol as eight numbered invariants (I1 record-first, I2 impact declaration, I3 single-writer state, I4 provenance, I5 high-water mark, I6 status vocabulary, I7 negative knowledge, I8 audit-grade rebuildability) plus skill-enforced conventions — and the three templates (record-node.md, state-node.md, config.example.yml).

## Why

Direct encoding of the settled design decisions (spring-pine-7256); everything downstream (checker, skills) is written against these invariant IDs.

## Method

Invariants split into mechanically checkable (I2, I4–I7 — enforced by tools/hypergraph.py) vs procedural (I1, I3, I8 — enforced by skills, with checker proxies). Templates pin exact `##` headings so node content parses deterministically: record nodes What/Why/Method/Result/Repo/State Impact; state nodes a Status: first line + Current/Negative knowledge/Provenance. Frontier defined as status ∈ {open, broken, blocked}.

## Result

SPEC.md and templates/ landed in commit d877338. Impact-line grammar: `- target: <state-slug or NEW name> — <delta>` or `none: <reason>`; negative-knowledge entries `[scope | confidence | evidence | optional decision]`.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: d87733881f9c0fb5063b047ab6bb9498cdd7e558

## State Impact

- target: young-wave-9364 — status open → working; SPEC.md invariants I1–I8 + conventions + all three templates landed