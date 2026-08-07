---
node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
slug: wandering-sun-8831
title: Checker tooling
created_at: '2026-08-06T21:41:18.171074+00:00'
parents:
- cool-king-8586
summary: 'check/render/viz green over fixtures and real exports; 22 tests; known blind spots: unrecorded work, stale cache exports.'
flywheel:
  node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
  slug: wandering-sun-8831
  revision: 5
  pushed_at: '2026-08-07T18:12:06.426139+00:00'
  content_sha256: 3f0fea20cd65b7ea3721ca6328972a348f015f7901f311fb1b748c1c26913e49
---
Status: working

## Current

- tools/hypergraph.py (single-file uv script, pyyaml only) implements `check` — mechanical validation of I2, I4, I5, I6, I7 over offline JSON exports with nonzero exit on violations, I1 proxied as warnings — and `render` — STATE.md with frontier first (broken → blocked → open) and architecture tree [rec: flat-pine-9555].
- Third subcommand `viz` added, reusing the checker's section/impact/citation parsers and export normalization to emit the interactive visualization (see the Visualization component) [rec: long-tree-4179].
- Five more subcommands implement the local backend — `export`, `import`, `new`, `update`, `push` — while the `check`/`render`/`viz` code paths were left untouched; the tool stays network-free, so Flywheel mirroring is emitted as a plan the skill layer executes [rec: old-dawn-8747].
- The tool now enforces protocol invariants at authoring time, not only at check time: `new` runs the real checker over a candidate node before writing it (a bad impact target exits 2 with nothing written), `--reconcile` gates every state write (I3), and `update` refuses record nodes outright [rec: old-dawn-8747].
- Test suite green: 50 pytest cases over committed fixtures — 11 checker + 11 viz + 28 local backend [rec: sleepy-branch-3744]. The strongest local-backend guarantee is the round-trip: importing the clean fixture into node files and exporting back yields node-for-node identical graphs that still check clean [rec: old-dawn-8747].
- Earlier suite state and what it covers: clean fixture passes with zero violations/warnings; each seeded violation fixture fails with exactly its invariant ID; CLI exit codes, staleness reporting, and viz determinism verified [rec: flat-pine-9555] [rec: long-tree-4179] [rec: morning-rain-7488] [rec: still-forest-9161].
- Verified against real Flywheel exports: normalizes the live edge encoding (incoming_ids as parents), alongside parent_ids/parents fixture forms [rec: steep-cell-5173].

## Negative knowledge

- [scope: parsing flywheel_export_subgraph output | confidence: high | evidence: steep-cell-5173] the export encodes edges as incoming_ids/outgoing_ids, not parent_ids — a parser reading only parent_ids sees every node as a root.
- [scope: detecting protocol omissions with `check` | confidence: high | evidence: tiny-sunset-0847] the checker only sees declared-but-unreconciled impacts; work never recorded to the record graph is invisible to it by construction — repo HEAD sitting ahead of the newest record node's head_commit_sha is the detectable proxy (repo-drift check, SPEC future work).
- [scope: trusting `check`'s unreconciled count | confidence: high | evidence: little-bar-4131] the count is computed from cache exports, not the live graph — an agent that records after its last export leaves check reporting 0 unreconciled while the live graph is ahead; comparing the export's exported_at against recent activity is the fix (export-freshness check, SPEC future work).
- [scope: guarding CLI-generated markdown sections | confidence: high | evidence: sleepy-branch-3744] a substring test for a heading rejects prose that merely mentions it — anchor heading guards to line starts.

## Provenance

- wandering-rice-9747 — component seeded at project init
- flat-pine-9555 — checker + renderer implementation and green test run (M3)
- steep-cell-5173 — live-export verification + edge-encoding fix (M5)
- long-tree-4179 — viz subcommand added sharing the checker's parsers
- morning-rain-7488 — suite to 22 tests (viz template/determinism cases)
- still-forest-9161 — viz test refresh under the unified view (count stays 22)
- tiny-sunset-0847 — blind-test finding: unrecorded work is invisible to check
- little-bar-4131 — cache-freshness facet: stale exports under-report unreconciled work
- old-dawn-8747 — five local-backend subcommands; authoring-time validation; round-trip guarantee
- sleepy-branch-3744 — corrected suite count (50) and the heading-guard fix
