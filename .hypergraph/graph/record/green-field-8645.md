---
node_id: b742ec11-cf3e-5a46-aa5e-8825e7dab1c4
slug: green-field-8645
title: 'Librarian audit of the remote-machine cycles: claims reproduced; summary-drift defect found and fixed'
created_at: '2026-08-07T18:54:08+00:00'
parents:
- kind-valley-8040
- damp-mountain-8757
summary: 'Independent audit of the publication + git-native-backend cycles: all claims reproduced (50 tests, 0/0 check, byte-identical STATE.md, empty push plan); stale frontmatter summaries found — the one defect — plus the overridden sequencing bet noted.'
flywheel:
  node_id: 6774b147-a74b-5878-bbcd-9c6651089906
  slug: lively-dream-2689
  revision: 0
  pushed_at: '2026-08-07T18:57:11+00:00'
  content_sha256: 0424816b2dc18a722ac8cdf4df0cb011f1968f852c29f0e59da702a272a89b5f
---
## What

Independent librarian audit of the two remote-machine cycles — the publication decision (damp-mountain-8757) and the git-native backend build with its self-reconciles (old-dawn-8747 → sleepy-branch-3744 → kind-valley-8040) — plus repair of three state-node frontmatter `summary:` fields those reconcile passes left stale.

## Why

The Operator asked for verification of work done on another machine before accepting it into the project's memory. First audit conducted entirely through the new local backend: the node files are now the source of truth, so the audit reads files, not the mirror.

## Method

Re-ran every verifiable claim: `uv run pytest tests/` (expecting 50), `export` from node files → `check`, `render` → diff against committed STATE.md, `push --plan` for mirror sync. Cross-checked record-node causal parenting, impact-declaration validity, the immutability discipline (correction-by-child-node), Flywheel state-root revision history, and the slug-divergence claim against a live Flywheel export.

## Result

All claims reproduced: 50/50 tests green; `check` 0 violations / 0 warnings / 0 unreconciled from the node files; STATE.md regenerates byte-identical; the mirror push plan is empty (in sync as claimed). Protocol discipline held across both workstreams: causal parenting correct, decision-node flow used for the publication directive, a correction node used instead of editing an immutable record, and the mirror slug divergence honestly measured and folded as negative knowledge.

Two findings. (1) Defect, fixed in this cycle's reconcile: the remote reconcile passes rewrote state-node bodies but left three frontmatter `summary:` fields stale — worst case empty-forest-6305, whose summary still claimed "Open gap … sequenced after field dogfooding" while the node's status is working; wandering-sun-8831 said 22 tests against a body saying 50. `check` parses only bodies, so summary drift is mechanically invisible — recorded as negative knowledge. (2) Governance nuance, no action: the patient-limit-9007 sequencing bet (git-native backend only after field dogfooding) was overridden by the work itself without a fresh decision node; the override is honest and traceable in old-dawn-8747's Why and in the folded state, but strictly the convention calls for a decision record when reversing a bet. Also noted for the pattern's visibility: the remote session held both the worker and librarian roles — permitted, since I3 is per-pass, not per-session.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 3ea524c780b9ba3d3cbe947fbd520a28e54acf09

## State Impact

- target: wandering-sun-8831 — summary corrected (50 tests, not 22); new negative knowledge: check cannot see frontmatter summary drift (it parses bodies only)
- target: empty-forest-6305 — summary corrected to match working status (was "Open gap … sequenced after field dogfooding")
- target: bold-field-1268 — new claim: remote-machine cycles independently audited and reproduced by the librarian session; summary refreshed
