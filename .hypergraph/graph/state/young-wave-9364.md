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
  revision: 4
  pushed_at: '2026-08-09T11:42:29+00:00'
  content_sha256: 7a8bf39e46dd574188801b31b131a24065d52be1ba657d7dd658de9d6a11f10f
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
