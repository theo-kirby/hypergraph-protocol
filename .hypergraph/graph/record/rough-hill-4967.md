---
node_id: 80ad1093-8eda-5ba0-87ae-967723157247
slug: rough-hill-4967
title: 'U4: upgrade delivers new skills; install.sh idempotent; retracted-label loop broken'
created_at: '2026-08-18T11:57:57+00:00'
parents:
- witty-chart-7035
summary: ''
flywheel:
  node_id: c19e8f6b-9f35-5119-a737-00c634046351
  slug: small-bread-0576
  revision: 0
  pushed_at: '2026-08-18T11:58:00+00:00'
  content_sha256: c1494dfb8eb125532ebb7e8de6aa55f684a66963cb10c53378c1173fca865aaf
  parents_sha256: 1c3aadda8df7f883a38089f4b6c16f1aa56b7085af2ac156cd5ad3bd77cf51ef
  parents:
  - 8c11b7a0-33a3-54ce-bb97-f5a4e6f7456b
---
## What

U4 of the 0.1.0 gate: the three distribution defects the audit found are fixed — `upgrade` now delivers skills a release added, `install.sh` is idempotent, and the retracted-0.9.0 skew loop is broken.

## Why

`upgrade_skills` skipped any skill absent from the target (`if not dst.exists(): continue`), so no pre-0.0.11 adopter could ever receive `hypergraph-dispatch` through the documented two-command path — every adopter was frozen at the skill set of the release they first installed. `install.sh` failed on its second run because the source-link guard in `skills install` fired on its own output. And a repo stamped `hypergraph_version: 0.9.0` (the retracted label) compared greater than 0.0.11, so the skew check permanently advised upgrading to a CLI that does not exist.

## Method

- `upgrade_skills`: a target holding any `hypergraph-*` entry gets the full shipped set — present skills refreshed, missing ones installed, mode-matched (all-symlink installs get a symlink to the source, anything else a copytree). A target with no hypergraph skills gets one `skipped` line naming `hypergraph skills install` and nothing written: the doctrine tightens from "never installs what is not already there" to "**never opts a repo in**" (a repo that opted in does get completed).
- `skills install --link` over a source-linked entry: "already linked" no-op, or a re-point when the link resolves elsewhere inside the tree. Copy mode still refuses — copying over a live link replaces the skill with a stale snapshot of itself invisibly.
- `RETRACTED_VERSIONS = frozenset({"0.9.0"})` beside `check_version_skew`: a retracted stamp warns "retracted release label — `hypergraph upgrade` re-stamps", never "upgrade the CLI".

## Result

5 new tests (missing-skill install in copy and symlink modes, never-opts-in with the install pointer, linked-install idempotency, copy-mode refusal, retracted-label wording); suite 327 → 332 passed, 2 skipped. Verified live: `./install.sh` run twice into a scratch dir — first run links six skills, second prints "already linked" ×6 and exits 0. `sync`: 0 violations, 0 drift.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: d5b9a9a16b69a76c950b3c79333106a2b59e5210

## State Impact

- target: fond-sail-3288 — the three audit-found delivery defects are fixed: upgrade completes an opted-in repo's skill set (doctrine: never opts a repo in), install.sh is re-runnable, and 0.9.0-stamped repos are told to re-stamp instead of chasing a CLI that does not exist
