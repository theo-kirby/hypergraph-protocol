---
node_id: 7fba16fb-c394-53d6-b168-b4fb50c57487
slug: gentle-journey-8382
title: 'Cruft sweep: the tree 0.9.0 stages from carries nothing stale'
created_at: '2026-08-16T17:39:36+00:00'
parents:
- loyal-tide-3608
summary: ''
---
## What

Pre-release cruft sweep for the 0.9.0 series: removed every stale artifact the viz
cut and earlier releases left behind, and made the "how many skills" phrasing
count-free so it cannot rot when a sixth skill lands.

Deleted (all untracked/git-ignored): `dist/` (stale 0.0.8 wheel + sdist),
`.hypergraph/viz.html` (980 KB; its generator left at 0.0.9), `tests/browser/`
(only `__pycache__` and screenshot output remained after the viz cut),
`.pytest_cache/`, stray `__pycache__` dirs. `.gitignore` dropped the entries that
pointed at them: the `hypergraph.py viz` half of the regenerable-files comment,
`.hypergraph/viz.html`, `/hg-viz/`, the Playwright-baseline comment plus
`tests/browser/shots/`, and the `.claude/skills` comment no longer hard-codes
"five entries".

## Why

0.9.0 is the clean-slate release: substrate + skills + dispatch, viz already out.
A release staged from a tree carrying dead artifacts and counts that are about to
be wrong is how drift starts. Counts in prose ("five skills") rot the moment the
dispatch skill lands, so the phrasing goes count-free once instead of being
patched every release.

## Method

`git status --porcelain --ignored` to enumerate candidates; confirmed each was
untracked or ignored before `rm -rf`. Grepped `five` across README.md, AGENTS.md,
SPEC.md, tools/, templates/ (filtered to skill mentions) and rewrote the six hits:
README.md lines 115/135/233, tools/hypergraph.py `skills` help text and the
`_trees_match` / upgrade section comments. Verification greps now return zero
skill-count hits.

## Result

Working tree carries no stale artifacts; `git status --porcelain --ignored` shows
only `.env`, `.hypergraph/cache/`, `.venv/`. Full suite green: 283 passed,
2 skipped. No behavior change — deletions and prose only.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: c7096b8b0405c1e2d1bc6dfbf1f4a953b7dfd088

## State Impact

none: repository hygiene — deletions of untracked artifacts and count-free prose; no state claim changes
