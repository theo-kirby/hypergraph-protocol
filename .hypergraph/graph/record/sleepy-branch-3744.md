---
node_id: 4e4d354a-8bc8-5998-8c5b-48fe86db1c9e
slug: sleepy-branch-3744
title: 'Correction: accurate test counts (50, not 49); fixed a false-positive heading guard in new record'
created_at: '2026-08-07T18:15:07+00:00'
parents:
- old-dawn-8747
summary: Suite is 50 tests (22 pre-existing + 28 local-backend), not 49/16/33 as stated in old-dawn-8747. Also fixes new record's substring heading guard to be line-anchored.
flywheel:
  node_id: cdc0228f-517a-56db-8805-6a4423910f8b
  slug: cold-recipe-1148
  revision: 0
  pushed_at: '2026-08-07T18:21:35+00:00'
  content_sha256: 36031f7fb9fe8a86140865d29ccdddb79d0bd6e2a88d735086d63df0b50823dc
---
## What

Corrects the test-suite arithmetic stated in old-dawn-8747's `## Result`, and
records one bug found while authoring that node with the new CLI.

## Why

Record nodes are immutable (SPEC conventions): a correction is a child node, not
an edit. Reconcile needs the accurate figure before folding a claim about the
suite into wandering-sun-8831.

## Method

`uv run pytest tests/ -q --collect-only`, counted per file.

## Result

- Accurate counts: **50 tests** — 11 `test_checker.py` + 11 `test_viz.py`
  (22 pre-existing, matching the standing state claim) + 28
  `test_local_backend.py`. old-dawn-8747 said "49 (16 pre-existing + 33 new)";
  both figures there are wrong, and 49 predated the last added case.
- Bug found and fixed while authoring old-dawn-8747: `new record`'s guard against
  a `--body` that already contains a generated section used a naive substring
  test, so prose merely *mentioning* `## State Impact` was rejected. Now anchored
  to line starts (`^## State Impact$`, case-insensitive), with a regression test
  covering both the duplicate-heading rejection and the prose-mention acceptance.
  This is the 28th local-backend test.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 192a7ed1f7acbf9dec7f0cdf20ed865e04c2fc97

## State Impact

- target: wandering-sun-8831 — test suite 22 → 50 (11 checker + 11 viz + 28 local backend); supersedes the count stated in old-dawn-8747
