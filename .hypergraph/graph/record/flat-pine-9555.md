---
node_id: 539c667a-99e4-541c-bc3b-76c9991239bf
slug: flat-pine-9555
title: 'M3: invariant checker + STATE.md renderer built, tests green'
created_at: '2026-08-06T21:42:29.729467+00:00'
parents:
- empty-cherry-5305
summary: check/render uv script + fixture-backed pytest suite, 11 tests green.
flywheel:
  node_id: 539c667a-99e4-541c-bc3b-76c9991239bf
  slug: flat-pine-9555
  revision: 2
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: fc683a1866678f0c3d2eb592ead938a9d75e3e125384ae1e74a435b3a47cae26
  parents_sha256: 9f344c17316cf00f0774ac2b3c7e34c7abc2c4e31b63474bbeca2b7bafa7bd6f
  parents:
  - ab4e2f97-9989-5366-813e-827466807faf
---
## What

Built tools/hypergraph.py — a single-file uv script (PEP 723, pyyaml only) with `check` and `render` subcommands — plus committed JSON fixtures and a pytest suite.

## Why

SPEC invariants (empty-cherry-5305) are only real if mechanically enforced; the checker consumes offline JSON exports so it is deterministic, auth-free, and CI-ready.

## Method

`check --record record.json --state state.json [--config]` validates I2 (impact declarations incl. unknown targets), I4 (provenance + inline [rec: slug] citations resolve), I5 (parseable HWM; enumerates unreconciled nodes + per-target pending impacts), I6 (status vocabulary), I7 (negative-knowledge scope/confidence/evidence, decision slug required for generalized scope); I1 proxied as warnings (uncited claims). Nonzero exit on violations. `render` emits STATE.md: frontier section first (broken → blocked → open), architecture tree below. Fixtures: tools/fixtures/clean/ passes; one seeded violation dir per checkable invariant.

## Result

`uv run pytest tests/` — 11 passed in 0.32s: clean fixture yields 0 violations/0 warnings, every violation fixture fails with exactly its invariant ID, CLI exit codes verified (0 clean / 1 violation), render output verified (frontier excludes working nodes), staleness reporting verified by rolling the HWM back one node.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: d87733881f9c0fb5063b047ab6bb9498cdd7e558

## State Impact

- target: wandering-sun-8831 — status open → working; check + render implemented, 11 tests green over committed fixtures