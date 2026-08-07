---
node_id: 8c1471f0-1499-5585-9b54-7eeef3f23e45
slug: damp-mountain-8757
title: 'Decision: publish as hypergraph-protocol — spec-first + PyPI CLI; name claimed (0.0.1 live)'
created_at: '2026-08-07T17:24:46.624669+00:00'
parents:
- little-bar-4131
summary: 'Publication shape and name decided: hypergraph-protocol. Repo renamed on GitHub, gitleaks history scan clean, package 0.0.1 published to PyPI with a working `hypergraph` console entry point.'
flywheel:
  node_id: 8c1471f0-1499-5585-9b54-7eeef3f23e45
  slug: damp-mountain-8757
  revision: 0
  pushed_at: '2026-08-07T18:12:00.956635+00:00'
  content_sha256: aebafa410f03f0a7eb0cc5e7c6a44759806447d9f79a1c631862a9ef9111cb42
---
## What

Decided the publication shape and name for the project, and executed the name claim. The project is now **hypergraph-protocol**: GitHub repo renamed to `theo-kirby/hypergraph-protocol` (old URL auto-redirects), and `hypergraph-protocol` 0.0.1 published to PyPI, shipping the existing single-file tool as module `hypergraph_protocol` with a `hypergraph` console entry point. Publication shape decided: (1) SPEC.md as the durable spec-first artifact, (2) a PyPI CLI package as the distribution vehicle (which will also install the skills into adopter projects), (3) the repo as reference implementation + self-dogfood exhibit — adopters never clone or fork it, (4) optionally a Claude Code plugin as a secondary channel. Existing Flywheel graphs are kept unchanged — rename, not rebirth: slugs are the cross-graph provenance mechanism and an export/import fork would re-slug and sever every provenance pointer.

## Why

Follows from blind test #2 (parent): the protocol is validated on itself, so the next thrust is publication. Clone/fork distribution was rejected because Hypergraph is an overlay on adopters' projects, not a template (model: pre-commit / spec-kit — install a tool, run init inside your own repo). Bare `hypergraph` is taken on PyPI; `hg*` names rejected for Mercurial collision (`hg` is Mercurial's CLI). ~80 candidates checked against PyPI and npm via registry HTTP lookups; Operator chose `hypergraph-protocol` (runner-up: `hypergraphia`, free on both registries) — package name carries identity, the console command stays `hypergraph` since the two namespaces are independent.

## Method

- Availability sweep: HEAD `https://pypi.org/pypi/<name>/json` and `https://registry.npmjs.org/<name>` for ~80 candidates (404 = available).
- Pre-publication secrets check: `.env` confirmed gitignored and never tracked; `gitleaks git` over full history — 12 commits, no leaks.
- `gh repo rename hypergraph-protocol` (local remote auto-updated).
- `pyproject.toml` rewritten as a real package: hatchling backend, `[tool.hatch.build.targets.wheel.force-include]` maps `tools/hypergraph.py` → `hypergraph_protocol.py` (repo layout unchanged, `uv run` dev flow unchanged), `[project.scripts] hypergraph = "hypergraph_protocol:main"`, deps `pyyaml>=6`.
- `uv build` → `uvx twine check dist/*` (PASSED) → `uv publish` with the PyPI token → verified live install with `uvx --refresh --from hypergraph-protocol hypergraph`.
- `config.yml` `project:` updated to hypergraph-protocol.

## Result

- `hypergraph-protocol` 0.0.1 live on PyPI; `uvx --from hypergraph-protocol hypergraph check` runs the real checker from the public index and passes 0/0 on this repo's own exports.
- gitleaks: no leaks in history; repo safe to flip public later (still private for now).
- `uv run pytest tests/` 22 passed; `check` 0 violations / 0 warnings after the pyproject change.
- npm name NOT claimed (no npm credentials available); LICENSE file does not exist yet — both open items under the new publication frontier node.
- Remaining for the publication thrust: `hypergraph skills install` subcommand (skills as package data, project-level `.claude/skills/` default), LICENSE choice, public flip + spec-first announcement, npm placeholder; package v0.1 gate remains the git-native backend (empty-forest-6305).

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol
- branch: main
- commit: e6141ef4dffbfb1eb5f14144abc391140d198082

## State Impact

- target: cool-king-8586 — project renamed to hypergraph-protocol: retitle state root to "hypergraph-protocol — state"; PyPI name claimed at 0.0.1
- target: NEW publication — publication/packaging thrust opened: shape decided (spec-first SPEC.md + PyPI CLI `hypergraph-protocol` + skills; repo = reference impl and dogfood exhibit, never cloned/forked; graphs continue unchanged). Name claimed on PyPI (0.0.1) and GitHub. Status: open — remaining: skills-install CLI subcommand, LICENSE choice, public flip + announcement, npm name; v0.1 package gate is the git-native backend