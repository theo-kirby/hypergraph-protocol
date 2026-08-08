---
node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
slug: weathered-union-7494
title: Publication
created_at: '2026-08-07T17:25:37.632552+00:00'
parents:
- cool-king-8586
summary: 'Named on PyPI + npm, MIT-licensed, 0.0.2 live and index-verified; last gap: public flip + spec-first announcement.'
flywheel:
  node_id: 609c7366-4f4e-5f6d-87f2-f384afc8bf6a
  slug: weathered-union-7494
  revision: 4
  pushed_at: '2026-08-08T08:47:33+00:00'
  content_sha256: 9e2a9a0d2f518910b155f6d1f6035d3ff24ac2b999dedcac7dfccf4aa882efb6
---
Status: open

## Current

Publication shape decided [rec: damp-mountain-8757]: spec-first (SPEC.md is the durable artifact), a PyPI CLI package as the distribution vehicle (CLI will also install the skills into adopter projects), this repo as reference implementation + self-dogfood exhibit — adopters never clone or fork it; optionally a Claude Code plugin as a secondary channel. The existing Flywheel graphs continue unchanged through the rename — an export/import fork would re-slug nodes and sever cross-graph provenance [rec: damp-mountain-8757].

Name claimed on both registries: `hypergraph-protocol` on PyPI (0.0.1 at claim time [rec: damp-mountain-8757]) and on npm (placeholder 0.0.2 pointing users to PyPI, published under the `kirbyt` account [rec: lively-willow-7648]). GitHub repo renamed to theo-kirby/hypergraph-protocol (old URL redirects). gitleaks scan over full history: clean; repo still private.

Release 0.0.2 is live on PyPI and verified from the public index [rec: crisp-lake-4496] [rec: rough-reef-5869]: `hypergraph skills install` installs all five skills (skills + `templates/agents-block.md` as package data via hatchling force-include; project-level `.claude/skills/` default, `--user` for `~/.claude/skills`), and the published CLI's epoch-aware `check` reports 0 violations on both adopted repos. The distribution story is end-to-end: an adopter needs only uvx + PyPI. Both adopter repos' onboarding un-pinned from the dev checkout [rec: rough-reef-5869].

Licensed MIT [rec: lively-willow-7648]: LICENSE committed, PEP 639 metadata in pyproject (`license`/`license-files`), LICENSE in the sdist; rebuilt 0.0.2 artifacts twine-clean. The already-published PyPI 0.0.2 predates the metadata — the next release carries it.

Remaining (the gap): public flip + spec-first announcement. The v0.1 package gate for general adoption is the git-native backend (see empty-forest-6305) [rec: damp-mountain-8757].

## Negative knowledge

- [scope: naming/distribution of this project | confidence: high | evidence: damp-mountain-8757] Bare `hypergraph` is taken on PyPI; `hg*` names read as Mercurial (its CLI is `hg`); clone/fork distribution rejected — the protocol is an overlay on adopters' repos, not a template.
- [scope: publishing to npm with a token from a dotenv file | confidence: high | evidence: lively-willow-7648] `source .env` sets but does not export variables — `${VAR}` in .npmrc expands empty in the npm child process and the PUT fails as E404 (not 401), which misreads as a registry problem. Wrap the source in `set -a` … `set +a`.

## Provenance

- damp-mountain-8757 — publication shape + name decision; executed PyPI 0.0.1 publish, GitHub rename, gitleaks-clean history check
- vast-sky-3964 — 0.0.2 scope: skills install + agents-block template as package data
- crisp-lake-4496 — 0.0.2 built, twine-clean, wheel-verified; publish blocked on credentials at the time
- rough-reef-5869 — 0.0.2 published and index-verified; adopters un-pinned
- lively-willow-7648 — MIT license + PEP 639 metadata; npm name claimed with a PyPI-pointing placeholder
