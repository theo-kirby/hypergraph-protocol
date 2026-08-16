---
node_id: d5d9e837-5f42-5f4a-8faf-e548ef34cb47
slug: stormy-glade-0866
title: 0.0.11 published and verified from the public index
created_at: '2026-08-16T18:34:27+00:00'
parents:
- vast-birch-5192
summary: ''
flywheel:
  node_id: 2da96655-83cc-561e-9c03-07a4f5c13ef6
  slug: black-king-1657
  revision: 0
  pushed_at: '2026-08-16T18:35:51+00:00'
  content_sha256: b3961e37ac4d23042cc063a12e42d0d4e5d7cb1c0e7f7f292982aa584c0dfe64
  parents_sha256: 17b1521a14f48685216e41170ad1a4cf2019ea59c5f0b425f88cdd8b7547c270
  parents:
  - cffd8cd9-d1f4-5414-9784-6aeb4ba6e412
---
## What

**0.0.11 is live on PyPI and verified from the public index.** `uv build`
produced the wheel and sdist; `uv publish` uploaded both with the Operator's
`PYPI_API_KEY`; and every verification ran against the index, not `dist/` —
the check that distinguishes "built" from "shipped".

## Why

The Operator directed the publish, naming 0.0.11 [rec: vast-birch-5192]. This
is the sixth published release and the first since 0.0.8: it carries the
dispatch loop (skill + lanes CLI + seam docs), the two-file mirror split, the
heal → `upgrade --graph` fold, the count-free docs, and the 0.0.11 stamps.
0.0.9 (staged by the viz cut) and 0.0.10 were never published; the index goes
0.0.8 → 0.0.11.

## Method

`rm -rf dist && uv build`; wheel inspected before upload (core +
`hypergraph_protocol_mirror.py` + the dispatch skill present). Publish via
`uv publish` with the token from the gitignored `.env`. Index verification,
all through `uvx --isolated --from hypergraph-protocol==0.0.11`:
`hypergraph --version` → `hypergraph-protocol 0.0.11`; `skills install`
into a scratch target lands **six** skills including `hypergraph-dispatch`;
`upgrade --graph` lists the repair registry; the PyPI JSON API lists exactly
the wheel and sdist.

## Result

https://pypi.org/project/hypergraph-protocol/0.0.11/ resolves; an adopter
needs only `uv tool install hypergraph-protocol` + `hypergraph skills
install` to get everything this release added.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: fd9c8efd0dc6bada021fefece18a866982ea8ae9

## State Impact

- target: odd-birch-3808 — 0.0.11 is live on PyPI and index-verified (version, six skills incl. dispatch, upgrade --graph registry); the sixth published release, first since 0.0.8; 0.0.9/0.0.10 never published
