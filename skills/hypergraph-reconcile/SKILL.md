---
name: hypergraph-reconcile
description: The single-writer librarian pass for a Hypergraph project - folds declared State Impacts from unreconciled record nodes into the state graph, advances the high-water mark, regenerates STATE.md, and runs the invariant checker.
---

# Hypergraph Reconcile

The **only** writer of state nodes (SPEC I3). Reads record nodes past the high-water
mark, folds their declared impacts into the distilled state graph, advances the HWM,
and regenerates STATE.md. Protocol: [spec.md](references/spec.md); backend recipes:
[flywheel-adapter.md](references/flywheel-adapter.md).

## When To Use

- After one or more hypergraph-record commits (the user asks to reconcile, or `check`
  reports unreconciled nodes / pending impacts).
- Before a milestone, handoff, or fresh-agent onboarding, so the frontier is current.

Not for recording new knowledge — if you learn something *during* reconcile, stop and
record it first (SPEC I1), then reconcile it in.

## Workflow

1. **Load context**: `.hypergraph/config.yml`; read the state root
   (`flywheel_get_node`) and parse `## Reconciliation` for the current HWM.
2. **Export the record graph**: `flywheel_export_subgraph` on the record root
   (`include_descendants: true`) → `.hypergraph/cache/record.json`.
3. **Enumerate unreconciled nodes**: record nodes created after the HWM node, in
   causal/created order. If none, regenerate STATE.md and stop.
4. **Fold impacts, per state node** (batch all pending deltas for a target into one
   write). For each affected state node, using the get → lease → commit → release
   sequence (adapter §7):
   - Apply the deltas: flip `Status:`, add/update claims in `## Current` with inline
     `[rec: <slug>]` citations, append `## Provenance` lines for every record node
     folded in (SPEC I4, I6).
   - `NEW` targets: create the state node under the architecturally right parent
     (usually the state root) via `flywheel_commit_new_node`, full state-node template.
   - Negative knowledge: entries carry scope, confidence, evidence slugs; a
     generalized scope needs a `decision:` slug pointing at a decision record node —
     if none exists, keep the scope narrow (SPEC I7).
   - **Compact while you're there**: merge redundant claims, trim superseded detail
     (the record graph keeps history), keep the node readable at a glance.
   - Judgment calls beyond the declared delta (e.g. an impact implies a status flip it
     didn't declare) are allowed but must stay derivable from the cited record nodes
     (SPEC I8) — when in doubt, fold only what was declared and note the discrepancy.
5. **Advance the HWM**: lease + commit the state root with `high_water_mark:` = the
   newest record node folded in and `reconciled_at:` = now (SPEC I5). Do this *after*
   the folds so a crashed run under-reports rather than skips.
6. **Re-export both graphs** → `.hypergraph/cache/{record,state}.json`, then:
   ```
   uv run <hypergraph repo>/tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
   uv run <hypergraph repo>/tools/hypergraph.py check --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json --config .hypergraph/config.yml
   ```
7. **Report honestly**: what was folded, what was created, checker output verbatim —
   including violations you could not fix. Impacts that could not be applied cleanly
   (ambiguous target, contradictory deltas) get reported, not guessed at.

## Guardrails

- Single writer: do not run two reconciles concurrently. A 409 `stale committed
  revision` mid-run means another writer is violating I3 — stop and report it.
- Full-payload commits: `flywheel_commit_node` replaces the whole body; compose the
  complete new content locally before committing. Release leases promptly.
- Never delete record nodes, never edit record content, never add cross-graph edges.
- Every claim you write must cite a record slug you actually read (SPEC I1/I4) — no
  provenance from memory.
- STATE.md is generated output; never hand-edit it to "fix" a checker complaint.
