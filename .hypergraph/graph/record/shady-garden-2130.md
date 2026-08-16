---
node_id: 85aeed41-48a4-52cf-817e-0967acea2404
slug: shady-garden-2130
title: '0.9.0: the clean-slate version, stamped and staged'
created_at: '2026-08-16T18:07:22+00:00'
parents:
- noble-stream-7701
summary: ''
flywheel:
  node_id: e37eab9a-7362-53d9-959b-eb69d77222e7
  slug: square-lake-5326
  revision: 0
  pushed_at: '2026-08-16T18:24:57+00:00'
  content_sha256: d0a3d52dfebb555b3225260b323a76a0c9772b509ab5e6e62eddf791d6da6770
  parents_sha256: 036876e92aa3f2a5cc73449c858c679f45099b7b3888913241c48c20fa65abd0
  parents:
  - dc8ebfa9-d1a0-5a1c-a6db-e0ba97f0e2f6
---
## What

Version 0.9.0 in all five stamps, one atomic commit: pyproject.toml, the
module's `__version__`, the SPEC.md header, this repo's
`.hypergraph/config.yml` `hypergraph_version:`, and
templates/config.example.yml. Both healers' `since=` moved "0.0.9" → "0.9.0" in
the same commit: 0.0.9 never shipped to PyPI, so 0.9.0 is where the tags and
artifacts repairs first publish, and `since` is a publication claim shown to
adopters. No `0.0.9` mention inside `.hypergraph/graph/**` was touched —
append-only history stays as written.

## Why

0.9.0 is the clean-slate release: substrate + skills + dispatch as one product,
viz already out, mirror optional behind its own module, box behind a documented
seam. The jump from 0.0.x to 0.9.x says what the series now is — a base to
iterate 0.9.1, 0.9.2, … toward 1.0. Four parity tests in test_packaging.py
enforce that the stamps move together, which is why this is one commit.

## Method

Five stamp edits plus a scripted `since=` replace asserting exactly two hits.
Grep confirms no stray 0.0.9 outside the append-only graph history.

## Result

`uv run pytest tests/` — 302 passed, 2 skipped (the four version-parity tests
pass against 0.9.0). `hypergraph --version` → `hypergraph-protocol 0.9.0`.
Staged, deliberately unpublished: the PyPI push is the Operator's step.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 10cf3803ef26b50e21ab4569b96720a568df05c1

## State Impact

- target: odd-birch-3808 — 0.9.0 is stamped in all five places and staged, deliberately unpublished; the PyPI publish (and its verify-from-the-public-index step) is the Operator's call
