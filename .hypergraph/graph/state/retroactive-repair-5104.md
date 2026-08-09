---
node_id: 67e77d92-1968-5854-b393-2649c2b9c00f
slug: retroactive-repair-5104
title: Retroactive repair
created_at: '2026-08-09T23:22:20+00:00'
parents:
- cool-king-8586
summary: '`hypergraph heal`: a registry of typed graph repairs that carry a capability backwards into a repo that adopted before it existed. Detect-only until --apply, persists nothing, and never treats `origin:` as a write target. Healer #1 (tags) is proven offline on a copy of the real neural-whoop repo; the mirror half has only met FakeTransport, and the extensibility claim has one healer behind it.'
---
Status: open

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

**Open, and what would close it.** The offline half is proven end to end on a copy of
the real neural-whoop repo: 188 nodes healed, 22 definitions written, `push --plan`
free of creates and body updates afterwards, and a second run changing nothing on a
git-clean tree [rec: clear-moss-4527]. The **mirror half has only met `FakeTransport`**,
which models the two properties that matter (a creation bumps the root revision; an
assignment bumps the node revision and is an atomic replace) but is not the host. The
live run against neural-whoop's own mirror — 22 creations, 188 assignments, then
`push --verify` reporting 0 drift and a second `heal tags` finding nothing — is the
evidence this claim is waiting on.

**The extensibility claim is not yet evidence either.** The framing is that healer #2
costs one registry entry and one comparator. `HEALERS` has one member, and
`FIELD_COMPARATORS` carries an `artifacts` entry with no healer behind it. The registry
test constrains the shape — unique names, acyclic `after:` ordering, `blocked_by`
returning a reason rather than a bool, an archive reader never declaring an archive
write — but shape is not cost. Artifacts are the natural second healer and the thing
that would settle it [rec: clear-moss-4527].

## Negative knowledge

- [scope: repairing graph content in someone else's repo | confidence: high | evidence: clear-moss-4527 | decision: simple-ocean-1716] a command that rewrites graph content cannot borrow the defaults of one that refreshes copies. `upgrade` acts by default because every effect of it is `git checkout`-reversible; a heal rewrites ~188 files outside any commit flow and spends mirror writes that cannot be un-spent, so acting by default would make the safe reading of `hypergraph heal tags` the destructive one. The inverted default is the design, not a precaution.
- [scope: reusing a source graph's own strings when repairing | confidence: high | evidence: clear-moss-4527] a healer and the importer it repairs *after* must produce byte-identical values, or the repair invents a second spelling of the same thing. heal first resolved tag ids through the raw export, so a healed repo got `★ studio-baseline` where an imported one got `studio-baseline` — two names for one tag, which is the duplicate-definition failure by another route. Found by running the healer against the real archive, not by reading it. Route both paths through the same transliteration and assert they agree node for node.

## Provenance

- simple-ocean-1716 — the decision that opened this: heal is a framework, and separate from upgrade because it rewrites graph content
- clear-moss-4527 — built and trialled offline end to end; the mirror half and healer #2 are what remain
- fresh-spire-9002 — the field loss that made a backward path necessary rather than nice
