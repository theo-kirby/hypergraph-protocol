---
node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
slug: young-wave-9364
title: Graph structure
created_at: '2026-08-06T21:41:08.043466+00:00'
parents:
- cool-king-8586
summary: 'SPEC.md and the two-graph structure: invariants I1-I8, the conventions around them, and the record/state split as the whole idea. The two halves are this node''s children.'
flywheel:
  node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
  slug: young-wave-9364
  revision: 7
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: ad29cd7e2548fd18177c0911022e1c31f4d50928dc922a7a78a9d97b268b585d
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

SPEC.md is where the structure is written down: invariants I1–I8 — record-first, impact declaration, single-writer state, provenance, high-water mark, status vocabulary, negative knowledge, audit-grade rebuildability — plus the skill-enforced conventions and the exact checker-parseable templates for both node kinds [rec: empty-cherry-5305]. The design underneath them is a record-first projection with markdown slug pointers rather than cross-graph edges, an append-only mark, and semantic rather than byte rebuildability [rec: spring-pine-7256].

**Two graphs, and the split is the whole idea** — an append-only record of everything that happened, and a distilled projection of what is true now. The two children of this node are each half. No operation may create an edge between the roots; cross-graph pointers stay markdown [rec: spring-pine-7256].

- **Conventions around the invariants.** *Forward work*: an open state node is a gap-claim falsified by work through I2, a bet is an immutable decision record, and an Operator directive enters through the record graph before reconcile opens the gap [rec: patient-limit-9007]. *Adoption epochs*: I2 carries an exemption for legacy history, with the marker's parentage defined per mode and a no-truncation rule [rec: shady-quill-2790]. *Collaboration*: contributors record, the maintainer reconciles; publish from the default branch; a repo fork is not a graph fork [rec: placid-ridge-4035].
- **`## Backend` became `## Storage`**: the node files *are* the storage, and INTERFACE.md's ~10 operations are restated as a portability contract — what a replacement store would have to satisfy — rather than a menu chosen at init. Mirroring is named as optional, one-way, and explicitly something the skills do not know exists [rec: silver-ember-3035].
- **I1–I8 were untouched by that change**, which is the evidence the storage/protocol boundary was drawn in the right place: they were already storage-neutral, and only the framing around them named a backend [rec: silver-ember-3035]. The fork/mirror doctrine split along the same line — fork semantics and "artifacts do not travel" are protocol and stayed; mirror mechanics moved out [rec: silver-ember-3035].
- **I5 became an ancestry frontier in v0.0.5** [rec: placid-ridge-4035]. The old wording — "record nodes created after the HWM node are unreconciled" — was the concurrency defect written down, so fixing the code without fixing the sentence would have left the next implementer to rebuild it [rec: vast-rain-4873].
- The spec header is pinned to `pyproject.toml` by assertion, after the two drifted with SPEC saying v0.0.2 while the tool shipped 0.0.3 [rec: calm-sand-3399].

## Negative knowledge

None yet.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — the settled design decisions SPEC.md encodes
- empty-cherry-5305 — SPEC.md and all three templates landed (M1)
- patient-limit-9007 — forward-work and Operator-directive conventions added
- shady-quill-2790 — the I2 adoption-epoch exemption and its convention section
- silver-ember-3035 — Backend → Storage; the fork/mirror doctrine split; I1–I8 confirmed storage-neutral
- calm-sand-3399 — version unified and pinned to pyproject by assertion
- vast-rain-4873 — the reproduced concurrency defect: I5's timestamp cutoff is not merge-safe
- placid-ridge-4035 — SPEC v0.0.5: I5 as an ancestry frontier and the Collaboration convention
- late-sage-5549 — narrowed to the two-graph structure, with the record and state halves as children
