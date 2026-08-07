---
node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
slug: young-wave-9364
title: Protocol spec
created_at: '2026-08-06T21:41:08.043466+00:00'
parents:
- cool-king-8586
summary: SPEC.md with invariants I1-I8, templates, forward-work conventions, and adoption epochs (I2 exemption + marker parentage rules); working.
flywheel:
  node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
  slug: young-wave-9364
  revision: 3
  pushed_at: '2026-08-07T21:22:58+00:00'
  content_sha256: 6d42c27bb0482d19f3891d5ad85125df7117d854b5163e70877e82ce4ca18e31
---
Status: working

## Current

- SPEC.md defines the protocol: invariants I1–I8 (record-first, impact declaration, single-writer state, provenance, high-water mark, status vocabulary, negative knowledge, audit-grade rebuildability) plus skill-enforced conventions [rec: empty-cherry-5305].
- Design foundation: record-first projection, impact-declaration + single-writer reconcile, markdown slug pointers (never cross-graph edges), append-only HWM, semantic (not byte) rebuildability [rec: spring-pine-7256].
- Templates pin exact checker-parseable headings for record nodes (What/Why/Method/Result/Repo/State Impact) and state nodes (Status line + Current/Negative knowledge/Provenance) [rec: empty-cherry-5305].
- Forward-work + Operator-directive conventions: open state nodes are gap-claims (falsified by work via I2), bets are immutable decision records, and directives enter through the record graph before reconcile opens the frontier gap [rec: patient-limit-9007].
- Adoption epochs: I2 carries an adoption-epoch exemption (record nodes created strictly before the config-named marker are legacy history, exempt from impact/template compliance at check time only), and a dedicated convention section defines the marker node, its parentage per mode (full-import: newest legacy node; mode B: newest prehistory node; epoch-split: parentless local root), and the no-truncation rule [rec: shady-quill-2790].

## Negative knowledge

None yet.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — the settled design decisions SPEC.md encodes
- empty-cherry-5305 — SPEC.md + all three templates landed (M1)
- patient-limit-9007 — forward-work + Operator-directive conventions added
- shady-quill-2790 — I2 adoption-epoch exemption + Adoption epochs convention
