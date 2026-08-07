---
node_id: be944979-3508-5583-b6b8-bd96106ca7f5
slug: empty-forest-6305
title: Git-native backend
created_at: '2026-08-07T10:57:13.256136+00:00'
parents:
- cool-king-8586
summary: 'Open gap: git-native second adapter behind INTERFACE.md; sequenced after field dogfooding.'
flywheel:
  node_id: be944979-3508-5583-b6b8-bd96106ca7f5
  slug: empty-forest-6305
  revision: 0
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: 22385670d82872274e1680cbd1b58a750ae32377a355ee28f865781fefd4b837
---
Status: working

## Current

- The git-native backend exists and is this repo's live backend: markdown node files under `.hypergraph/graph/{record,state}/<slug>.md` are the source of truth, with `backend/local-adapter.md` mapping all 10 INTERFACE ops to CLI/file operations [rec: old-dawn-8747].
- Node format: YAML frontmatter (`node_id` = uuid5 of the slug, `slug`, `title`, `created_at`, `parents` as slugs, optional `flywheel:` mapping) over a body that is the node content byte-for-byte — so `check`/`render`/`viz` parse it unchanged [rec: old-dawn-8747].
- Integration surface is one file format and `export`: the checker, renderer and visualizer were not modified, because they only ever read the two JSON exports [rec: old-dawn-8747].
- Flywheel is now optional rather than load-bearing, and the two compose: `backend: local` + `mirror: flywheel` keeps files canonical and Flywheel a regenerable projection, refreshed by `push --plan` → skill executes → `push --record-result` [rec: old-dawn-8747].
- The sequencing bet in patient-limit-9007 — build-vs-defer decided only after field dogfooding — was overtaken: the adapter shipped first, so the interface was proven by a second implementation rather than by field use [rec: patient-limit-9007] [rec: old-dawn-8747].

## Negative knowledge

- [scope: mirroring a local graph to Flywheel | confidence: medium | evidence: old-dawn-8747] pushing content byte-identical means the slugs inside the markdown stay the local ones, so a slug read in Flywheel's UI resolves only via the frontmatter mapping; slug translation on push was rejected because it makes the mirror non-identical to source and complicates every update.

## Provenance

- patient-limit-9007 — Operator directive opening this gap, with constraints and sequencing
- old-dawn-8747 — the adapter, the CLI subcommands, and this repo's migration onto it
