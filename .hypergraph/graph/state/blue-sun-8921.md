---
node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
slug: blue-sun-8921
title: Storage & node format
created_at: '2026-08-06T21:41:11.400955+00:00'
parents:
- wandering-sun-8831
summary: The node files are the only storage; INTERFACE.md is a portability contract with one shipped implementation. Names and repo-relative paths are the portable identity; state topology is writable, record topology is not.
flywheel:
  node_id: d82f019d-c029-5999-ad8c-332abcfaa3ee
  slug: blue-sun-8921
  revision: 11
  pushed_at: '2026-08-14T13:37:28+00:00'
  content_sha256: cd29650e5f208989ada5a3b1177c9984b8299de641d4a791404e14582325fc90
  parents_sha256: 7581a2a3ab3e0f666772fb38ea612fbca98197235dbd11585614ad362efda1a1
  parents:
  - 2b993e9c-708e-5940-a67f-cf80aa0955e4
---
Status: working

## Current

What a node *is* on disk, and what a store would have to satisfy to hold one instead [rec: crimson-dawn-7137] [rec: old-dawn-8747].

- **The node files are the only storage.** Markdown under `.hypergraph/graph/{record,state}/<slug>.md` is the source of truth; there is no `backend:` key to select, and a missing one means the node files, correct by construction because there is one thing it can mean [rec: old-dawn-8747] [rec: calm-sand-3399].
- **The format**: YAML frontmatter — `node_id` (uuid5 of the slug), `slug`, `title`, `created_at`, `parents` as slugs, optional `tags:` names, optional `artifacts:` paths, optional bookkeeping blocks — over a body that is the node content byte-for-byte, so `check`, `render` and `viz` parse it unchanged [rec: old-dawn-8747]. The integration surface is one file format plus `export`: the checker, renderer and visualizer were never modified for any of this, because they only ever read the two JSON exports [rec: old-dawn-8747].
- **Two identity blocks that are never confused**: `origin:` — where an imported node came from, immutable, written once by `import --fork`, read by nothing — and `flywheel:` — this project's own mirror identity and change-detection baseline. Before the split one field did all three jobs at once [rec: copper-moss-3669] [rec: tender-moss-3792]. They are not peers: `origin:` is protocol, the mirror block is bookkeeping [rec: silver-ember-3035].
- **`backend/INTERFACE.md` is a portability contract, not a menu** [rec: silver-ember-3035]. It names ~10 abstract operations [rec: crimson-dawn-7137], one implementation ships — `backend/local-adapter.md`, node files in the repo — and the table states what a *replacement* store would have to satisfy. Two adapters existing at once was what previously proved the table swappable [rec: old-dawn-8747]; the claim now rests on the table's shape.
- **Op 7's concurrency story is a body-hash compare-and-swap** (`--expect`) with git as the merge substrate, and `--reconcile` is the mechanical I3 gate [rec: old-dawn-8747] [rec: silver-ember-3035].
- **Both optional ops are implemented, and neither asks the store for anything** [rec: clear-moss-4527] [rec: shady-bay-7654]. A tag is a name in frontmatter with the vocabulary in a committed `.hypergraph/tags.yml` keyed by graph kind; an artifact is a repo-relative path in frontmatter. INTERFACE's old clause — *"artifacts and tags are optional; the shipped implementation omits artifacts"* — was false the moment op 9 landed and was rewritten in place [rec: shady-bay-7654].
- **Names and paths are the portable identity, for the same reason `parents:` holds slugs.** Every store mints its own tag ids and artifact ids, so an id is as local to a store as a mirror's slug is. `synth_tag` derives a colour pair from `sha256(name)`, which is what keeps `tags.yml` optional; an artifact path is typed cwd-relative like `git add` and stored repo-root-relative, with the root from git rather than a config key, because an absolute path committed into a repo goes stale the moment the checkout moves [rec: clear-moss-4527] [rec: shady-bay-7654]. A store implementing op 9 therefore *copies* evidence and never owns it.
- **Three contract notes INTERFACE states rather than leaving to be discovered** [rec: shady-bay-7654] [rec: clear-moss-4527]: artifacts attach to record nodes and to nothing else, because a state node is rewritten on every reconcile and a pointer hung there has no stable owner; a tag is annotation and no invariant reads one, so a claim living only as a tag is invisible to the protocol; and prose and the list are both required and are not the same thing — `## Method`/`## Result` explains a path, `artifacts:` enumerates it so a tool can find it without parsing prose.
- **Assignment is an atomic replace, and that property is load-bearing**: a re-issued assignment cannot duplicate anything, so a 409 on one may be re-read and re-issued in place — the only operation here where that is safe. A *declaration* has no such property, since deleting a tag definition un-tags every node that used it, so an implementation must resolve an existing name before declaring [rec: clear-moss-4527].
- **Two constraints op 10 must leave room for, both learned from a live backend** [rec: early-mesa-8507]: a store may constrain *where* a tag lives, not merely that it exists, which makes assignment order part of the contract; and a tag creation may move revisions graph-wide, so a node's revision can change without that node being written. The second is sharper — an optimistic lock held across an unrelated operation is stale, and nodes nobody touched read as drift.
- **Two storage-path defects, both found by the first mode A adoption run without its author** [rec: clever-ledge-6588]. `adopt --init` derived the config's root `node_id` from the slug unconditionally, but a mode A root arrives through `import --fork`, which preserves the archive's id verbatim — so the project would have published under an id nothing else in the repo used; it now reads the node's own id. And `mirror pull` and `export` both defaulted to the same cache path, so the first export destroyed the legacy pull, which is the only record of what stayed on the archive; the pull now writes `legacy-*.json`.
- **A state node's parents may move; a record node's may not** [rec: autumn-glade-5802]. `hypergraph update --parent/--root` re-homes a state node with the same compare-and-swap and the same `--reconcile` gate as a body write, refusing a self-parent, a second root and any edge that would close a cycle. Record topology is causal history.

