---
name: hypergraph-reconcile
description: The single-writer librarian pass for a Hypergraph project - folds declared State Impacts from unreconciled record nodes into the state graph, advances the high-water mark, regenerates STATE.md, and runs the invariant checker.
---

# Hypergraph Reconcile

The **only** writer of state nodes (SPEC I3). Reads record nodes past the high-water
mark, folds their declared impacts into the distilled state graph, advances the HWM,
and regenerates STATE.md. Protocol: [spec.md](references/spec.md).

## Backend dispatch

Read `backend:` from `.hypergraph/config.yml` before touching anything:

- **`local`** → [local-adapter.md](references/local-adapter.md). Node files in the repo;
  every state write goes through `hypergraph update <slug> --expect <sha> --reconcile`
  (§7) or `hypergraph new state … --reconcile` (§1/§2). Both refuse without
  `--reconcile` — that flag is the I3 gate, so only this skill ever passes it.
- **`flywheel`** → [flywheel-adapter.md](references/flywheel-adapter.md). MCP get →
  lease → commit → release.

A missing key means `flywheel`. If `mirror: flywheel` is set alongside `backend: local`,
refresh the mirror at the end (step 8).

## When To Use

- After one or more hypergraph-record commits (the user asks to reconcile, or `check`
  reports unreconciled nodes / pending impacts).
- Before a milestone, handoff, or fresh-agent onboarding, so the frontier is current.

Not for recording new knowledge — if you learn something *during* reconcile, stop and
record it first (SPEC I1), then reconcile it in.

## Workflow

1. **Load context**: `.hypergraph/config.yml`; read the state root (its node file, or
   `flywheel_get_node`) and parse `## Reconciliation` for the current HWM.
2. **Export the record graph** → `.hypergraph/cache/record.json`:
   `hypergraph export --config .hypergraph/config.yml` (`local`, writes both graphs) or
   `flywheel_export_subgraph` on the record root with `include_descendants: true`
   (`flywheel`).
3. **Enumerate unreconciled nodes**: record nodes created after the HWM node, in
   causal/created order — `check` prints the count and the pending impact targets. If
   none, regenerate STATE.md and stop.
4. **Fold impacts, per state node** (batch all pending deltas for a target into one
   write). For each affected state node, using read-sha → compose → `hypergraph update
   --expect --reconcile` (local-adapter §7) or get → lease → commit → release
   (flywheel-adapter §7):
   - Apply the deltas: flip `Status:`, add/update claims in `## Current` with inline
     `[rec: <slug>]` citations, append `## Provenance` lines for every record node
     folded in (SPEC I4, I6).
   - `NEW` targets: create the state node under the architecturally right parent
     (usually the state root) — `hypergraph new state --parent <state-root-slug>
     --status … --prov "<record-slug> — why" --reconcile`, or
     `flywheel_commit_new_node` with the full state-node template.
   - Negative knowledge: entries carry scope, confidence, evidence slugs; a
     generalized scope needs a `decision:` slug pointing at a decision record node —
     if none exists, keep the scope narrow (SPEC I7).
   - **Compact while you're there**: merge redundant claims, trim superseded detail
     (the record graph keeps history), keep the node readable at a glance.
   - Judgment calls beyond the declared delta (e.g. an impact implies a status flip it
     didn't declare) are allowed but must stay derivable from the cited record nodes
     (SPEC I8) — when in doubt, fold only what was declared and note the discrepancy.
5. **Advance the HWM**: rewrite the state root's `## Reconciliation` with
   `high_water_mark:` = the newest record node folded in and `reconciled_at:` = now
   (SPEC I5), through the same op-7 sequence. Do this *after* the folds so a crashed run
   under-reports rather than skips.
6. **Re-export both graphs** → `.hypergraph/cache/{record,state}.json` (`hypergraph
   export --config .hypergraph/config.yml`, or two `flywheel_export_subgraph` calls),
   then:
   ```
   uv run <hypergraph repo>/tools/hypergraph.py render --state .hypergraph/cache/state.json --config .hypergraph/config.yml -o STATE.md
   uv run <hypergraph repo>/tools/hypergraph.py check --record .hypergraph/cache/record.json --state .hypergraph/cache/state.json --config .hypergraph/config.yml
   ```
7. **Commit** (`local` only): `git add .hypergraph/graph STATE.md` — the reconcile is not
   durable until the node files are committed.
8. **Refresh the mirror** (`local` + `mirror: flywheel` only): `hypergraph push --plan`,
   execute the ops per local-adapter §Mirroring, then `hypergraph push --record-result`
   and commit the frontmatter updates. A plan that exits 1 carries a record-graph
   violation — fix it locally, do not mirror it. Then close the loop:
   - **Slug legend**: `hypergraph push --legend` → commit/update the mirror-only
     legend node (title exactly "Hypergraph mirror slug legend", parented to the
     mirror's record root; find it among the root's children by title, lease +
     commit if it exists, create otherwise). It never gets a local node file.
   - **Verify**: fetch a fresh export of both mirror roots
     (`flywheel_export_subgraph`, `include_descendants: true`, one call with both
     node_ids) and run `hypergraph push --verify --against <export.json>`. Exit 1
     means drift — report each DRIFT line; local files are canonical, so drift is
     fixed by re-pushing (or investigating who wrote to the mirror), never by
     editing local nodes to match the mirror.
9. **Report honestly**: what was folded, what was created, checker output verbatim —
   including violations you could not fix. Impacts that could not be applied cleanly
   (ambiguous target, contradictory deltas) get reported, not guessed at.

## Guardrails

- Single writer: do not run two reconciles concurrently. A refused `--expect` (`local`)
  or a 409 `stale committed revision` (`flywheel`) mid-run means another writer is
  violating I3 — stop and report it.
- Full-payload writes: both `hypergraph update --body` and `flywheel_commit_node`
  replace the whole body; compose the complete new content locally before committing.
  Release Flywheel leases promptly.
- Never delete record nodes, never edit record content, never add cross-graph edges.
- Every claim you write must cite a record slug you actually read (SPEC I1/I4) — no
  provenance from memory.
- STATE.md is generated output; never hand-edit it to "fix" a checker complaint.
