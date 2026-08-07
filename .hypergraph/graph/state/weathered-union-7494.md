---
node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
slug: weathered-union-7494
title: Publication
created_at: '2026-08-07T17:25:37.632552+00:00'
parents:
- cool-king-8586
summary: 'Publication/packaging thrust: spec-first + PyPI CLI + skills; name claimed as hypergraph-protocol.'
flywheel:
  node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
  slug: weathered-union-7494
  revision: 0
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: 6d3fa023742bdc073d741a48c2df422e8ce5457130a3d55e0d63350a88051f7c
---
Status: open

## Current

Publication shape decided [rec: damp-mountain-8757]: spec-first (SPEC.md is the durable artifact), a PyPI CLI package as the distribution vehicle (CLI will also install the skills into adopter projects), this repo as reference implementation + self-dogfood exhibit — adopters never clone or fork it; optionally a Claude Code plugin as a secondary channel. The existing Flywheel graphs continue unchanged through the rename — an export/import fork would re-slug nodes and sever cross-graph provenance [rec: damp-mountain-8757].

Name claimed [rec: damp-mountain-8757]: `hypergraph-protocol` 0.0.1 live on PyPI, shipping tools/hypergraph.py as module `hypergraph_protocol` with a `hypergraph` console entry point (verified installable via uvx; checker passes on this repo's own exports). GitHub repo renamed to theo-kirby/hypergraph-protocol (old URL redirects). gitleaks scan over full history: clean; repo still private.

Remaining (the gap): `hypergraph skills install` CLI subcommand (skills as package data, project-level `.claude/skills/` default); LICENSE choice; public flip + spec-first announcement; npm name unclaimed (no npm credentials). The v0.1 package gate for general adoption is the git-native backend (see empty-forest-6305) [rec: damp-mountain-8757].

## Negative knowledge

- [scope: naming/distribution of this project | confidence: high | evidence: damp-mountain-8757] Bare `hypergraph` is taken on PyPI; `hg*` names read as Mercurial (its CLI is `hg`); clone/fork distribution rejected — the protocol is an overlay on adopters' repos, not a template.

## Provenance

- damp-mountain-8757 — publication shape + name decision; executed PyPI 0.0.1 publish, GitHub rename, gitleaks-clean history check