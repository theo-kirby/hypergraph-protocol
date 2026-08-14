---
node_id: 67e77d92-1968-5854-b393-2649c2b9c00f
slug: retroactive-repair-5104
title: Retroactive repair
created_at: '2026-08-09T23:22:20+00:00'
parents:
- cool-king-8586
summary: '`hypergraph heal`: a registry of typed graph repairs that carry a capability backwards into a repo that adopted before it existed. Detect-only until --apply, persists nothing, and never treats `origin:` as a write target. Healer #1 (tags) is proven offline on a copy of the real neural-whoop repo; the mirror half has only met FakeTransport, and the extensibility claim has one healer behind it.'
flywheel:
  node_id: e6fbea9b-ac04-5b61-9545-315b8f02da43
  slug: lingering-credit-5743
  revision: 1
  pushed_at: '2026-08-14T11:21:56+00:00'
  content_sha256: bc09a7d03086e3072d20b260d9f3ea6b6d61d12f925469ba14566e37156bfd86
---
Status: working

## Current

`hypergraph heal` carries a capability **backwards** into a repo that adopted before
the capability existed. It is a registry of typed graph repairs, not a migration
script, and it is a separate command from `upgrade` because the two cost different
things: `upgrade` refreshes copies and `git checkout` undoes it, while `heal` rewrites
graph content and spends a mirror-write budget that cannot be un-spent
[rec: simple-ocean-1716] [rec: clear-moss-4527].

- **Dry run is the default**, the one inverted default in this tooling, and plain
  detected drift exits **0**. Unhealed drift is a capability that landed after your
  adoption, not a broken invariant — the same reasoning that keeps `check`'s version
  skew a warning. `--fail-on-drift` opts into exit 1 [rec: clear-moss-4527].
- **Nothing is persisted.** No "have I run?" flag: the written data is the state and
  `detect` re-derives it from the files, the property that already makes `push_plan` a
  safe resume primitive. A runtime check asserts every drift a healer *claimed* to heal
  is absent from the next `detect` — a healer that reports more than it did fails
  loudly rather than quietly [rec: clear-moss-4527].
- **A healer's write targets come from `flywheel:` and never from `origin:`**, enforced
  by `heal_write_targets()` as the only sanctioned way to obtain one. In an adopted repo
  every `origin.node_id` is an id on the frozen archive — same shape, same credentials,
  one dict lookup away — so this mechanizes a rule hypergraph-adopt had only ever
  stated in prose [rec: clear-moss-4527].
- Refuses on an uncommitted graph directory, and on the protocol's own checkout. The
  dirty-tree guard is deliberately *not* the same call `push` made: `push` has none
  because reconcile publishes before it commits, and nothing about heal is inside that
  flow [rec: clear-moss-4527].
- Healer #1 is **tags**, in two separable phases — frontmatter and `tags.yml` offline,
  then the mirror vocabulary and assignments. Matching is exact: an imported node's
  `origin.node_id` *is* its archive id, so nothing is ever guessed [rec: clear-moss-4527].

**Proven end to end against a live mirror** [rec: early-mesa-8507]. On neural-whoop:
22 tag definitions created, 486 assignments across 188 of 189 nodes, **per-tag counts
identical to the archive**, `push --verify` 0 drift, a second `heal tags` reporting 0
changes, and the archive root still at revision 28. The offline half needed no
credentials at all — the adoption's own cached pull was the source.

Every guard held under real conditions: `origin:` was never a write target across all
212 pushed nodes; `push --plan` after the frontmatter rewrite showed 0 creates, 0 body
updates and 0 violations; and every `--apply`-less invocation wrote nothing [rec: early-mesa-8507].

**Three host behaviours broke it first, and none was findable by reading**
[rec: early-mesa-8507]: `tags:create` returns the graph *root node* rather than the tag;
a `cluster:*` tag must cover a connected set of nodes, checked on every write, so
assignment *order* is part of the contract; and creating a tag bumps the committed
revision of **every node in the graph**, which left nodes nobody had written reading as
drift. All three are fixed, tested, and modelled in `FakeTransport` — and the healer
framework itself did not change to accommodate any of them. Every fix landed in the
transport or in `push_tags`, which is better evidence for the framework's shape than a
second healer would have been, because it was not designed for.

**The extensibility claim is now evidence, and it came in under budget**
[rec: shady-bay-7654]. The framing was that healer #2 costs one registry entry and one
comparator; the speculative `artifacts` entry in `FIELD_COMPARATORS` even carried a
comment admitting *"a claim with no second instance is not evidence"*. `HEAL_ARTIFACTS`
cost **zero** new comparator entries and **one** registry entry — the existing entry
served, and the only real work was teaching `side_from_local` which frontmatter block to
read the ids out of. That is cheaper than the claim, not merely equal to it. Partial
evidence had already arrived from the live tag run, where three host defects moved
nothing in the registry, the drift types or `detect`/`apply` [rec: early-mesa-8507].

**Healer #2 is `artifacts`, and what it does *not* do is the finding**
[rec: shady-bay-7654]. It inventories what the frozen archive still holds, per node,
under `origin.artifacts` — frontmatter only, offline-capable, no mirror phase at all, so
it never needs `heal_write_targets` and is fully `git checkout`-reversible. It
deliberately does **not** repatriate the archive's bytes: those are not in the repo, so
re-uploading them would leave the mirror holding evidence the repo cannot regenerate.

**The normal case needs no healer at all, and that difference from tags is the point.**
An adoption that predated tags *lost the names* — they were on the archive and nothing
local held them, which is what made a backward path necessary [rec: fresh-spire-9002].
An adoption that predated artifacts lost **nothing**, because there was nothing local to
lose. A repo adding paths to old record nodes today is served by `push` alone, since the
plan fires on the absent stamp. So the registry's second member is narrower than its
first, and the reason is a real asymmetry between the two capabilities rather than an
oversight [rec: shady-bay-7654].

## Negative knowledge

- [scope: repairing graph content in someone else's repo | confidence: high | evidence: clear-moss-4527 | decision: simple-ocean-1716] a command that rewrites graph content cannot borrow the defaults of one that refreshes copies. `upgrade` acts by default because every effect of it is `git checkout`-reversible; a heal rewrites ~188 files outside any commit flow and spends mirror writes that cannot be un-spent, so acting by default would make the safe reading of `hypergraph heal tags` the destructive one. The inverted default is the design, not a precaution.
- [scope: reusing a source graph's own strings when repairing | confidence: high | evidence: clear-moss-4527] a healer and the importer it repairs *after* must produce byte-identical values, or the repair invents a second spelling of the same thing. heal first resolved tag ids through the raw export, so a healed repo got `★ studio-baseline` where an imported one got `studio-baseline` — two names for one tag, which is the duplicate-definition failure by another route. Found by running the healer against the real archive, not by reading it. Route both paths through the same transliteration and assert they agree node for node.

## Provenance

- simple-ocean-1716 — the decision that opened this: heal is a framework, and separate from upgrade because it rewrites graph content
- clear-moss-4527 — built and trialled offline end to end; the mirror half and healer #2 are what remain
- fresh-spire-9002 — the field loss that made a backward path necessary rather than nice
- early-mesa-8507 — the live run: 188 nodes recovered on neural-whoop's mirror, and the three host behaviours that took
- shady-bay-7654 — healer #2 (artifacts), and the extensibility claim settled at zero comparators and one registry entry
