---
node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
slug: dry-wildflower-2260
title: Skills
created_at: '2026-08-06T21:41:21.141576+00:00'
parents:
- cool-king-8586
summary: Four skills + AGENTS.md onboarding, validated by controlled blind retest; discoverability lesson at high confidence.
flywheel:
  node_id: 0a4e4167-71ec-545b-a5b7-036016974a9d
  slug: dry-wildflower-2260
  revision: 5
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: 79f8f956de4594242fababe3bf4ec1d32fab42ba33a2635cfaabd9e60cb8d92b
---
Status: working

## Current

- Four skills landed and installed: hypergraph-init (roots + skeleton + config), hypergraph-record (causally-parented record nodes, always declares State Impact, never writes state), hypergraph-reconcile (single writer: folds impacts, advances HWM, regenerates STATE.md, runs check), hypergraph-orient (read-only frontier brief, ≤~6 tool calls, STATE.md fallback) [rec: spring-fog-0600].
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