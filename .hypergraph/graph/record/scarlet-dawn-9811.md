---
node_id: 9c258196-fe04-5bb2-8a71-7c35031e3548
slug: scarlet-dawn-9811
title: '0.0.13: stage the version bump — named views ship under it'
created_at: '2026-08-19T10:23:40+00:00'
parents:
- strong-star-9849
summary: 0.0.13 staged across every synchronized version location; CHANGELOG carries the views compatibility statement; publication remains the open step.
flywheel:
  node_id: 1b18363c-95ba-5ccf-9b44-6505c0c11dd2
  slug: plain-silence-7905
  revision: 0
  pushed_at: '2026-08-19T10:25:52+00:00'
  content_sha256: b05e4c4b26d08b09eca1f17ec3c8fff3aace527b87d35e04907250865a54185a
  parents_sha256: 2dd231349f784a0ad4283c8fe1d7c779f7d06eda1f86eeb57907c1ec045c074b
  parents:
  - 93f06f70-f526-5acb-beb8-2cc83386149d
---
## What

Staged the 0.0.13 version bump: `pyproject.toml`, `tools/hypergraph.py
__version__`, the SPEC header, this repo's `.hypergraph/config.yml` stamp, the
config template stamp, the lockfile, and the CHANGELOG's `[0.0.13]` entry — the
six synchronized locations `tests/test_packaging.py` pins, plus the new
agents-block digest registered in `SHIPPED_BLOCK_DIGESTS` (the block's "two
graphs" sentence became record + one or more views).

## Why

The named-views work of `strong-star-9849` ships under 0.0.13, and the packaging
tests hold every version location equal — the bump is one unit or the suite is
red. The CHANGELOG heading carries the compatibility statement the versioning
policy requires: a project that adds views needs ≥0.0.13 tooling (old `check`
reports a view-qualified impact as I2 unparseable), bare projects unaffected in
both directions.

## Method

Bumped all locations in one pass; `uv lock` refreshed the lockfile;
`uv run pytest tests/` green (386 passed, 2 skipped);
`uv run tools/hypergraph.py sync --config .hypergraph/config.yml` exit 0 with
STATE.md unchanged. The CHANGELOG heading stays undated until publication is
verified from the public index, per the changelog's own convention.

## Result

The repo is release-ready at 0.0.13. PyPI publication and index verification
remain the open step, as they were for 0.0.12 at this stage.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e05b6b80e1f363f0916f6606dd0e682672567e58

## State Impact

- target: odd-birch-3808 — 0.0.13 is staged across all synchronized version locations with the views compatibility statement in the CHANGELOG; PyPI publication and index verification remain the open step, and the heading stays undated until then
