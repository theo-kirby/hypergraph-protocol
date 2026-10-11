---
node_id: 347235e5-756c-56ef-874b-923d5d58d9cc
slug: wise-stone-8848
title: 'Flywheel repository store: a second INTERFACE implementation, opt-in via store:'
created_at: '2026-10-11T12:14:06+00:00'
parents:
- mellow-tooth-5722
summary: ''
---
## What

Shipped a second storage implementation behind backend/INTERFACE.md: the
**Flywheel repository store**. A `store: {kind: flywheel-repo, flywheel_cli: <pin>}`
config block makes a Flywheel local repository (`flywheel repo:*`, CLI 0.2.78, Node
^24.15) the graphs' store of record, and `.hypergraph/graph/` its gitignored working
copy. New: `tools/hypergraph_store.py` (lazily loaded like the mirror),
`hypergraph store init|status|push|pull|verify`, backend/flywheel-repo-adapter.md,
tests/test_flywheel_store.py (10 tests, real CLI, skipped without it). SPEC Storage,
INTERFACE, cli.md, CHANGELOG, and the record/reconcile skills' commit steps updated.

## Why

Operator directive (via Cadex): migrate Cadex's graphs to Flywheel local repositories,
hosted later on the operator's Flywheel account, with pull/push between machines. This
settles the ADR-0002 tension that mellow-tooth-5722 documented, as an option per
project: the store-backed graph does not fork with the code, so worktree agents share
one graph instead of branch slices.

## Method

Rehearsed first in Cadex (cold-hollow-1327): a 1133-node import was lossless, but there
was one shared staging area per repository, and reading the full graph took 155 s. The design follows from those
facts: the core keeps every validation and file write unchanged; the adapter wraps
non-read-only commands with flock → refresh (incremental via `repo:diff` between the
index head and the store head) → command → push (stage changed files, one commit,
message = the command). Content = body + an invisible trailer holding the
frontmatter verbatim, so every file is rebuilt byte for byte; parents are mirrored as
lineage; non-root nodes are contained under their graph root. Store and working copy
resolve to the main checkout through `git rev-parse --git-common-dir`, so worktrees
share them. `check --since` under the store counts records created after the merge
base's commit time. The CLI version is pinned; a mismatch refuses.

## Result

`uv run pytest tests/ -m "not live"`: 396 passed, 1 failed. The failure is the
pre-existing `test_push_reports_actionably_when_no_transport_exists`, which fails on
any branch but `main`, because it reads the live branch name. The 10 store tests
pass against the real CLI and cover: byte-identical rebuild from a fresh working
copy; slugs, lineage and containment; new and update reaching the store; a worktree
writing into the main checkout's graph; 3 concurrent writers getting 3 commits;
an external store edit pulled in; a racing local edit refused rather than
overwritten; pin mismatch refused; `check --since` before and after a record.
Version stays 0.0.13 with the work under [Unreleased]. No PyPI publication.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: flywheel-store
- commit: b8322e805d57a86ecd666cb66b0b0a6442e7caa8

## State Impact

- target: blue-sun-8921 — a second store ships: store: {kind: flywheel-repo} makes a Flywheel local repository canonical and the node files its gitignored working copy shared across worktrees; byte-exact trailer encoding; flock-serialized write-through; check --since counts records created after the fork
