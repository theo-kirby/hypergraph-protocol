---
node_id: 9cb1715d-3f46-5fde-baef-534ab1bf2af0
slug: weathered-ivy-5352
title: 0.0.13 published and verified from the public index
created_at: '2026-08-19T16:53:35+00:00'
parents:
- young-ivy-4144
summary: 'The eighth release: named views + the structure-first docs, published via uv publish and verified entirely against the index (version, six skills + shared references at v0.0.13, the views verb, exactly two files). CHANGELOG heading dated.'
flywheel:
  node_id: 24b993a7-b4ea-5c47-b67e-88cc1c12f789
  slug: bitter-darkness-5795
  revision: 0
  pushed_at: '2026-08-19T16:54:06+00:00'
  content_sha256: d5c944ef26c487b40e1b288a7ffe009a005de2e04272bdf094ebca7fbdd9d334
  parents_sha256: 8e0dfcbc806e68bc7f6e6f2e536a088bf5375677408b20471d05e109ba5b3546
  parents:
  - ec960c65-6920-5ec6-8282-31b753fd4139
---
## What

Published 0.0.13 to PyPI and verified it from the public index — the eighth
release, carrying named views and the structure-first public docs. The Operator
tightened the README once more before the publish (109 lines final) and directed
the release.

## Why

The 0.0.13 bump was staged with publication named as the open step; the
Operator's "push to git and pypi" closed it. This release is also the first
whose PyPI page renders correctly: the rewritten README uses absolute GitHub
URLs, and the summary line leads with "agent-native substrate".

## Method

`rm -rf dist && uv build`; both artifacts inspected before upload — wheel 27
files / 195 KB with the core, `hypergraph_protocol_mirror.py`, all six skills,
**exactly one spec.md** under `hypergraph_protocol_data/references/`, and the
`references.yml` manifest; the sdist 48 files with neither `tests/` nor
`.hypergraph/`. Published via `uv publish` with the token from the gitignored
`.env`. Index verification, all through `uvx --isolated --from
hypergraph-protocol==0.0.13` (after ~1 minute of index propagation):
`hypergraph --version` → `hypergraph-protocol 0.0.13`; `skills install` into a
scratch target lands six skills plus the shared `hypergraph-references/` payload
whose spec.md reads "v0.0.13"; the new `views` subcommand resolves; the PyPI
JSON API lists exactly the wheel and the sdist and serves the rewritten README
and summary. CHANGELOG's `[0.0.13]` heading gained its date in the same commit,
per the convention that only index-verified releases are dated.

## Result

https://pypi.org/project/hypergraph-protocol/0.0.13/ resolves; the index goes
0.0.12 → 0.0.13. An adopter now gets named views (`hypergraph views add`,
view-qualified impacts, per-view reconciliation) from
`uv tool install hypergraph-protocol`, and the PyPI page reads as the project's
actual front door for the first time.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: f5b6720cb5e342f0903d22e4d6e67e4465c70a9d

## State Impact

- target: odd-birch-3808 — 0.0.13 is live and index-verified, the eighth release: named views reach adopters, the index goes 0.0.12 → 0.0.13, and the PyPI page now renders the rewritten README with resolving links
