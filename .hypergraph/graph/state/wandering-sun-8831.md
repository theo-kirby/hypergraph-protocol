---
node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
slug: wandering-sun-8831
title: Checker tooling
created_at: '2026-08-06T21:41:18.171074+00:00'
parents:
- cool-king-8586
summary: 'check/render/viz + local backend + epoch support + push --verify/--legend/--lineage + import --fork; 72 tests green; known blind spots: unrecorded work, stale cache exports, frontmatter summary drift, archive-spliced verify exports.'
flywheel:
  node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
  slug: wandering-sun-8831
  revision: 9
  pushed_at: '2026-08-08T11:35:36+00:00'
  content_sha256: 757d6c9b7ec60b6b9baf2260eab14c3fe34928c9adf1254e9e57470b8f7c8e23
---
Status: working

## Current

- tools/hypergraph.py (single-file uv script, pyyaml only) implements `check` — mechanical validation of I2, I4, I5, I6, I7 over offline JSON exports with nonzero exit on violations, I1 proxied as warnings — and `render` — STATE.md with frontier first (broken → blocked → open) and architecture tree [rec: flat-pine-9555].
- Third subcommand `viz` added, reusing the checker's section/impact/citation parsers and export normalization to emit the interactive visualization (see the Visualization component) [rec: long-tree-4179].
- Five more subcommands implement the local backend — `export`, `import`, `new`, `update`, `push` — while the `check`/`render`/`viz` code paths were left untouched; the tool stays network-free, so Flywheel mirroring is emitted as a plan the skill layer executes [rec: old-dawn-8747].
- Adoption-epoch support: `check` resolves `epoch.marker` to a created_at cutoff and exempts strictly-older record nodes from I2 (one info finding with the count); an unresolvable marker is a violation; authoring-time validation is never exempted [rec: shady-quill-2790].
- Mirror-integrity subcommands: `push --verify --against <export>` reports missing nodes either side, body-hash and summary mismatches, and revision skew as DRIFT findings (exit 1), exempting the legend node and config-declared `mirror_roots` (the latter added after a false flag on a3go's fresh mirror roots); `push --legend` emits the mirror-only slug-legend body; `import` skips legend nodes [rec: careful-harbor-3902] [rec: humble-clover-7048]. `push --lineage` renders the mirror record root's body from the config `archive:` block (errors when there is none), and `push --plan` warns on stderr above 200 creates, naming incremental result-recording and epoch-split [rec: tender-moss-3792].
- `import --fork` splits the two jobs the `flywheel:` block was doing at once: the source graph's ids go to a new `origin:` block (immutable provenance, read by nothing), and `flywheel:` is omitted, so `push_plan` plans every imported node as a `create` under roots the project owns. Plain `import` is byte-identical to before — it still serves re-homing a graph you own. No logic change was needed in `push_plan` or `verify_mirror`, and `check` reads neither block, so I1-I8 are untouched [rec: tender-moss-3792].
- The tool now enforces protocol invariants at authoring time, not only at check time: `new` runs the real checker over a candidate node before writing it (a bad impact target exits 2 with nothing written), `--reconcile` gates every state write (I3), `update` refuses record nodes outright, and `new state` rejects pre-scaffolded bodies that would duplicate the CLI-generated template sections [rec: old-dawn-8747] [rec: careful-harbor-3902].
- Test suite green: 72 pytest cases over committed fixtures — checker (incl. 4 epoch cases), viz, and local backend (incl. verify/legend/drift, fork-import, and skills-install cases) [rec: tender-moss-3792]. The strongest local-backend guarantee is the round-trip: importing the clean fixture into node files and exporting back yields node-for-node identical graphs that still check clean [rec: old-dawn-8747].
- Verified against real Flywheel exports: normalizes the live edge encoding (incoming_ids as parents), alongside parent_ids/parents fixture forms [rec: steep-cell-5173].

## Negative knowledge

- [scope: parsing flywheel_export_subgraph output | confidence: high | evidence: steep-cell-5173] the export encodes edges as incoming_ids/outgoing_ids, not parent_ids — a parser reading only parent_ids sees every node as a root.
- [scope: detecting protocol omissions with `check` | confidence: high | evidence: tiny-sunset-0847] the checker only sees declared-but-unreconciled impacts; work never recorded to the record graph is invisible to it by construction — repo HEAD sitting ahead of the newest record node's head_commit_sha is the detectable proxy (repo-drift check, SPEC future work).
- [scope: trusting `check`'s unreconciled count | confidence: high | evidence: little-bar-4131] the count is computed from cache exports, not the live graph — an agent that records after its last export leaves check reporting 0 unreconciled while the live graph is ahead; comparing the export's exported_at against recent activity is the fix (export-freshness check, SPEC future work).
- [scope: state-node frontmatter summaries under reconcile | confidence: medium | evidence: green-field-8645] `check` parses only node bodies — a reconcile that rewrites a body but not the frontmatter `summary:` leaves drift no invariant can catch; surfaced summaries then contradict the body (worst case observed: an "Open gap" summary on a working node).
- [scope: verifying an adopted project's mirror | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] `push --verify` proves nothing when the archive roots are spliced into the export it is given: the imported nodes' archive-owned ids resolve through the archive subgraph, so a mirror holding 3 record nodes of 111 exits 0. The export must cover the project's own `mirror_roots` alone.
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
- green-field-8645 — audit found summary drift (22 vs 50 tests) and the frontmatter blind spot
- shady-quill-2790 — epoch support; suite to 54
- careful-harbor-3902 — verify + legend + pre-scaffolded-body guard; suite to 60
- humble-clover-7048 — mirror_roots verify exemption; suite to 62
- copper-moss-3669 — fork-import decision: the identity split and mirror-only verification
- tender-moss-3792 — import --fork, push --lineage, scale guard, legend header; suite to 72
- northern-willow-0469 — mirror-only verify proven live on a3go
