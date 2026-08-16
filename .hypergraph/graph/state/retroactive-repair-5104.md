---
node_id: 67e77d92-1968-5854-b393-2649c2b9c00f
slug: retroactive-repair-5104
title: Retroactive repair
created_at: '2026-08-09T23:22:20+00:00'
parents:
- wandering-sun-8831
summary: 'upgrade --graph (formerly heal): typed graph repairs carrying a capability backwards into a repo that adopted before it existed. Detect-only until --apply; two healers, one proven live on 188 nodes.'
flywheel:
  node_id: e6fbea9b-ac04-5b61-9545-315b8f02da43
  slug: lingering-credit-5743
  revision: 6
  pushed_at: '2026-08-16T18:35:51+00:00'
  content_sha256: a6635434ad2d8f364d4bc996ebd47ca24e64f5404e133edad22ffd50763516e1
  parents_sha256: 7581a2a3ab3e0f666772fb38ea612fbca98197235dbd11585614ad362efda1a1
  parents:
  - 2b993e9c-708e-5940-a67f-cf80aa0955e4
---
Status: working

## Current

`hypergraph upgrade --graph` carries a capability **backwards** into a repo that adopted before the capability existed. It is a registry of typed graph repairs, not a migration script. At 0.0.11 the standalone `heal` verb folded into `upgrade` as its graph half — one verb for bringing an adopted repo current, with `--graph` naming the cost boundary: bare `upgrade` refreshes copies and `git checkout` undoes it, while the graph half rewrites content and spends a mirror-write budget that cannot be un-spent. `heal` survives as a hidden deprecated alias through the 0.0.x series [rec: simple-ocean-1716] [rec: clear-moss-4527] [rec: violet-shade-9541].

- **Dry run is the default**, the one inverted default in this tooling, and plain detected drift exits **0** — unhealed drift is a capability that landed after your adoption, not a broken invariant. `--fail-on-drift` opts into exit 1 [rec: clear-moss-4527].
- **Nothing is persisted.** No "have I run?" flag: the written data is the state and `detect` re-derives it from the files, the property that already makes `push_plan` a safe resume primitive. A runtime check asserts every drift a healer *claimed* to heal is absent from the next `detect`, so a healer that reports more than it did fails loudly [rec: clear-moss-4527].
- **A healer's write targets come from `flywheel:` and never from `origin:`**, enforced by `heal_write_targets()` as the only sanctioned way to obtain one — in an adopted repo every `origin.node_id` is an id on the frozen archive, same shape, same credentials, one dict lookup away [rec: clear-moss-4527]. It also refuses on an uncommitted graph directory and on the protocol's own checkout.
- **Healer #1 is `tags`, and it is proven end to end against a live mirror** [rec: early-mesa-8507]: on neural-whoop, 22 definitions created and 486 assignments across 188 of 189 nodes, **per-tag counts identical to the archive**, `push --verify` 0 drift, a second run reporting 0 changes, and the archive root still at revision 28. Every guard held under real conditions — `origin:` was never a write target across all 212 pushed nodes, and every `--apply`-less invocation wrote nothing.
- **Three host behaviours broke it first and none was findable by reading** [rec: early-mesa-8507]. All three fixes landed in the transport or in `push_tags`, and **the healer framework itself did not change to accommodate any of them** — which is better evidence for its shape than a second healer would have been, because it was not designed for.
- **The extensibility claim is now evidence, and it came in under budget** [rec: shady-bay-7654]. The framing was that healer #2 costs one registry entry and one comparator; `HEAL_ARTIFACTS` cost **zero** new comparator entries and **one** registry entry, with the only real work teaching `side_from_local` which frontmatter block to read ids out of.
- **Healer #2 is `artifacts`, and what it does *not* do is the finding** [rec: shady-bay-7654]. It inventories what the frozen archive still holds per node, frontmatter only, offline-capable, with no mirror phase at all, so it never needs `heal_write_targets` and is fully `git checkout`-reversible. It deliberately does **not** repatriate the archive's bytes: those are not in the repo, so re-uploading them would leave the mirror holding evidence the repo cannot regenerate.
- **The normal case needs no healer at all, and that difference from tags is the point.** An adoption that predated tags *lost the names* — they were on the archive and nothing local held them [rec: fresh-spire-9002]. An adoption that predated artifacts lost **nothing**, because there was nothing local to lose, and a repo adding paths to old record nodes today is served by `push` alone. The registry's second member is narrower than its first because of a real asymmetry between the two capabilities [rec: shady-bay-7654].

## Negative knowledge

- [scope: repairing graph content in someone else's repo | confidence: high | evidence: clear-moss-4527 | decision: simple-ocean-1716] a command that rewrites graph content cannot borrow the defaults of one that refreshes copies. `upgrade` acts by default because every effect of it is `git checkout`-reversible; a heal rewrites ~188 files outside any commit flow and spends mirror writes that cannot be un-spent, so acting by default would make the safe reading of `hypergraph heal tags` the destructive one. The inverted default is the design, not a precaution.
- [scope: reusing a source graph's own strings when repairing | confidence: high | evidence: clear-moss-4527] a healer and the importer it repairs *after* must produce byte-identical values, or the repair invents a second spelling of the same thing. heal first resolved tag ids through the raw export, so a healed repo got `★ studio-baseline` where an imported one got `studio-baseline` — two names for one tag, which is the duplicate-definition failure by another route. Found by running the healer against the real archive, not by reading it. Route both paths through the same transliteration and assert they agree node for node.

## Provenance

- simple-ocean-1716 — the decision that opened this: heal is a framework, separate from upgrade because it rewrites graph content
- clear-moss-4527 — built and trialled offline end to end
- fresh-spire-9002 — the field loss that made a backward path necessary rather than nice
- early-mesa-8507 — the live run: 188 nodes recovered, and the three host behaviours that took
- shady-bay-7654 — healer #2, and the extensibility claim settled at zero comparators and one registry entry
- autumn-glade-5802 — the single-node canary that proved state re-parenting against the live mirror
- violet-shade-9541 — the fold: heal becomes upgrade --graph, alias deprecated
- vast-birch-5192 — Operator directive: the release label is 0.0.11, not 0.9.0
