---
node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
slug: young-wave-9364
title: Graph structure
created_at: '2026-08-06T21:41:08.043466+00:00'
parents:
- cool-king-8586
summary: 'SPEC.md and the graph structure: invariants I1-I8, the conventions around them, and the record/state split as the whole idea. At 0.0.13 the projection half generalizes to named views (I2 grammar, I3 per-view single writer, I5 per-view frontiers).'
flywheel:
  node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
  slug: young-wave-9364
  revision: 11
  pushed_at: '2026-08-19T10:25:52+00:00'
  content_sha256: c0960f2f896444a85b084864f94b97d72459c764c109e9d3ae4ca393577e6fe7
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

SPEC.md is where the structure is written down: invariants I1–I8 — record-first, impact declaration, single-writer state, provenance, high-water mark, status vocabulary, negative knowledge, audit-grade rebuildability — plus the skill-enforced conventions and the exact checker-parseable templates for both node kinds [rec: empty-cherry-5305]. The design underneath them is a record-first projection with markdown slug pointers rather than cross-graph edges, an append-only mark, and semantic rather than byte rebuildability [rec: spring-pine-7256].

**Two graphs, and the split is the whole idea** — an append-only record of everything that happened, and a distilled projection of what is true now. The two children of this node are each half. No operation may create an edge between the roots; cross-graph pointers stay markdown [rec: spring-pine-7256]. At 0.0.13 the projection half generalizes: a project may declare further **named views** of the same record graph (SPEC: Views), each a disjoint DAG with the state graph's template and its own reconciliation frontier — N+1 disjoint DAGs, same no-edges rule [rec: strong-star-9849].

- **Conventions around the invariants.** *Forward work*: an open state node is a gap-claim falsified by work through I2, a bet is an immutable decision record, and an Operator directive enters through the record graph before reconcile opens the gap [rec: patient-limit-9007]. *Adoption epochs*: I2 carries an exemption for legacy history, with the marker's parentage defined per mode and a no-truncation rule [rec: shady-quill-2790]. *Collaboration*: contributors record, the maintainer reconciles; publish from the default branch; a repo fork is not a graph fork [rec: placid-ridge-4035].
- **`## Backend` became `## Storage`**: the node files *are* the storage, and INTERFACE.md's ~10 operations are restated as a portability contract — what a replacement store would have to satisfy — rather than a menu chosen at init. Mirroring is named as optional, one-way, and explicitly something the skills do not know exists [rec: silver-ember-3035].
- **I1–I8 were untouched by that change**, which is the evidence the storage/protocol boundary was drawn in the right place: they were already storage-neutral, and only the framing around them named a backend [rec: silver-ember-3035]. The fork/mirror doctrine split along the same line — fork semantics and "artifacts do not travel" are protocol and stayed; mirror mechanics moved out [rec: silver-ember-3035].
- **I5 became an ancestry frontier in v0.0.5** [rec: placid-ridge-4035]. The old wording — "record nodes created after the HWM node are unreconciled" — was the concurrency defect written down, so fixing the code without fixing the sentence would have left the next implementer to rebuild it [rec: vast-rain-4873].
- **The Views section landed at 0.0.13** [rec: strong-star-9849]: I2's grammar gains view-qualified targets (`<view>/<slug>`, `<view>/NEW <kebab>`; unqualified still means state, so every existing record node keeps parsing), I3 is restated as single writer *per view*, and I5's `## Reconciliation` moves to every view root with independent marks. Invariant numbers are unchanged, per the Versioning section's own rule. The one documented compatibility edge: pre-0.0.13 `check` reports a qualified impact line as I2 unparseable, so a project that adds views needs ≥0.0.13 tooling — verified against the real published 0.0.12.
- **SPEC's Future-work section is deleted at the 0.1.0 gate** [rec: mellow-birch-2818]: its durable items already live as frontier state nodes, and the speculative list was weight; the slot is reserved for a Versioning section stating what a minor bump may change and what is stable.
- **The audit's SPEC drift is closed** [rec: lively-spring-9646] [rec: steady-rose-0661]: `check --since` is documented in Tooling as the PR gate; the enforced-set sentences now name the structural checks and branch-mode I1 (mechanical under `--since`); every stale `heal` spelling reads `upgrade --graph` and the alias promises are gone; no stale version headers remain outside the intentional I5 migration prose.
- **SPEC gained a Versioning section in Future-work's old slot** [rec: damp-meadow-9143]: a minor bump may tighten the checker (a rule that flags a correct live graph is a defect in the rule — the dogfood test is the standing net), reshape the CLI surface, and reword prose output; stable are invariant numbers (permanent, never reused — I5's v0.0.5 change as the precedent), exit codes 0/1/2 as a contract, the additive node-file format, and the export JSON shape.
- **What the audit had measured** [rec: lively-spring-9646]: `check --since` — the one mechanism that reaches a contributor who never read AGENTS.md — appears nowhere in SPEC's Tooling section; the enforced-set sentences underdescribe what branch mode enforces (I1 is mechanical under `--since`); the heal-vs-`upgrade --graph` contradiction spans five files; and the last section is still headed v0.0.5.
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
- lively-spring-9646 — the 0.1.0 audit: SPEC drift enumerated with line-level evidence
- mellow-birch-2818 — U7: the Future-work section deleted; the slot reserved for Versioning
- steady-rose-0661 — U9: the SPEC half of the drift sweep
- damp-meadow-9143 — U10: the Versioning section, and CHANGELOG as the sixth held version location
- strong-star-9849 — 0.0.13: the Views section; I2/I3/I5 generalized per view
