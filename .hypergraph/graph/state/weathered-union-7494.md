---
node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
slug: weathered-union-7494
title: Publication
created_at: '2026-08-07T17:25:37.632552+00:00'
parents:
- cool-king-8586
summary: 0.0.1 live on PyPI; 0.0.2 built + wheel-verified with skills install but publish blocked on Operator credentials; LICENSE + public flip remain.
flywheel:
  node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
  slug: weathered-union-7494
  revision: 1
  pushed_at: '2026-08-07T20:03:23+00:00'
  content_sha256: deaf9c0fa3a6dfe574ef731bf610104a082c9fdb6f8842e26a6c9777e576776b
---
Status: open

## Current

Publication shape decided [rec: damp-mountain-8757]: spec-first (SPEC.md is the durable artifact), a PyPI CLI package as the distribution vehicle (CLI will also install the skills into adopter projects), this repo as reference implementation + self-dogfood exhibit — adopters never clone or fork it; optionally a Claude Code plugin as a secondary channel. The existing Flywheel graphs continue unchanged through the rename — an export/import fork would re-slug nodes and sever cross-graph provenance [rec: damp-mountain-8757].

Name claimed [rec: damp-mountain-8757]: `hypergraph-protocol` 0.0.1 live on PyPI, shipping tools/hypergraph.py as module `hypergraph_protocol` with a `hypergraph` console entry point (verified installable via uvx; checker passes on this repo's own exports). GitHub repo renamed to theo-kirby/hypergraph-protocol (old URL redirects). gitleaks scan over full history: clean; repo still private.

Release 0.0.2 built and wheel-verified [rec: crisp-lake-4496]: `hypergraph skills install` subcommand shipped (skills + `templates/agents-block.md` as package data via hatchling force-include; project-level `.claude/skills/` default, `--user` for `~/.claude/skills`; symlinked references materialized at build); `uv build` + twine check clean; install verified from the built wheel.

Remaining (the gap): the 0.0.2 PyPI publish itself — `uv publish` fails with no credentials on this machine (0.0.1 was published elsewhere; no ~/.pypirc, keychain, or env token), so the Operator must publish; until then adopter repos pin the dev-checkout CLI, because PyPI 0.0.1 lacks epoch support and would report false I2 violations on adopted graphs [rec: crisp-lake-4496]. Also open: LICENSE choice; public flip + spec-first announcement; npm name unclaimed (no npm credentials). The v0.1 package gate for general adoption is the git-native backend (see empty-forest-6305) [rec: damp-mountain-8757].

## Negative knowledge

- [scope: naming/distribution of this project | confidence: high | evidence: damp-mountain-8757] Bare `hypergraph` is taken on PyPI; `hg*` names read as Mercurial (its CLI is `hg`); clone/fork distribution rejected — the protocol is an overlay on adopters' repos, not a template.

## Provenance

- damp-mountain-8757 — publication shape + name decision; executed PyPI 0.0.1 publish, GitHub rename, gitleaks-clean history check
- vast-sky-3964 — 0.0.2 scope: skills install + agents-block template as package data
- crisp-lake-4496 — 0.0.2 built, twine-clean, wheel-verified; publish blocked on credentials
