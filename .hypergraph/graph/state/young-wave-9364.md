---
node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
slug: young-wave-9364
title: Protocol spec
created_at: '2026-08-06T21:41:08.043466+00:00'
parents:
- cool-king-8586
summary: 'SPEC.md v0.0.4: invariants I1-I8, templates, forward-work conventions, adoption epochs, and Storage (files are the storage; INTERFACE.md is a portability contract, not a menu); working.'
flywheel:
  node_id: 3310b4b6-38dc-5091-b321-0a62ce235f80
  slug: young-wave-9364
  revision: 6
  pushed_at: '2026-08-09T12:28:31+00:00'
  content_sha256: cf012a2b99a30b7d0d352f93ff0fda49b458f94a70ad76d5f5f2d0f0f2dd0c63
---
Status: working

## Current

- SPEC.md defines the protocol: invariants I1–I8 (record-first, impact declaration, single-writer state, provenance, high-water mark, status vocabulary, negative knowledge, audit-grade rebuildability) plus skill-enforced conventions [rec: empty-cherry-5305]. Currently **v0.0.4**, and a packaging assertion ties the header to `pyproject.toml` — they had drifted, the spec saying v0.0.2 while the tool shipped 0.0.3 [rec: calm-sand-3399].
- Design foundation: record-first projection, impact-declaration + single-writer reconcile, markdown slug pointers (never cross-graph edges), append-only HWM, semantic (not byte) rebuildability [rec: spring-pine-7256].
- Templates pin exact checker-parseable headings for record nodes (What/Why/Method/Result/Repo/State Impact) and state nodes (Status line + Current/Negative knowledge/Provenance) [rec: empty-cherry-5305].
- Forward-work + Operator-directive conventions: open state nodes are gap-claims (falsified by work via I2), bets are immutable decision records, and directives enter through the record graph before reconcile opens the frontier gap [rec: patient-limit-9007].
- Adoption epochs: I2 carries an adoption-epoch exemption (record nodes created strictly before the config-named marker are legacy history, exempt from impact/template compliance at check time only), and a dedicated convention section defines the marker node, its parentage per mode (full-import: newest legacy node; mode B: newest prehistory node; epoch-split: parentless local root), and the no-truncation rule [rec: shady-quill-2790].
- **`## Backend` became `## Storage`**: the node files *are* the storage, and INTERFACE.md's ~10 operations are restated as a **portability contract** — what a replacement store would have to satisfy — rather than a menu chosen at init. Mirroring is named as optional, one-way, out of band, and explicitly something the skills do not know exists [rec: silver-ember-3035].
- The fork/mirror doctrine split cleanly along the same line: fork semantics, the frozen archive, and "artifacts do not travel" are protocol and stayed; mirror mechanics and failure modes moved to `backend/mirror.md`. A continuing graph is not a copy of the graph it forked from — lineage is content, belonging in a node body, never in a title [rec: silver-ember-3035].
- **Invariants I1–I8 were untouched by that change**, which is the evidence that the storage/protocol boundary was drawn in the right place: they were already storage-neutral, and only the framing around them named a backend [rec: silver-ember-3035].
- Node-file frontmatter is now described asymmetrically, because the two blocks are not peers: `origin:` is protocol (immutable import provenance), while a `flywheel:` block is bookkeeping that `push` writes and nothing else reads, `check` included [rec: silver-ember-3035].
- **Open gap: the protocol has no concurrency story.** I5's high-water mark is specified and implemented as a *timestamp* cutoff, which silently drops any record node authored before the last reconcile and merged after it — reproduced, with the checker reporting 0 unreconciled and 0 violations. A merge-aware protocol needs the mark to be an **ancestry frontier** over the causal DAG. Doctrine to add alongside it: contributors record, maintainers reconcile — which follows from I3 rather than extending it [rec: vast-rain-4873].
- **v0.0.5 closes the concurrency gap in the spec itself** [rec: placid-ridge-4035]. I5 is restated: the mark is a **frontier** of record tips, and a node is reconciled exactly when it is an ancestor of one of them. The old wording — "record nodes created after the HWM node are unreconciled" — was the defect written down, so fixing the code without fixing the sentence would have left the next implementer to rebuild it.
- A new **Collaboration** convention states the rule the invariants already implied: contributors record, the maintainer reconciles; publish from the default branch only; after a merge run `sync` rather than a bare `check`; never commit a conflict marker; and a repo fork is not a graph fork — forking a repository copies the graph verbatim and a PR merges back into it, while `import --fork` starts a new project and mints new identity [rec: placid-ridge-4035].
- The HWM vocabulary entry and the `## Reconciliation` template were updated with it, and the header is v0.0.5 [rec: placid-ridge-4035].

## Negative knowledge

None yet.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — the settled design decisions SPEC.md encodes
- empty-cherry-5305 — SPEC.md + all three templates landed (M1)
- patient-limit-9007 — forward-work + Operator-directive conventions added
- shady-quill-2790 — I2 adoption-epoch exemption + Adoption epochs convention
- silver-ember-3035 — Backend → Storage; fork/mirror doctrine split; I1–I8 confirmed storage-neutral
- calm-sand-3399 — version unified at 0.0.4 and pinned to pyproject by assertion
- vast-rain-4873 — parallel-work investigation: I5's timestamp cutoff is not merge-safe; collaboration doctrine to add
- placid-ridge-4035 — SPEC v0.0.5: I5 as an ancestry frontier, the Collaboration convention, fork disambiguation
