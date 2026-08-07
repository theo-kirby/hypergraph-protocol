---
node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
slug: young-wave-9364
title: Protocol spec
created_at: '2026-08-06T21:41:08.043466+00:00'
parents:
- cool-king-8586
summary: SPEC.md with invariants I1-I8, templates, and forward-work conventions; working.
flywheel:
  node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
  slug: young-wave-9364
  revision: 2
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: 9c4d93cda92abb27aabc2a512b6946af907d611fe514ce763918fed749eb929c
---
Status: working

## Current

- SPEC.md defines the protocol: invariants I1–I8 (record-first, impact declaration, single-writer state, provenance, high-water mark, status vocabulary, negative knowledge, audit-grade rebuildability) plus skill-enforced conventions [rec: empty-cherry-5305].
- Design foundation: record-first projection, impact-declaration + single-writer reconcile, markdown slug pointers (never cross-graph edges), append-only HWM, semantic (not byte) rebuildability [rec: spring-pine-7256].
- Templates pin exact checker-parseable headings for record nodes (What/Why/Method/Result/Repo/State Impact) and state nodes (Status line + Current/Negative knowledge/Provenance) [rec: empty-cherry-5305].
- Forward-work + Operator-directive conventions: open state nodes are gap-claims (falsified by work via I2), bets are immutable decision records, and directives enter through the record graph before reconcile opens the frontier gap [rec: patient-limit-9007].

## Negative knowledge

None yet.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — the settled design decisions SPEC.md encodes
- empty-cherry-5305 — SPEC.md + all three templates landed (M1)
- patient-limit-9007 — forward-work + Operator-directive conventions added