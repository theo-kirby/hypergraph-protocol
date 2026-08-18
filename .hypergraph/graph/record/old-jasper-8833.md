---
node_id: cb8866e4-546f-55e3-89e7-077011895675
slug: old-jasper-8833
title: 'U6: installed-skills payload dedupe — references ship once, skills link to them'
created_at: '2026-08-18T12:06:55+00:00'
parents:
- steady-ember-8009
summary: ''
flywheel:
  node_id: 2d1dd205-542e-5abf-9b63-6e18458129f4
  slug: broad-violet-3662
  revision: 0
  pushed_at: '2026-08-18T12:06:59+00:00'
  content_sha256: b78de4b37d573d0f0e0b91501796bcd61bc684dfb365bee5af845bd59cb546dc
  parents_sha256: eaa92fe8faf3fbeac7c305266474f1fb6c6930383318556c3a368d2625180763
  parents:
  - 85eec449-b850-5bf5-9956-a1a544ee9e59
---
## What

U6 of the 0.1.0 gate — the highest-risk item, landed without the fallback: the installed-skills payload no longer ships six copies of its reference documents. Each referenced file ships once; installed skills link to it.

## Why

The audit measured the installed payload at 348 KB with 78% of it duplicates: every skill's `references/` symlinks (spec.md, local-adapter.md, …) were materialized as full copies at wheel build. Six copies of SPEC.md in every adopter's `.claude/skills/` is weight without work, and a copy that drifts is worse than weight.

## Method

- **Wheel**: `hypergraph_protocol_data/references/` carries each of the 7 referenced files once. Discovered en route: hatchling's `force-include` bypasses `exclude` *and* `skip-excluded-dirs` (both tried, both measured ineffective on force-included trees), so the per-skill payload is enumerated file by file — six SKILL.md entries plus `skills/references.yml` — with `test_wheel_force_include_enumerates_every_skill_file` pinning the enumeration complete against the tree.
- **Manifest**: a wheel cannot carry symlinks, so `skills/references.yml` records the per-skill reference sets. The dogfooding symlinks stay authoritative in the repo (layout unchanged); `skill_reference_sets()` reads symlinks when present, the manifest otherwise, and `test_manifest_matches_the_dogfooding_symlinks` pins the two representations equal.
- **Install**: under the wheel layout, `skills install` writes `<target>/hypergraph-references/` once, then each skill's `references/<name>` as a relative symlink (`../../hypergraph-references/<name>`), copy-fallback when `symlink()` raises. `--link` under a wheel layout is refused with the reason (it needs a source tree whose skills carry their references). Dev-checkout behavior is unchanged.
- **Upgrade**: `_refresh_shared_references` refreshes/prunes the shared dir wholesale and rewrites every real skill dir's links — which also converts a fat pre-0.1.0 install to the deduped shape on its first upgrade. `_trees_match` compares `references/` only when the source has one.

## Result

7 new tests (suite 333 → 340 passed, 2 skipped), including a built-wheel inspection asserting exactly one spec.md. End-to-end on a real artifact: `uv build` → `uv pip install` into a scratch venv → `hypergraph skills install --target` → every `references/<name>` is a symlink resolving to real content; payload measured at 136 KB (from ~348 KB). Symlinked references provably load in Claude Code — this repo's own `.claude/skills` already work that way. `sync`: 0 violations, 0 drift.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: dfdb5b308e30dc39e2ae2e15e26221b8fd161a70

## State Impact

- target: fond-sail-3288 — the installed payload drops 348 KB to 136 KB: the wheel ships each reference once, skills install links per-skill references to the shared payload, and upgrade converts fat pre-0.1.0 installs on first run; force-include proven to bypass exclude filters, so the skill payload is enumerated and test-pinned
