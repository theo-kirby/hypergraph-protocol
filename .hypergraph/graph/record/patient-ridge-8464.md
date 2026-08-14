---
node_id: 147ba0f5-ec6f-5f56-8f36-88bcae2240c0
slug: patient-ridge-8464
title: 0.0.8 published, and verified from the public index
created_at: '2026-08-09T19:40:12+00:00'
parents:
- clever-ledge-6588
summary: '0.0.8 is on PyPI. Verified with published artifacts only: the released skills carry the mode A walkthrough, and upgrade run from the published binary preserves cadex''s customized AGENTS.md block where 0.0.7 deleted it.'
flywheel:
  node_id: 78b3686e-43c8-5499-8e7e-942da80f5b98
  slug: muddy-voice-8069
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 349273697083994348e6a3002f4a7fc2225eacc13f4a6e0f182bda87faa7b263
  parents_sha256: bad793a92b2edd19ca330cfa9de6a8962fd445ed61058d5ec51ce249e4789a24
  parents:
  - f0b33eb5-ae8b-50b2-9e40-f22b8eab7a46
---
## What

0.0.8 is on PyPI and verified from the public index with published artifacts only —
not from the checkout that built them.

## Why

Closes the release the previous node's work was for. 0.0.7 shipped a destructive
`upgrade` and three latent defects on the mode A path; until a release carried the
fixes, every adopter still ran the broken code, which is why `fond-sail-3288` was held
at `broken` after the fix landed in the tree.

## Method

`uv build` → `uvx twine check` (both PASSED) → 25 `skills/` entries and
`templates/agents-block.md` confirmed in the sdist → commit and push main →
`uv publish`. Then verification *from PyPI*, deliberately not from `dist/`:

```
uv tool install hypergraph-protocol --force --refresh
  - hypergraph-protocol==0.0.7
  + hypergraph-protocol==0.0.8
```

`--refresh` was needed: a plain `uv tool upgrade` reported "Nothing to upgrade" against
a stale index cache while 0.0.8 was already live. Worth knowing before concluding a
publish failed.

## Result

- **PyPI latest: 0.0.8.** Releases 0.0.5 → 0.0.8. The package summary carries the new
  framing — "a substrate for autonomous research and engineering" — so the reframing is
  the first thing the index shows.
- **The published skills carry the documentation pass.** `hypergraph skills install`
  from the released package lands an `hypergraph-adopt/SKILL.md` containing both the
  "Mode A, end to end" walkthrough and the "Authoring nodes: four traps" section.
- **The block-preservation fix works on the repo that exposed it.** `hypergraph upgrade
  --dry-run` in cadex, using the published binary against a block carrying two
  hand-restored project-specific paragraphs:

  ```
    customized     AGENTS.md   (local edits inside the sentinels — pass --agents-block
                                to overwrite)
    would refresh  .hypergraph/config.yml   (hypergraph_version: 0.0.8)

  upgrade: 6 item(s) would be refreshed to 0.0.8, 1 block(s) left alone
  ```

  Under 0.0.7 the same command deleted those paragraphs. The six other items still
  refresh, which is the point: the safety is scoped to the one artifact adopters edit.

Both adopted repos are still on 0.0.7 skills by choice — nothing has run `upgrade`
against them yet, and their `check` will now say the copies are behind.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 92f62e05ace4d5d3d7a860bbf33436b22c7a00ce

## State Impact

- target: weathered-union-7494 — 0.0.8 published to PyPI and verified from the public index with published artifacts only: `uv tool install --force --refresh` moves 0.0.7 -> 0.0.8, the released package's skills carry the mode A walkthrough and the authoring-traps section, and `upgrade --dry-run` run from the published binary against cadex's customized AGENTS.md block reports it and steps back where 0.0.7 deleted it. The index summary carries the new framing, so the substrate-for-autonomous-research statement is what the package advertises. Note for future releases: `uv tool upgrade` alone reported "Nothing to upgrade" against a stale index cache while 0.0.8 was live — verification needs `--refresh` before a publish is judged to have failed.
