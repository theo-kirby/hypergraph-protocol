---
node_id: 40f49fa0-eb2d-5b11-95af-e12811dd8793
slug: dry-spark-3491
title: 'The local lane provider: hypergraph dispatch open/ls/harvest/close'
created_at: '2026-08-16T18:03:15+00:00'
parents:
- young-sage-8406
summary: ''
flywheel:
  node_id: 4a9b6fcb-26ac-5a60-9b48-256b3a838e93
  slug: bold-cherry-6482
  revision: 0
  pushed_at: '2026-08-16T18:24:57+00:00'
  content_sha256: 54d382a8ece00bf56ea2d778c74a3d3df89322ec428338e0992947ded5e2f5cf
  parents_sha256: 96584699d72083014446b2ce83f92d9d1c289e02036dc039d32f7003d61166e7
  parents:
  - 4245ba73-15e8-5ae2-b7f9-90d22caac299
---
## What

The local lane provider: `hypergraph dispatch open|ls|harvest|close` (~250 lines
in tools/hypergraph.py), implementing backend/lanes.md's five operations with
git alone. `open` mints the lane slug (the caller never names it), provisions a
worktree on `lane/<slug>`, and either launches the configured agent — argv from
`shlex.split` with `{lane_dir}` as the only placeholder, no shell, dispatch
brief (target/budget/attribution) as JSON on stdin — or, with no
`dispatch.agent` configured, stands down at exit 0 printing the manual steps.
`ls` lists lanes (dirty/merged/unmerged) plus live dispatch claims read from
the record graph (unreconciled `Dispatch:` nodes with no `Dispatch closed:`
descendant, computed against the state root's high-water mark). `harvest`
refuses a dirty lane or a dirty checkout, merges `lane/<slug>`, and reports
which record nodes arrived. `close` refuses while unmerged or dirty unless
`--force` (which says so: "its work is abandoned"), then removes worktree and
branch. Config: a commented `dispatch:` block in templates/config.example.yml
(`lanes_dir`, `agent`) — read by the CLI only, invisible to the skills;
`/.hypergraph/lanes/` gitignored in this repo.

## Why

The skill carries the judgment; this carries the mechanics — and the two rules
worth code rather than prose are the ones from the lab repo's fleet lessons:
briefs on stdin never argv (argv is world-readable process state), and teardown
that *refuses* while unharvested (the one irreversible provider mistake is
destroying work never brought home). Applying our own lanes.md rules to our own
provider is the point of writing the seam first.

## Method

Lane discovery parses `git worktree list --porcelain` filtered to `lane/*`
branches; a strict `_lane_git` raises on failure so bookkeeping never mistakes
failure for empty. Agent exit status passes through as a harness fact, never a
work verdict (lanes.md op 3). tests/test_dispatch.py (9 tests, throwaway-git-
repo idiom from test_collaboration.py): unique minted lanes; stand-down at exit
0 with the manual steps naming the skill, the target, and both follow-up
commands; a fake agent receives the brief on stdin with the target/budget
absent from argv and `{lane_dir}` substituted; exit-status passthrough; harvest
merges and reports arrived nodes then refuses dirty; close refuses unharvested
without `--force` and deletes worktree+branch after harvest; `--force` abandons
loudly; `ls` shows lanes and live claims, and a closure descendant retires the
claim.

## Result

`uv run pytest tests/` — 302 passed, 2 skipped (293 + 9). Manual smoke in this
checkout: `dispatch ls` → "no lanes / no live dispatch claims".

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 0ad40cc0d8d2bdac08b0fbd73cc602fa8fe9282a

## State Impact

- target: wandering-sun-8831 — new CLI verb: dispatch (local lanes as git worktrees on lane/<slug> branches; brief on stdin never argv; teardown refuses while unharvested; stand-down at exit 0 with no agent configured); suite 293→302
- target: gilded-vale-8087 — the lanes seam has its shipped implementation: backend/lanes.md's five ops realized with git alone, harvest as a merge
