---
node_id: ea4a4774-70e8-517f-9bb2-0f625e7f5ca7
slug: mellow-tooth-5722
title: 'Deep-dive: flywheel-local — the offline git-for-research sibling, compared'
created_at: '2026-08-30T13:18:10+00:00'
parents:
- crimson-dawn-7137
summary: ''
flywheel:
  node_id: f3588eeb-e3d6-5ce4-8163-f393602205bc
  slug: round-fog-3920
  revision: 0
  pushed_at: '2026-08-30T13:18:35+00:00'
  content_sha256: 518bb20537f9e1cf4d259c163603690dbc1721f1b644607977fb042742bd5eb0
  parents_sha256: 74c2e3995b3a6af01b5ea18126905d703c1c8df93e06e687ec41daa62e2e584f
  parents:
  - 31dc7dde-666d-527e-806f-4ba4dd119cc1
---
## What

A comparative deep-dive of `../flywheel-local` — a sibling project (built 2026-08-28,
in one day, by parallel worktree agents) that implements "git for research" offline:
a local research-DAG workspace (`fwl`) with content-addressed snapshots, single-file
share bundles, and a node-level three-way merge. Read all 8 ADRs, the full source
(`src/flywheel_local/`, ~18 modules), the test system, and the 89-node hosted
Flywheel graph that documents its build (root `nameless-night-0689`).

## Why

Operator directive: explore the project, its decisions, and its hosted graph, and
assess how its ideas relate to this protocol. Exploration only — no incorporation
decided. The two projects share the node/slug/tag data model (both mirror hosted
Flywheel) but sit at different layers, so the comparison maps the seam between them.

## Method

Read `README.md`, `AGENTS.md`, `docs/adr/0001–0008`, `docs/testing/surface-map.md`;
rendered the hosted graph via `flywheel nodes:render:tree` (89 nodes, 12 deep) and
fetched key node bodies (root, the "We hit the exact problem" Finding, the remote-
origin and graph-replay idea nodes). A subagent read every source module plus the
test spine and reported mechanisms. Compared against SPEC.md v0.0.13, STATE.md, and
docs/internal/{mirror,flywheel}.md.

## Result

**What flywheel-local is.** One graph per workspace in a hidden, gitignored `.fwl/`;
one canonical Markdown-with-YAML-frontmatter file per node (round-trip law:
`serialize(parse(x)) == x`, doctor-enforced); an append-only content-addressed
snapshot store (manifest hash = snapshot id, timestamps outside the hash); `.fwlb`
bundles that carry tip content + lineage *ids* (the receiver's store supplies the
merge base); a three-way merge where edges/tags merge as base-aware set union (never
conflict), only Markdown bodies ever get conflict markers, and everything else
reports in `CONFLICTS.md` so node files stay parseable mid-conflict; no revision
integers anywhere (content hashes are the only versioning truth); single-writer
workspaces with parallelism via bundles (their ADR-0005 ≈ our I3 at a different
layer). CLI: hosted Flywheel verbs verbatim for graph ops, bare git verbs for the
version layer.

**Key findings for this protocol:**

1. **Different layers, same substrate.** flywheel-local is version control *for one
   graph* (storage, snapshots, merge). Hypergraph is a knowledge *discipline over
   two graphs* (record/state split, impact declarations, reconcile, frontier). They
   are complementary: `fwl`'s graph ops are roughly our backend/INTERFACE.md
   operations implemented locally — it is a plausible second backend adapter shape.
2. **The direct design collision: ADR-0002 vs our local adapter.** They ruled that
   the graph must be *decoupled from the code repo's git timeline* (checkout must
   never rewind research memory; git line-merge is an unguarded second door). We
   deliberately chose the opposite: node files committed in-repo, merged through
   git, offline, PR-reviewable. Their "Finding: we hit the exact problem we are
   building this to solve" is real evidence: parallel worktree agents saw
   branch-sliced `docs/adr/` (two agents both drafted ADR-0005) while the shared
   hosted graph kept every agent coherent. Under our protocol the same slicing
   exists — record nodes on unmerged branches are invisible to sibling worktrees
   (SPEC acknowledges it: "a side branch replays only the tail it can see"). Our
   mitigations are one-file-per-node append-only merge + loud slug add/add
   conflicts + record-on-any-branch/reconcile-on-main; theirs is decoupling. The
   tension is now documented, not resolved.
3. **Their finding is independent evidence *for* our premise.** A shared graph that
   does not fork with the code kept parallel agents coherent through a real
   collision — supporting the record-graph/shared-memory hypothesis this protocol
   leads with.
4. **Portable ideas worth considering later (no decision made):** (a) the
   surface-map testing spine — a table of falsifiable promises with stable IDs,
   pytest markers declaring which promise each test proves, and a gap report that
   *derives* coverage from collection so it cannot drift; (b) canonical
   serialization as a checked law (we hash bodies but do not enforce round-trip
   canonicality of node files); (c) narrated executable scenarios as documentation;
   (d) `fwl viz --html --replay` (timeline scrubber over embedded snapshots) as a
   feature idea for the hypergraph-viz consumer of our export contract; (e) their
   graph-discipline rules (one phase tag + one type tag, anchor nodes with dual
   parents, "no willy-nilly nodes", ADR numbers allocated from the graph not the
   file tree).
5. **What not to take:** snapshot store, bundles, semantic merge, lockfile, stage
   leases — git gives us all of that because our record graph is append-only,
   one file per node.
6. **Gaps noted in their build** (for completeness): `--full` bundle unpacking
   copies store blobs unverified; the doctor checks the working tree only (no store
   fsck); merge results bypass the doctor until the next `status`.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 93c1bf0d3ba3e27d8c54f969075638ae05b3cfc1

## State Impact

none: comparative exploration of a sibling project; no protocol change, status flip, or new claim adopted — any incorporation gets its own decision record
