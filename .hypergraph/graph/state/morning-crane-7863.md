---
node_id: 5683b425-7e64-5829-8b78-6a69b75220f2
slug: morning-crane-7863
title: Adoption
created_at: '2026-08-07T20:01:01+00:00'
parents:
- cool-king-8586
summary: 'Adoption thrust delivered end-to-end: epoch mechanism, adopt skill, verify+legend+lineage, fork-import, a3go+tbinn adopted and mirrored in full, acceptance loop held, 0.0.2 published.'
flywheel:
  node_id: 67d32718-3dcf-5321-978a-212599c531b4
  slug: long-hall-1227
  revision: 2
  pushed_at: '2026-08-07T22:07:22+00:00'
  content_sha256: f9cf3577a135bc91fc9e7d5a1ee9126c10e66a1681018bd2f42e4cb16da2601b
---
Status: working

## Current

- The adoption path is built, shipped, and field-proven end-to-end. Settled design held throughout: all-local import default, epoch-split only for scale, fork = import (slugs immutable), one-way mirror, artifacts stay on the archive [rec: vast-sky-3964].
- Epoch mechanism live: `epoch.marker` in config; `check` exempts record nodes created strictly before the marker from I2 (authoring-time validation never exempted; unresolvable marker is itself a violation); parentage rules per mode — full-import marker parents on the newest legacy node, mode B on the newest prehistory node, epoch-split marker is a parentless local root [rec: shady-quill-2790] [rec: stormy-dew-2969].
- Mirror integrity closed: `push --verify --against <export>` detects missing nodes, body-hash and summary drift, and revision skew; a mirror-only slug legend node is regenerated on every push; verify exempts config-declared `mirror_roots` (gap found live on a3go) [rec: careful-harbor-3902] [rec: humble-clover-7048].
- hypergraph-adopt skill shipped (mode A: import-as-fork with mandatory `archive:`; mode B: authored prehistory), with distillation guidance (per-branch subagent mining, id-prefix→slug resolution, honest statuses, user interview), the idempotent sentinel AGENTS.md block with contract reconciliation, and full `.hypergraph/AGENTS.md` onboarding [rec: late-isle-6483].
- Release 0.0.2 built with `hypergraph skills install` (skills + agents-block as package data) [rec: crisp-lake-4496] and now published to PyPI and verified from the public index — skills install works via uvx and the published CLI checks both adopted repos clean; the adopter onboarding pins on the dev checkout are removed [rec: rough-reef-5869].
- Field adoptions landed: a3go mode A (108-node legacy graph imported verbatim, 107 nodes epoch-exempt, check 0/0, verified mirror on fresh roots with the legacy graph frozen as archive) [rec: humble-clover-7048]; tbinn mode B (authored prehistory, frontier honestly led by a broken node, full mirror verified) [rec: stormy-dew-2969].
- Fork-import closed the last gap in the thrust: a full import **is** a fork, so the project re-publishes its whole imported history to a mirror it owns. `import --fork` files the archive's ids under `origin:` and omits `flywheel:`; `push --lineage` puts the archive lineage in the mirror record root's body; verification runs against the project's own roots alone. Shipped with tests, docs and skills [rec: copper-moss-3669] [rec: tender-moss-3792], then proven live on a3go — 108 creates, topology restored by re-parenting, `push --verify` exit 0 against the mirror alone [rec: northern-willow-0469].
- Acceptance test passed: a fresh agent with no protocol context completed the full loop in a3go — orient in 6 calls, genuine frontier work (GEO-1 precondition: d=1 boards proven exactly 2D Go, corner-flip endpoint measured), causally-parented record, no state writes, librarian reconcile, mirror verify clean — zero protocol violations [rec: fond-tree-4727].

## Negative knowledge

- [scope: importing legacy Flywheel graphs into the local backend | confidence: high | evidence: vast-sky-3964 | decision: vast-sky-3964] Artifacts do not survive import — the local backend has no artifact operation, so archived artifacts stay on the legacy Flywheel graph; the `archive:` config reference is mandatory in mode A for this reason, and the mirror record root now states the loss explicitly via `push --lineage`.
- [scope: adopting a graph you do not own | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] preserving the source node_ids as the *push target* silently orphans the whole imported history: the nodes are on Flywheel, on a graph another account owns, so push omits them and the project's own mirror stays a stub. Provenance and push target must be separate fields, and mirror verification must never include the archive in its export.

## Provenance

- vast-sky-3964 — Operator directive opening the adoption thrust; settled epoch design, fork-by-import, storage default, mirror policy, AGENTS.md approach, and both dogfooding targets
- shady-quill-2790 — M1: epoch support in the checker
- careful-harbor-3902 — M2: push --verify + slug legend, live-proven
- late-isle-6483 — M3: hypergraph-adopt skill + agents-block template
- crisp-lake-4496 — M4: 0.0.2 built with skills install; publish blocked on credentials
- humble-clover-7048 — M5: a3go adopted (mode A)
- stormy-dew-2969 — M6: tbinn adopted (mode B); mode-B marker rule corrected
- fond-tree-4727 — M7: fresh-agent acceptance loop held
- rough-reef-5869 — 0.0.2 published; adopters un-pinned; thrust tail closed
- copper-moss-3669 — fork-import direction opened: adopted projects mirror their full history
- tender-moss-3792 — fork-import shipped (tooling, docs, skills)
- northern-willow-0469 — a3go migrated live; fork-import field-proven
