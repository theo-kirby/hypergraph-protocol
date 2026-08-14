---
node_id: 65e56c95-78e0-5425-8ce3-fabbf2e3137b
slug: late-isle-6483
title: 'M3: hypergraph-adopt skill + AGENTS.md sentinel block'
created_at: '2026-08-07T20:18:29+00:00'
parents:
- careful-harbor-3902
summary: 'hypergraph-adopt shipped: mode A import-as-fork / mode B prehistory, epoch marker, distillation with id-prefix resolution + dead-end interview, init tail, idempotent AGENTS.md block with contract reconciliation. Fifth skill registered.'
flywheel:
  node_id: b2698e17-6991-5f96-9e76-b9e50e520230
  slug: purple-sunset-6177
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: e5b5255dc5a02e7eae24d7ed3d8ed121af4fbb2525a82be7b3cdb068a6e3493b
  parents_sha256: e7743197fb996c1c11095d81036f7cd4a44a133b149dc6e7e39e5d2407e5ffdd
  parents:
  - da12e9f7-dd2f-5666-a942-e390000d59fe
---
## What

Shipped the `hypergraph-adopt` skill and the AGENTS.md onboarding block (adoption thrust M3): the conversion path for repos with a past, covering mode A (existing Flywheel graph → import as the fork) and mode B (no graph → authored prehistory), through epoch marker, state-graph distillation, init tail, and onboarding install.

## Why

hypergraph-init only covers day zero. Both dogfooding targets (vast-sky-3964) need a history-aware path: a3go carries a 67-node legacy graph plus docs that cite anchors and node-id prefixes; tbinn has real experiment history and no graph. Without a skill, each adoption would improvise — and the AGENTS.md contract is what made blind test #2 pass, so adopters need it installed mechanically.

## Method

`skills/hypergraph-adopt/` in the hypergraph-init layout (SKILL.md + references/ symlinks incl. the new `templates/agents-block.md`). Workflow: (1) inventory with all-anchors resolution — docs-declared index nodes are anchors too, union-exported in one `flywheel_export_subgraph` call and count-checked against what the docs cite; (2) mode A import (ids/slugs verbatim, mandatory `archive:` block since artifacts don't survive import, epoch-split offered >~1000 nodes) or mode B prehistory (1–3 honest era nodes, never event-by-event); (3) "Adopted Hypergraph" epoch marker with the M1 parentage rules, `epoch.marker` into config; (4) distillation — per-branch mining with subagent fan-out for over-context graphs, id-prefix→slug resolution before writing provenance, honest statuses, dead ends as negative knowledge with legacy evidence slugs, and a user interview for invisible dead ends; (5) init tail (HWM → marker, config, export/render/check green, commit; new mirror roots + legend + verify when mirroring); (6) onboarding — sentinel block `<!-- hypergraph:begin/end -->` appended idempotently (replace-if-present), contract reconciliation when an existing agent contract conflicts, symlink-preserving edits, full `.hypergraph/AGENTS.md`.

## Result

Skill registered: install.sh glob picked it up (five skills now symlinked), README "What ships" + repo map + adoption paragraph updated, SPEC per-project files section covers adopt outputs (epoch/archive config keys, sentinel block). `templates/agents-block.md` is ≤15 content lines wrapping the four non-negotiables + pointer to `.hypergraph/AGENTS.md`. 60/60 tests green (no code changes). Commit 67f518c.

## Repo

- repo: https://github.com/theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 67f518c98d82ea6b4a51c750616020fe19b8ad29

## State Impact

- target: morning-crane-7863 — M3 done: adopt skill + agents-block template shipped; milestone list advances to M4
- target: dry-wildflower-2260 — new claim: fifth skill hypergraph-adopt (modes A/B, epoch, distillation, onboarding install); agents-block.md template ships with it
