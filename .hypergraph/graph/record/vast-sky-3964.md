---
node_id: d4cb9971-fc27-562a-85ae-5ed64fb85b2e
slug: vast-sky-3964
title: 'Decision: Hypergraph adoption path — epoch, adopt skill, mirror-verify, field dogfooding on a3go + tbinn'
created_at: '2026-08-07T19:59:19+00:00'
parents:
- green-field-8645
- patient-limit-9007
summary: 'Adoption path settled: epoch exemption for legacy history, fork-by-import (all-local default, split for scale), one-way mirror with push --verify, hypergraph-adopt skill + AGENTS.md block, 0.0.2 with skills install, dogfooding on a3go (mode A) and tbinn (mode B).'
flywheel:
  node_id: 7e9d61e9-20b4-5752-b3a6-24af11057248
  slug: little-pond-8702
  revision: 0
  pushed_at: '2026-08-07T20:03:23+00:00'
  content_sha256: 3261361dbffa1b37e81de3af4e79917db0b726492d4312ead6446a8ddb610dd1
---
## What

Settled the adoption path for bringing existing projects under Hypergraph (Operator directive, designed jointly with the agent): an epoch mechanism that exempts pre-adoption history from template compliance, a `hypergraph-adopt` skill covering both repos with a legacy Flywheel graph (mode A) and repos with only a codebase history (mode B), mirror drift detection via `push --verify`, a release (0.0.2) carrying `skills install`, and field dogfooding on two real repos: a3go and tbinn.

## Why

The frontier's field-dogfooding gap (bitter-sound-9744) needs real external projects, and both candidates have a past the protocol cannot currently absorb: a3go has a 67-node pre-hypergraph Flywheel graph plus rich in-repo result prose; tbinn has freshly pushed experiment work and no graph. Day-zero `hypergraph-init` has no answer for history — strict I2 enforcement over imported legacy nodes would produce hundreds of meaningless violations, and no conversion path means adoption would silently discard the very memory the protocol exists to keep.

## Method

Design discussion between Operator and agent. Decisions and their rejected alternatives:

- **Storage default: all-local import** of legacy graphs into node files. Epoch-split (marker as a parentless local root recording the archive lineage, older nodes left on the archive) is offered only as the scale option for huge graphs. Truncation was rejected outright — never discard history.
- **Fork = import.** Flywheel has no native graph fork (slugs are generated-on-create and immutable), so `hypergraph import` preserving node_ids/slugs verbatim *is* the fork; the original graph stays untouched as the frozen archive.
- **Epoch**: an "Adopted Hypergraph" decision record node marks the boundary; record nodes created strictly before the marker are exempt from I2/template compliance in `check`. Authoring-time validation is never epoch-exempted.
- **Mirror stays one-way** (local → Flywheel). Drift detection lands as `push --verify --against <export>`; a mirror-only slug legend node maps local↔flywheel slugs for readers without touching mirrored node bodies.
- **AGENTS.md onboarding**: idempotent sentinel-delimited block (≤15 lines) plus a full `.hypergraph/AGENTS.md`, with a contract-reconciliation step when an existing agent contract prescribes a conflicting discipline.
- **a3go (mode A)**: legacy public graph root `purple-fog-6345` (73d510e5-875e-59b2-ad07-f4711ee0b748, 67 nodes) plus the EXPANSION index anchor `proud-king-2753` (f9f2bf74-2ce6-5488-b471-dc0b6c422b99) — not writable by this account, so the mirror gets NEW Flywheel roots under this account and the legacy graph is referenced as the archive.
- **tbinn (mode B)**: young private repo, no graph; local backend + new mirror roots, prehistory authored from the just-pushed experiment work.

Known limitation accepted: **artifacts do not survive import** — the local backend has no artifact operation, so archived artifacts stay on the legacy Flywheel graph. This is why the `archive:` config reference is mandatory in mode A.

## Result

Adoption thrust opened with concrete milestones: M1 epoch support in the checker, M2 `push --verify` + slug legend, M3 `hypergraph-adopt` skill + AGENTS.md block, M4 release 0.0.2 with `skills install`, M5 adopt a3go (mode A), M6 adopt tbinn (mode B), M7 close the loop with a fresh-agent acceptance test in a3go. Protocol followed throughout: this decision node first, every milestone recorded, reconcile + mirror push at the end.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 4a624dc3e4f6baa6c647f05bb22be1319d276c73

## State Impact

- target: NEW adoption — open: the adoption path (epoch, adopt skill, push --verify, skills install release) is decided but unbuilt; M1–M7 milestones pending
- target: bitter-sound-9744 — concrete dogfooding targets chosen: a3go (mode A, 67-node legacy Flywheel graph as frozen archive, new mirror roots) and tbinn (mode B, ground-up prehistory); acceptance bar is the M7 fresh-agent loop
- target: weathered-union-7494 — 0.0.2 scoped: skills install subcommand plus templates/agents-block.md ship as package data in M4
