---
node_id: 19ab6cd2-b4af-5a63-807f-d766ab4879db
slug: lively-willow-7648
title: MIT license adopted; npm name hypergraph-protocol claimed
created_at: '2026-08-08T08:44:51+00:00'
parents:
- rough-reef-5869
summary: ''
flywheel:
  node_id: b84b6711-9145-5066-a820-c9570a9dd5ca
  slug: royal-heart-0264
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 5f54e9d6d9e5fc038542e077f8eac98889058148147c1caf611b2175dab2adba
  parents_sha256: 7da2bcbab4cd87ab0dad1cdaaed27c8dffeecda663c45d64e661dd396166ad2a
  parents:
  - 0f73be66-ea95-51c0-8c1b-9b49e42feac8
---
## What

Licensed the project under MIT and claimed the `hypergraph-protocol` name on npm, closing two of the three publication gaps left open after the 0.0.2 release (rough-reef-5869). The remaining gap is the public repo flip + spec-first announcement.

## Why

weathered-union-7494 carried both items as the publication frontier: an unlicensed repo cannot be flipped public in good conscience, and the npm name was unclaimed (a squat risk once the project is announced). The Operator chose "very permissive" and supplied the npm token location (.env, `NPM_API_KEY`).

## Method

License: MIT chosen over Apache-2.0/GPL — the Operator asked for maximally permissive, which rules out copyleft; MIT vs Apache-2.0 is near-equivalent for a protocol/tooling repo and MIT is the lower-friction default. Wrote `LICENSE` (MIT, (c) 2026 Theo Kirby), added PEP 639 metadata to pyproject.toml (`license = "MIT"`, `license-files = ["LICENSE"]`) and LICENSE to the sdist include; `uv build` + `uvx twine check` both PASSED on the rebuilt 0.0.2 artifacts, so the next PyPI upload carries the license metadata (the already-published 0.0.2 does not — not worth a version bump alone).

npm: published a 2-file placeholder package `hypergraph-protocol@0.0.2` (README + package.json pointing at PyPI and the GitHub repo, MIT) from a scratch directory under the `kirbyt` account via the .env token. Gotcha recorded: `source .env` does not export variables to child processes — `${NPM_API_KEY}` in .npmrc expanded empty and npm returned E404 (not 401) on the PUT; `set -a`/`set +a` around the source fixed it. Post-publish `npm view` confirmed name/version/license live on the public registry after ~45s propagation lag.

## Result

`LICENSE` and license metadata committed; twine check PASSED. `npm view hypergraph-protocol` returns version 0.0.2, license MIT — the name is claimed and points users to PyPI. Publication frontier narrows to one item: flip the repo public + announce.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: c71d0a036f08f883effe09949f5a5e26f1fe8b9e

## State Impact

- target: weathered-union-7494 — LICENSE (MIT) and npm-name gaps closed: LICENSE + PEP 639 metadata committed (twine clean), placeholder hypergraph-protocol@0.0.2 live on npm pointing to PyPI; remaining gap narrows to the public flip + announcement
