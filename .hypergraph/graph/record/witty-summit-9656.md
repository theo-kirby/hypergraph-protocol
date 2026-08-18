---
node_id: b53ae917-48f1-53c8-9cb1-eb919f5b8b1c
slug: witty-summit-9656
title: 0.0.12 published and verified from the public index
created_at: '2026-08-18T21:20:57+00:00'
parents:
- smooth-nest-0450
summary: ''
flywheel:
  node_id: 3401b72d-8c7b-514f-a48a-404b70bc3aa6
  slug: long-wood-9723
  revision: 0
  pushed_at: '2026-08-18T21:21:06+00:00'
  content_sha256: e27aedd3248f4efd807c8aa1d68fc26760a883a2d513a18079b51d8d463bbfca
  parents_sha256: ca7620832179cfc6b2f69a9b483ebe8629524cec2bcff54ef1db4358d959bb39
  parents:
  - fe496f6f-229c-5ebf-8fff-47c77e49d725
---
## What

**0.0.12 is live on PyPI and verified from the public index.** `uv build` produced the wheel and sdist; `uv publish` uploaded both with the Operator's `PYPI_API_KEY`; every verification ran against the index, not `dist/` — the check that distinguishes "built" from "shipped".

## Why

The Operator directed the publish of the staged 0.0.12 [rec: smooth-nest-0450]. This is the seventh published release and carries the whole 0.1.0 gate: the hardened checker with the live-graph regression net, guarded export loading, sync/hwm under test with `hwm --tips`, upgrade that delivers new skills, the deduplicated skills payload, init writing the onboarding contract, the drift sweep, and the release surface (CHANGELOG, versioning policy, docs/cli.md, docs/example.md).

## Method

`rm -rf dist && uv build`; both artifacts inspected before upload — core + `hypergraph_protocol_mirror.py` present, all six skills, **exactly one spec.md** (under `hypergraph_protocol_data/references/`), the `references.yml` manifest, no per-skill reference copies, wheel 189 KB; the sdist carries the skills tree and neither `tests/` nor `.hypergraph/`. Publish via `uv publish` with the token from the gitignored `.env`. Index verification, all through `uvx --isolated --from hypergraph-protocol==0.0.12`: `hypergraph --version` → `hypergraph-protocol 0.0.12`; `skills install` into a scratch target lands six skills **plus the shared `hypergraph-references/` payload, with every per-skill reference a resolving relative symlink** whose spec.md reads "v0.0.12" — the first index-side proof of the U6 dedupe; `upgrade --graph` lists the repair registry; the PyPI JSON API lists exactly the wheel and sdist. CHANGELOG's `[0.0.12]` heading gained its date in the same commit, per the convention that only index-verified releases are dated.

## Result

https://pypi.org/project/hypergraph-protocol/0.0.12/ resolves. An adopter needs only `uv tool install hypergraph-protocol` + `hypergraph skills install` to get everything the gate added, at ~136 KB of installed skills instead of ~348 KB. The index goes 0.0.11 → 0.0.12.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e1dd6673e0f42db1ba58b50ae0959db66645705f

## State Impact

- target: odd-birch-3808 — 0.0.12 is live on PyPI and index-verified (version, six skills, the shared references payload with resolving links, the upgrade --graph registry, exactly wheel+sdist); the seventh published release, carrying the whole 0.1.0 gate
