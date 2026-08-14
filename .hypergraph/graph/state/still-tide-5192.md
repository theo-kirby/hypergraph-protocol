---
node_id: 2d57b36b-ae4c-57a4-9875-f5bdbefee5b2
slug: still-tide-5192
title: GitHub repository
created_at: '2026-08-14T13:25:06+00:00'
parents:
- damp-basin-8974
summary: Public since a second gitleaks-clean full-history scan; both CI workflows green, so the mirror is a build artifact of main written by CI rather than by a laptop.
flywheel:
  node_id: b43a6656-05d1-513f-9d4a-6ef607dc45f7
  slug: sweet-cloud-4293
  revision: 0
  pushed_at: '2026-08-14T13:37:04+00:00'
  content_sha256: d8a2d22d0456eb1645764beb12cfafaa31908de35ba0142a1d455d200746fdae
  parents_sha256: 9c8039d8ccc995d9c15665648d7d82c9399050ef076f05102c409e2d18ebabfb
  parents:
  - e6697aa9-2f7c-5b23-8ef4-abc687d15567
---
Status: working

## Current

- The repository is **public**, at `theo-kirby/hypergraph-protocol` after a rename from `hypergraph` that left the old URL redirecting [rec: damp-mountain-8757]. main was pushed and visibility flipped only after a second full-history gitleaks scan — 43 commits, no leaks, `.env` confirmed untracked with no history. GitHub auto-detects the MIT license and the PyPI/npm repository links now resolve for outsiders [rec: lawful-birch-4414].
- **A published artifact's source has to be public at the same moment.** The 0.0.5 release closed a window where it was not, by pushing 14 local commits so main matched what was on the index [rec: long-peak-1620].
- **Both CI halves are live rather than merely designed** [rec: long-peak-1620]. The PR check runs tests, invariants, `check --since` and a STATE.md freshness gate; the publish job authenticates over REST and reports 0 drift. Both were green on their first run, which makes the mirror a build artifact of the default branch in fact and not only in design [rec: placid-ridge-4035].
- The publish job is also what proves the REST transport in anger: `push --transport rest --require-mirror` over `urllib` with two environment variables, needing no npm and no `flywheel` binary. The CLI transport's one advantage — reading a key from the OS keychain — does not apply when the key arrives from a repository secret [rec: long-peak-1620].

## Negative knowledge

None yet.

## Provenance

- damp-mountain-8757 — the repo rename, with the old URL redirecting
- lawful-birch-4414 — main pushed and the repo flipped public after a gitleaks-clean re-scan
- long-peak-1620 — both workflows installed and green; the publish job reaches the mirror over REST
- placid-ridge-4035 — the publish gates that let CI own publishing
