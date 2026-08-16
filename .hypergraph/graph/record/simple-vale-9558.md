---
node_id: 735a8736-a9a9-5fd5-8710-14ccd71860c2
slug: simple-vale-9558
title: The onboarding block names dispatch, and its digest ships registered
created_at: '2026-08-16T18:04:07+00:00'
parents:
- dry-spark-3491
summary: ''
flywheel:
  node_id: 1bc9079d-6042-5dbb-bad4-2ee78079c50e
  slug: silent-forest-6249
  revision: 0
  pushed_at: '2026-08-16T18:24:57+00:00'
  content_sha256: d79a3165397b80a09b95bafd41f6e405dcbbed6890702c2568716c385af97928
  parents_sha256: ea7a2f3bf5c6dc7c40c5f131751b792174da1c260cb8eab1af3e4ab1e437b545
  parents:
  - 4a9b6fcb-26ac-5a60-9b48-256b3a838e93
---
## What

The shipped AGENTS.md onboarding block now names dispatch: non-negotiable 1
("orient on arrival") gains one clause — to work a frontier gap deliberately
(a target, a budget, a lane of your own), use the `hypergraph-dispatch` skill.
The new block digest (5f15fb60…) is registered in `SHIPPED_BLOCK_DIGESTS` in
the same commit, tagged 0.9.0.

## Why

The block is how an arriving agent in an adopted repo learns the protocol
exists; a sixth skill it never mentions is a sixth skill nobody dispatches.
The digest registration is the upgrade contract: a block whose digest is in
the set is a template nobody edited, safe to overwrite on `hypergraph
upgrade`; forgetting the registration makes every clean 0.9.0 block look like
adopter prose and freezes it forever — which is why
`test_shipped_block_digest_is_registered` fails until the entry lands, and
why block edit and digest travel in one commit.

## Method

One-sentence clause in item 1; digest computed with the tool's own
`block_digest` (whitespace-insensitive content hash) and appended to the
frozenset with a 0.9.0 comment line, matching the 0.0.7/0.0.8 entries.

## Result

`uv run pytest tests/` — 302 passed, 2 skipped; the digest parity test passes
against the edited template.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 3506521c2e5ce8a227f82ab0885d6b85ffba2fb3

## State Impact

- target: fond-sail-3288 — the shipped agents-block now points arriving agents at hypergraph-dispatch; its digest is registered so upgrade recognizes an unedited 0.9.0 block as ours to refresh
