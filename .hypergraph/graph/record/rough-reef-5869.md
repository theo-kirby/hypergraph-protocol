---
node_id: bd86f002-0981-5439-a281-5a7f31007591
slug: rough-reef-5869
title: hypergraph-protocol 0.0.2 published to PyPI; adopters un-pinned
created_at: '2026-08-07T22:04:56+00:00'
parents:
- fond-tree-4727
summary: ''
flywheel:
  node_id: 0f73be66-ea95-51c0-8c1b-9b49e42feac8
  slug: sparkling-tooth-0222
  revision: 0
  pushed_at: '2026-08-07T22:06:09+00:00'
  content_sha256: 4700ae02a9747616bf5ede78ef02b0acf275f9727aa8c2ae1acf57ccb3c7fdb7
---
## What

Published hypergraph-protocol 0.0.2 to PyPI, closing the one item the adoption thrust left blocked: the M4 build was wheel-verified but unpublishable for lack of credentials. The dev-checkout CLI pins in both adopter repos' onboarding are removed.

## Why

crisp-lake-4496 recorded the publish as blocked (no PyPI token on this machine), and fond-tree-4727 left it as the thrust's only open tail. The Operator supplied the credential location (.env, `PYPI_API_KEY`), unblocking it.

## Method

`uvx twine check dist/*` re-run on the existing 0.0.2 artifacts (both PASSED — same wheel and sdist built in M4, unchanged), then `uv publish --token` from the repo .env. Post-publish verification from the public index after ~1 min of propagation: `uvx --refresh --from hypergraph-protocol==0.0.2 hypergraph skills install` in a scratch project (all five skills installed into `.claude/skills/`, including hypergraph-adopt), and the published CLI's `check` run against both adopted repos. Onboarding un-pin: the "until 0.0.2 is on PyPI use the dev checkout" sentence in each adopter's `.hypergraph/AGENTS.md` replaced with the plain `uvx --from hypergraph-protocol hypergraph` form (a3go d8203e5, tbinn 4ca09b4).

## Result

0.0.2 is live and correct on the public index: `skills install` works via uvx, and the published CLI reports 0 violations on a3go (107 legacy nodes epoch-exempt — the false-positive hazard that forced the pin is gone) and 0 violations on tbinn. The distribution story the plan called for is now real end-to-end: an adopter needs only uvx + PyPI, no clone of this repo. Remaining publication gaps are unchanged from before: LICENSE choice, public repo flip + announcement, npm name.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: a1f64d503357275c940f16bc793094e7a5eeb67a

## State Impact

- target: weathered-union-7494 — 0.0.2 published to PyPI and verified from the public index (skills install + epoch-aware check on both adopted repos); the credentials blocker is resolved; remaining gap narrows to LICENSE, public flip, npm name
- target: morning-crane-7863 — the adoption thrust's last open tail is closed: adopter repos un-pinned from the dev checkout; the published CLI is the onboarding path
