---
node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
slug: weathered-union-7494
title: Publication
created_at: '2026-08-07T17:25:37.632552+00:00'
parents:
- cool-king-8586
summary: 0.0.2 live on PyPI (skills install verified from the public index, epoch-aware check clean on both adopted repos); LICENSE + public flip + npm remain.
flywheel:
  node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
  slug: weathered-union-7494
  revision: 3
  pushed_at: '2026-08-07T22:06:45+00:00'
  content_sha256: e58f08b66afb2f4848e064e5aa8d04816eb99263dbbbf03876b3d555c56a71c3
---
Status: open

## Current

Publication shape decided [rec: damp-mountain-8757]: spec-first (SPEC.md is the durable artifact), a PyPI CLI package as the distribution vehicle (CLI will also install the skills into adopter projects), this repo as reference implementation + self-dogfood exhibit — adopters never clone or fork it; optionally a Claude Code plugin as a secondary channel. The existing Flywheel graphs continue unchanged through the rename — an export/import fork would re-slug nodes and sever cross-graph provenance [rec: damp-mountain-8757].

Name claimed [rec: damp-mountain-8757]: `hypergraph-protocol` on PyPI (0.0.1 published at claim time), shipping tools/hypergraph.py as module `hypergraph_protocol` with a `hypergraph` console entry point. GitHub repo renamed to theo-kirby/hypergraph-protocol (old URL redirects). gitleaks scan over full history: clean; repo still private.

Release 0.0.2 is live on PyPI and verified from the public index [rec: crisp-lake-4496] [rec: rough-reef-5869]: `hypergraph skills install` installs all five skills (skills + `templates/agents-block.md` as package data via hatchling force-include; project-level `.claude/skills/` default, `--user` for `~/.claude/skills`), and the published CLI's epoch-aware `check` reports 0 violations on both adopted repos. The distribution story is end-to-end: an adopter needs only uvx + PyPI. Both adopter repos' onboarding un-pinned from the dev checkout [rec: rough-reef-5869].

Remaining (the gap): LICENSE choice; public flip + spec-first announcement; npm name unclaimed (no npm credentials). The v0.1 package gate for general adoption is the git-native backend (see empty-forest-6305) [rec: damp-mountain-8757].

## Negative knowledge

- [scope: naming/distribution of this project | confidence: high | evidence: damp-mountain-8757] Bare `hypergraph` is taken on PyPI; `hg*` names read as Mercurial (its CLI is `hg`); clone/fork distribution rejected — the protocol is an overlay on adopters' repos, not a template.

## Provenance

- damp-mountain-8757 — publication shape + name decision; executed PyPI 0.0.1 publish, GitHub rename, gitleaks-clean history check
- vast-sky-3964 — 0.0.2 scope: skills install + agents-block template as package data
- crisp-lake-4496 — 0.0.2 built, twine-clean, wheel-verified; publish blocked on credentials at the time
- rough-reef-5869 — 0.0.2 published and index-verified; adopters un-pinned
