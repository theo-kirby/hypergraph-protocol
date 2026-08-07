---
node_id: be944979-3508-5583-b6b8-bd96106ca7f5
slug: empty-forest-6305
title: Git-native backend
created_at: '2026-08-07T10:57:13.256136+00:00'
parents:
- cool-king-8586
summary: 'Git-native backend live: node files are the source of truth; Flywheel a regenerable mirror (readable projection, not checkable).'
flywheel:
  node_id: be944979-3508-5583-b6b8-bd96106ca7f5
  slug: empty-forest-6305
  revision: 2
  pushed_at: '2026-08-07T18:23:46+00:00'
  content_sha256: 1102fd66e59b47ba5a5517f5e1287e9c33e76bfa8cfe1c5b01f4c9770e1ab6fc
---
Status: working

## Current

- The git-native backend exists and is this repo's live backend: markdown node files under `.hypergraph/graph/{record,state}/<slug>.md` are the source of truth, with `backend/local-adapter.md` mapping all 10 INTERFACE ops to CLI/file operations [rec: old-dawn-8747].
- Node format: YAML frontmatter (`node_id` = uuid5 of the slug, `slug`, `title`, `created_at`, `parents` as slugs, optional `flywheel:` mapping) over a body that is the node content byte-for-byte — so `check`/`render`/`viz` parse it unchanged [rec: old-dawn-8747].
- Integration surface is one file format and `export`: the checker, renderer and visualizer were not modified, because they only ever read the two JSON exports [rec: old-dawn-8747].
- Flywheel is now optional rather than load-bearing, and the two compose: `backend: local` + `mirror: flywheel` keeps files canonical and Flywheel a regenerable projection, refreshed by `push --plan` → skill executes → `push --record-result`; first live push applied 7 ops with no revision conflicts [rec: old-dawn-8747] [rec: kind-valley-8040].
- The sequencing bet in patient-limit-9007 — build-vs-defer decided only after field dogfooding — was overtaken: the adapter shipped first, so the interface was proven by a second implementation rather than by field use [rec: patient-limit-9007] [rec: old-dawn-8747].

## Negative knowledge

- [scope: mirroring a local graph to Flywheel | confidence: high | evidence: old-dawn-8747, kind-valley-8040] Flywheel mints its own slug on create, so nodes authored locally after the switch live there under a different slug while the markdown still cites the local one — `check` against a Flywheel export reported 25 dangling-pointer violations (I4/I5/I7) on a graph that checks 0/0 from the node files. The mirror is a readable projection, never the thing you check; slugs cross the boundary only through each file's `flywheel:` block.
- [scope: deferring slug translation on push | confidence: medium | evidence: kind-valley-8040] translation would make the mirror non-identical to source, breaking the byte-identical `content_sha256` change detector and forcing two-way translation on every update; the cost of *not* translating is now measured (above) rather than assumed.

## Provenance

- patient-limit-9007 — Operator directive opening this gap, with constraints and sequencing
- old-dawn-8747 — the adapter, the CLI subcommands, and this repo's migration onto it
- kind-valley-8040 — first live mirror push; measured mirror-consistency limits
