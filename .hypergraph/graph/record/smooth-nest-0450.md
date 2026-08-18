---
node_id: 955babff-46ed-5c86-8662-51c33ed3cc09
slug: smooth-nest-0450
title: '0.0.12: the gate work shipped under a staged bump; 0.1.0 stays reserved'
created_at: '2026-08-18T16:28:47+00:00'
parents:
- open-snow-3693
summary: ''
flywheel:
  node_id: fe496f6f-229c-5ebf-8fff-47c77e49d725
  slug: ancient-scene-0864
  revision: 0
  pushed_at: '2026-08-18T16:29:03+00:00'
  content_sha256: 5b6d0353e73d20cdb537ed0e1b498d5143c374538c044d63a9472e019a6358f2
  parents_sha256: 1dc1dcae9f42bd4345c6a3b96eb4900376d2100db051dc4cd0dfcc59a5acfcc9
  parents:
  - 0b4d02e0-9477-5db9-b970-cd894c27787c
---
## What

Version bump: 0.0.11 → 0.0.12, by Operator decision. The 0.1.0 gate work ships under this number; the 0.1.0 label stays reserved — the Operator plans more work before using it.

## Why

The Operator reviewed the completed gate and directed: commit and push everything, as 0.0.12 rather than 0.1.0. This partially lifts the version half of the release park (the bump is executed) while keeping the announcement parked as before.

## Method

The one-commit procedure CHANGELOG.md wrote down, executed with six locations: `pyproject.toml`, `tools/hypergraph.py` `__version__`, the SPEC.md header, `templates/config.example.yml`, `.hypergraph/config.yml` (all 0.0.12), and CHANGELOG's `[Unreleased]` promoted to `[0.0.12]` with a fresh empty `[Unreleased]` above it. The `[0.0.12]` heading is deliberately **undated**: this repo's convention dates only index-verified releases, this push publishes the mirror (CI) and the repo, not PyPI, and 0.0.9 already taught what a staged-but-unpublished version costs when it is not labeled as such — the section says so in as many words. Two forward-looking "0.1.0" labels in code comments (the block-digest registry entry, the fat-install conversion note) now read 0.0.12.

## Result

`uv run pytest tests/`: 342 passed, 2 skipped — `test_packaging` holds all six locations in step. `sync`: 0 violations, `push --verify` 0 drift. Pushed to origin/main. PyPI publication remains its own step; when it happens, the `[0.0.12]` heading gains its date and the release is verified from the public index as always.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: fe4a1fd8b2e84f5be0e0d5a02c0cc127116456db

## State Impact

- target: odd-birch-3808 — 0.0.12 is staged across all six synchronized version locations (Operator decision: not 0.1.0); PyPI publication and index verification remain the open step, and the CHANGELOG heading stays undated until then