## Negative knowledge

- [scope: mode-A adoption mirrors | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] a mirror can verify clean while holding almost none of the graph. `import` stamped every node with the archive's `flywheel:` identity, so `push_plan` omitted all of them as already-pushed — they were on Flywheel, just on somebody else's graph — and `push --verify` was run against an export that spliced the archive roots in, which made those orphaned ids resolve. Measured on a3go: 3 record nodes mirrored of 111, with `push --plan` reporting 0 creates and verify exiting 0. **Now mechanically unreachable**: `mirror_root_ids()` refuses to treat an `archive:` root as a mirror root [rec: silver-ember-3035].
- [scope: documenting a mechanism agents should not use | confidence: high | evidence: silver-ember-3035] a reference doc symlinked into a skill's `references/` is part of that skill's context whether or not the skill's own body mentions it. Deleting the backend-dispatch preambles alone would have left every MCP recipe, the lease dance and the rate budgets one hop away. Moving the prose out of the symlinked file — not merely stopping citing it — is what makes a mechanism actually absent.

## Provenance

- wandering-rice-9747 — component seeded at project init
- spring-pine-7256 — the markdown-pointers decision the interface encodes
- crimson-dawn-7137 — INTERFACE.md and the first adapter landed (M2)
- old-dawn-8747 — the local adapter, the node format, and the round-trip integration surface
- kind-valley-8040 — adapter doc corrected from the first live mirror push
- copper-moss-3669 — fork-import decision: one field doing three jobs
- tender-moss-3792 — the origin:/flywheel: split shipped; re-home vs adopt documented
- northern-willow-0469 — the stub-mirror consequence proven live on a3go
- silver-ember-3035 — INTERFACE.md re-scoped as a portability contract; mirroring moved out
- calm-sand-3399 — config schema migrated; the backend: key retired
- clear-moss-4527 — op 10 shipped: names as the portable identity, and the no-invariant-reads-a-tag note
- early-mesa-8507 — two host constraints op 10 has to leave room for
- shady-bay-7654 — op 9 shipped as repo-relative paths, with its three contract notes
- clever-ledge-6588 — two storage-path defects found by the first unattended mode A run
- autumn-glade-5802 — state topology becomes writable through update --parent, with record topology refused
- late-sage-5549 — re-homed under Protocol mechanics and given the storage half of the mirror node
