---
node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
slug: dry-wildflower-2260
title: Skills
created_at: '2026-08-06T21:41:21.141576+00:00'
parents:
- cool-king-8586
summary: Five skills (init/record/reconcile/orient/adopt) + AGENTS.md onboarding, validated by controlled blind retest and field adoption; discoverability lesson at high confidence.
flywheel:
  node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
  slug: dry-wildflower-2260
  revision: 6
  pushed_at: '2026-08-07T21:23:55+00:00'
  content_sha256: 9fb3527f664f26321dd2fa151238b18c7891c13f4b80cc13ff380200377eae52
---
Status: working

## Current

- Five skills landed and installed: hypergraph-init (roots + skeleton + config), hypergraph-record (causally-parented record nodes, always declares State Impact, never writes state), hypergraph-reconcile (single writer: folds impacts, advances HWM, regenerates STATE.md, runs check, refreshes + verifies the mirror), hypergraph-orient (read-only frontier brief, ≤~6 tool calls, STATE.md fallback), and hypergraph-adopt (conversion path for repos with a past) [rec: spring-fog-0600] [rec: late-isle-6483].
- hypergraph-adopt covers both modes — A: import an existing Flywheel graph verbatim as the fork with mandatory `archive:` config; B: author 1–3 prehistory nodes from the repo itself — plus the epoch marker, distillation into an honest state graph (per-branch subagent mining, id-prefix→slug resolution, user interview for invisible dead ends), the init tail, and onboarding install; `templates/agents-block.md` (idempotent sentinel block with contract reconciliation, symlink-safe) ships with it [rec: late-isle-6483].
- Field correction from tbinn: the mode-B marker parents on the newest prehistory node, not `--root` — the CLI correctly refuses a second parentless root per graph; skill and SPEC amended [rec: stormy-dew-2969].
- install.sh symlinks the skill dirs into ~/.claude/skills; relative reference symlinks (references/spec.md → ../../../SPEC.md) survive installation because they resolve against physical location [rec: spring-fog-0600].
- Orient validated end-to-end by a fresh agent (4/6 calls); skill updated to read component bodies via one flywheel_get_node_children page [rec: steep-cell-5173].
- hypergraph-record covers directive decision nodes: Operator/agent intent is recorded with impact declarations before any work exists, so gaps reach the frontier through the record graph [rec: patient-limit-9007].
- Onboarding outside the skills channel: AGENTS.md states the record discipline as non-negotiable for arriving agents, with CLAUDE.md containing only `@AGENTS.md`; added after blind test #1 (machinery used, obligation missed) and validated by blind test #2 — a controlled retest with AGENTS.md as the only changed variable produced full compliance: orient, record, defer reconcile [rec: tiny-sunset-0847] [rec: little-bar-4131].

## Negative knowledge

- [scope: hypergraph-orient reading state-node bodies on the Flywheel backend | confidence: medium | evidence: steep-cell-5173] flywheel_get_node_tree with projection=full returns topology-only payloads — it cannot substitute for get_node_children/get_node when bodies are needed.
- [scope: protocol discoverability by uninstructed agents | confidence: high | evidence: tiny-sunset-0847, little-bar-4131] README/SPEC presence and installed skills do not by themselves cause a protocol-naive agent to record its work — it can use the graphs as app data without recognizing the obligation; repo-level agent onboarding (AGENTS.md/CLAUDE.md) is required, and the controlled retest confirms it is also sufficient.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-fog-0600 — four skills + installer landed, installed, registered (M4)
- steep-cell-5173 — orient validated cold-start; body-reading recipe corrected (M5)
- patient-limit-9007 — directive-decision-node guidance added to hypergraph-record
- tiny-sunset-0847 — AGENTS.md onboarding added after blind test #1
- little-bar-4131 — blind test #2 validated AGENTS.md; discoverability entry raised to high confidence
- late-isle-6483 — fifth skill hypergraph-adopt + agents-block template
- stormy-dew-2969 — mode-B marker parentage corrected from field use
