---
node_id: 00c0bfed-6d8d-5c87-8341-99327f794b3f
slug: steady-ember-8009
title: 'U5: viz stub and heal alias removed; dead code and numpy cut; .DS_Store ignored'
created_at: '2026-08-18T12:01:07+00:00'
parents:
- rough-hill-4967
summary: ''
flywheel:
  node_id: 85eec449-b850-5bf5-9956-a1a544ee9e59
  slug: wandering-surf-2186
  revision: 0
  pushed_at: '2026-08-18T12:01:10+00:00'
  content_sha256: 707c61e2ef6a15714bd56399eef41b90155bec26b9801bb1b52828a042a57bec
  parents_sha256: a702c3ef3d1868e75027f9141cd23f247404a60980fd18889aa88577140e586e
  parents:
  - c19e8f6b-9f35-5119-a737-00c634046351
---
## What

U5 of the 0.1.0 gate: the code cuts the Operator locked — the `viz` signpost stub and the hidden `heal` alias are removed now (not deprecated further), dead code and the unused numpy dev-dependency are deleted, and `.DS_Store` is gitignored.

## Why

The audit flagged weight without work. The viz stub was two releases past its cut and still occupied a subcommand, a SPEC section, a README section and comment blocks in both configs. The `heal` alias survived "for the 0.0.x series" — with 0.1.0 as the next release, its window closes exactly now. `tag_def` and `artifact_abspath` had zero callers (grep-confirmed before deletion; only `merge_tag_def` is live). numpy was declared for a "benchmark lab fidelity evaluator" that no longer exists in the tree — zero uses in tests/ or tools/. And because the wheel force-includes `skills/` wholesale, an untracked `.DS_Store` would ship in the next release artifact.

## Method

Removed: `cmd_viz` + its subparser + the module-docstring signpost; SPEC's Visualization section collapsed to one sentence (the JSON exports are the contract) and its tag-standing sentence rewritten off the `viz:` reference; README's renderer section trimmed to the hypergraph-viz pointer; the `viz:` comment block in `.hypergraph/config.yml`; the `viz` pin in test_mirror.py. Removed: the `p_heal` subparser, `_heal_alias` runtime note, docstring/comment alias promises, and the metavar comment that existed to hide it. `tests/test_heal.py` migrated its 6 alias invocations to `upgrade --graph` and now pins `heal` as an argparse "invalid choice" exit 2. Deleted `tag_def`, `artifact_abspath`, the numpy dev-group entry with its stale comment (lockfile resynced). `.gitignore` gains `.DS_Store` with the force-include rationale.

## Result

Suite 332 → 333 passed (one alias test replaced by the removal pin plus a no-deprecation-note check), 2 skipped. `sync`: 0 violations, 0 drift. The CLI surface is now 16 subcommands with no hidden entries — the count docs/cli.md (U10) will document.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 0c7cc2b5d35d18581ebbf77f6414343f84e295a6

## State Impact

- target: wandering-sun-8831 — the viz signpost and the heal alias are gone from the CLI (16 subcommands, none hidden); tag_def/artifact_abspath and the numpy dev-dependency deleted; .DS_Store gitignored so it cannot ship in the wheel
- target: polished-pond-2718 — the in-core signpost stub is now removed too: the CLI carries no viz entry at all, and the one remaining sentence in SPEC/README says visualization is external with the JSON exports as the contract
