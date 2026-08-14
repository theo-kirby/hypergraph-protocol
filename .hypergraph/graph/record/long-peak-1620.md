---
node_id: 84d861a8-e9e0-5400-84fc-de055f6c1d02
slug: long-peak-1620
title: 0.0.5 released to PyPI; CI publishes the mirror; a broken sdist caught on the way
created_at: '2026-08-09T12:45:33+00:00'
parents:
- placid-ridge-4035
summary: PyPI 0.0.5 live and verified from the public index. Both GitHub workflows installed and green on their first run, with the publish job refreshing the mirror over REST at 0 drift. Fixed an sdist that carried no skills/ at all, because hatchling dedupes by inode and the dogfooding symlinks shadowed the real tree.
flywheel:
  node_id: a7a3106b-d4ea-58aa-88bc-5184bafb7fcd
  slug: noisy-tooth-4033
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 4b3b8f3a705f4c84c860c9939fd8d2d543d995013a24393317677638dd10423b
  parents_sha256: 3b62a025b331d00e6f3da299ec845347bc4d59eb8d7acd3a38a974ea9dd98a85
  parents:
  - d1338969-8407-52f7-bc2f-c71cc5df0eaf
---
## What

**0.0.5 is live on PyPI**, and the CI half of the collaboration model is running: both
workflows are installed in this repo, and the publish job has refreshed the mirror over
the HTTP API for real. A packaging defect that would have shipped a broken sdist was
found and fixed on the way.

## Why

The 0.0.5 work [rec: placid-ridge-4035] left two Operator calls open: whether to release,
and whether to install the publish workflow. Both were unblocked in one turn — the
release parking [rec: southern-ridge-1802] was lifted for this version, and a Flywheel
key belonging to the mirror's own account was placed in `.env`.

The release also had a hard dependency the other way round: the shipped
`templates/github-actions/hypergraph-check.yml` does `uv tool install hypergraph-protocol`
and then calls `check --since`, which does not exist before 0.0.5. Until this release,
an adopter copying the template got a workflow that could not run.

## Method

**The sdist was broken, and every declaration in `pyproject.toml` was correct.**
`uv build` failed at "build wheel from sdist" with `Forced include not found: skills`.
The sdist contained `.claude/skills/**` and no `skills/**` at all.

Cause: hatchling's `safe_walk` uses `os.walk(followlinks=True)` and skips any directory
whose `(st_dev, st_ino)` it has already seen. `.claude/skills/hypergraph-*` are the
committed dogfooding symlinks into `skills/`, and `.claude` sorts first — so hatchling
materialized the skills under `.claude/`, then reached the real `skills/` and dropped it
as a duplicate.

Adding `exclude = [".claude"]` made it *worse*, and that is the instructive part:
`exclude` filters the output, not the walk. The walker still descended, still followed
the symlinks, still marked the inodes — so both copies vanished and the sdist had no
skills at all. The fix is `skip-excluded-dirs = true`, which prunes the directory
*before* descent; the two lines only work together.

Diagnosed by calling hatchling's own builder API rather than by reading tarballs:
`include_path("skills/hypergraph-record/SKILL.md")` returned `True` while
`recurse_included_files()` yielded nothing under `skills/`, which located the fault in
traversal rather than in pattern matching, and `directory_is_excluded(".claude", "")`
returning `False` exposed `skip_excluded_dirs` as the reason.

**The regression test builds an artifact and looks inside it.** For every path the
wheel's `force-include` names, the sdist must carry it — which is exactly the invariant
that was violated. Verified by removing `skip-excluded-dirs` and watching it fail.

**CI transport.** The publish workflow uses `--transport rest`, so CI needs no npm and
no `flywheel` binary — `urllib` plus `FLYWHEEL_BASE_URL` and `FLYWHEEL_API_KEY`. The CLI
transport's advantage is that it can read a key from the OS keychain, which does not
apply when the key arrives from a repository secret. Measured, not assumed: the CLI does
honour `FLYWHEEL_API_KEY` from the environment (a bogus value 401s), so either transport
would have worked in CI; REST is simply one less install step.

## Result

**PyPI**: `hypergraph-protocol` 0.0.5, sdist + wheel. Verified from the public index in a
clean venv — `--version` reports 0.0.5, `hwm` and `check --since` resolve, and
`skills install` lays down all five skills from the published wheel.

**Both workflows green on their first run**, on the push that installed them. The publish
job authenticated over REST, reported `0 create(s), 0 update(s)` — the mirror was already
current — and `push --verify: 0 drift finding(s)`. That is the whole collaboration claim
demonstrated rather than argued: the mirror is now a build artifact of the default branch,
written by CI, and no contributor needs a credential.

**The repository is public and its main branch now matches the release**; 14 local commits
were pushed, which also closes the gap of a published artifact whose source was not yet
visible.

**Severity of the sdist bug, stated honestly**: `pip install hypergraph-protocol` prefers
the wheel, and the wheel was always correct, so no installer was broken. What was broken
is building from source — `pip install --no-binary`, a distro packager, or anyone running
`uv build` on a clone. It was introduced by the dogfooding symlinks and would have shipped
in the first release after them.

**Not done**: the npm placeholder still points at PyPI 0.0.2, and the spec-first
announcement remains parked on an Operator decision with no date [rec: southern-ridge-1802].

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: bf02ff63712ec59b918af4d934135169146e2a5d

## State Impact

- target: weathered-union-7494 — 0.0.5 is released and verified from the public index, clearing four previously-unreleased changes plus everything in 0.0.4 and 0.0.5; the adopter CI template now has a version that supports it.
- target: wandering-sun-8831 — a packaging defect that made the sdist unbuildable is fixed (hatchling inode dedup vs the dogfooding symlinks), with a test that builds an sdist and inspects it. Suite to 283.
- target: gilded-vale-8087 — the CI half of the collaboration model is live: both workflows installed and green, the publish job reaching the mirror over REST at 0 drift. No longer only proven by construction.
- target: empty-forest-6305 — the REST transport is proven in anger: CI publishes with urllib and two environment variables, needing no npm and no flywheel binary.
