---
node_id: 46de7285-a961-5823-8d2a-4b0fc7b3a42c
slug: spring-fog-0600
title: 'M4: four protocol skills + installer written'
created_at: '2026-08-06T21:42:44.475241+00:00'
parents:
- flat-pine-9555
- crimson-dawn-7137
summary: init/record/reconcile/orient skills + install.sh, installed and registered.
flywheel:
  node_id: 46de7285-a961-5823-8d2a-4b0fc7b3a42c
  slug: spring-fog-0600
  revision: 1
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 3422b8062697147e90d538a7c124925e13f2186f7f9727f80582ee9a45ede556
  parents_sha256: a3049db0241506ef07cbcaad4447b881e0f678e883979fa537778807f7acd13d
  parents:
  - 539c667a-99e4-541c-bc3b-76c9991239bf
  - 31dc7dde-666d-527e-806f-4ba4dd119cc1
---
## What

Wrote the four Claude skills — hypergraph-init, hypergraph-record, hypergraph-reconcile, hypergraph-orient — and install.sh, which symlinks them into ~/.claude/skills.

## Why

The protocol runs through agents, so the workflows must be packaged as skills. Written directly against the adapter recipes (crimson-dawn-7137) and invoking the checker/renderer from M3 (flat-pine-9555, second causal parent).

## Method

Each SKILL.md: frontmatter name/description, When To Use, Workflow, Guardrails, referencing SPEC invariants by ID. Division of labor: init creates roots + skeleton + config; record appends causally-parented record nodes and always declares `## State Impact` but never touches state (I3); reconcile is the single writer that folds impacts, advances the HWM, regenerates STATE.md and runs check; orient is read-only, frontier-first, ≤~6 tool calls, STATE.md fallback. Cross-file references are relative symlinks (references/spec.md → ../../../SPEC.md) which survive the install symlink because relative links resolve against physical location.

## Result

All four skills + install.sh landed in commit d877338; installer run verified — skills registered and the symlink chain resolves from ~/.claude/skills.

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: d87733881f9c0fb5063b047ab6bb9498cdd7e558

## State Impact

- target: dry-wildflower-2260 — status open → working; four skills + install.sh landed, installed, and registered