---
node_id: a76b334c-142c-50fe-9134-71e5121188e0
slug: simple-ocean-1716
title: 'Decision: tags travel, and a heal framework carries them backwards'
created_at: '2026-08-09T22:32:48+00:00'
parents:
- fresh-spire-9002
summary: 'Forward: import and push carry tag names into the repo and onto the mirror. Backward: `hypergraph heal` is a registry of typed graph-diff repairs, healer #1 being tags. Underneath both, a graph comparison layer (Drift/GraphSide/diff_graphs) that verify_mirror is refactored onto byte-identically. Dry run is heal''s default because it rewrites graph content and spends an irreversible mirror budget; upgrade only refreshes reversible copies. Nothing built yet.'
flywheel:
  node_id: b97b67d8-2608-50fd-a339-aef0e78f667d
  slug: tight-salad-4142
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 38c409a8f2cd7b0a95a0d5b588fa00165cc4bf5327784bf65373ad1306db5159
  parents_sha256: 1b7b6933d97800feb9bb2c5a5e9b66a6795aa6d6814aa77f8ff58b4275ec413e
  parents:
  - 12ee0f00-9391-5025-bcf5-be9e2cf263f5
---
## What

The direction settled after the tag-loss audit [rec: fresh-spire-9002], recorded
before any code exists (SPEC: Forward work). Two deliverables and one piece of
machinery underneath them.

**Forward.** A new adoption carries tags: `import` reads the source vocabulary,
writes `tags:` into node frontmatter and a committed `.hypergraph/tags.yml`, and
`push` creates the vocabulary on the mirror and assigns it per node.

**Backward.** `hypergraph heal tags` carries tags into a repo that adopted *before*
the capability existed. `heal` is a **framework**, not a one-off: healer number two
(artifacts) must cost one registry entry and one comparator, or the framing is a lie.

**Underneath both**, and the load-bearing piece: a **graph comparison layer**. Every
healer is a typed diff of a source graph against the local graph on one field, so
`Drift`, `GraphSide` and `diff_graphs` land above the mirror section and
`push_plan`, `verify_mirror` and `heal` all sit downstream of them. `verify_mirror`
gets refactored to format from `Drift` **byte-identically** — the refactor is only
honest if its findings do not move.

## Why

Adoption is the protocol's claim that a project with a past keeps the past. Every
category that silently does not travel is a counter-example, and this one had no
excuse: the backend implemented the operation, the protocol just had no word for it.

The backward half matters more than the forward half. Anyone who adopts is adopting
a release, and a capability that lands after them is worthless if reaching it means
re-running the adoption. `upgrade` already answers "are your *copies* current". It
cannot answer "is your *graph content* current", because refreshing a copy is
`git checkout`-reversible and rewriting graph content is not. Two commands, on
purpose.

## Method

The decisions below are settled. They are recorded here so a later reader sees the
reasoning, not just the diff.

### Where a tag lives

| question | decision | reason |
| --- | --- | --- |
| per-node assignment | `tags:` list of **names** in frontmatter | names, not ids — the same reason `parents:` holds slugs. Ids are a backend's business. |
| vocabulary home | new committed `.hypergraph/tags.yml` | **not** config.yml: push must *update* entries in place to stamp mirror tag ids, and config.yml is only ever appended to textually so its hand-written comments survive. |
| `FM_ORDER` position | between `summary` and `origin` | tags are annotation, not provenance bookkeeping. |
| empty list | **omitted**, never written as `tags: []` | otherwise the upgrade rewrites every node file in every adopting repo for nothing. |
| keyed by | graph kind (`record:` / `state:`) | `tags:create` is per graph root and this protocol has two roots. |

### Pointer-tag history is not modelled

`★ studio-baseline`'s 6 hops do not become frontmatter. The names travel; the chain
goes to `cache/import-report.json` and then into the **epoch marker body as prose**.

A pointer move with a reason *is* a decision record — that is a record node, which
this protocol already has. Frontmatter history would be a third home for a claim no
invariant reads (SPEC I1). Routing it into the epoch marker is what makes this a
routing decision rather than data loss, which is why the adopt skill step that writes
it is load-bearing and not a nicety.

### What `check` does about tags

Tag-blind, with one exception: **if `.hypergraph/tags.yml` exists**, an undeclared tag
name is a **warning**. Never a violation. A tag is annotation; no invariant reads one,
so failing a build over one would be inventing an obligation the spec does not carry.

### `heal` is not `upgrade`

`upgrade` refreshes *copies* of shipped files and every effect is
`git checkout`-reversible. `heal` rewrites *graph content* and spends an irreversible
mirror-write budget. So:

- **Dry run is the default for `heal`, and opt-in everywhere else.** Heal is
  human-initiated, sits in no commit flow, rewrites ~188 files at once, and cannot be
  un-spent on the mirror.
- Plain detected drift exits **0**, not 1. Unhealed drift is a capability that landed
  after your adoption, not a broken invariant — the same reasoning as
  `check_version_skew`.
- **Persist nothing.** The written data *is* the state and `detect` re-derives it,
  the same property `push_plan` has. No healer may store "have I run?".
- `upgrade` gains a pointer to `heal`, computed from each healer's `blocked_by`,
  **offline only**.
- Heals are **not** keyed off `hypergraph_version:` — SPEC defines it as "not a
  compatibility floor", and letting `upgrade` stamp it would falsely assert heals ran.

### The safety rule that mechanizes an existing guardrail

`heal_write_targets()` asserts every write target came from a `flywheel.*` block,
**never `origin.*`**. In neural-whoop every `origin.node_id` *is* an archive id, so a
healer reaching for it would write the frozen archive with the mirror's credentials
and nothing would stop it. The adopt skill has said "never write, tag, or re-parent
archive nodes" in prose since it shipped; this makes it a call site.

### Two traps written down in advance

1. **The revision fold is not optional.** `tags:assign` bumps the node revision, and
   `verify_mirror` treats revision skew as a violation. A tag push that does not
   re-stamp `flywheel.revision` leaves 188 permanent false drift findings — the most
   likely thing to be skipped and the most expensive to discover.
2. **Retry doctrine inverts for assignments.** An atomic replace cannot duplicate, so
   a 409 on `tags:assign` may be re-read and re-issued in-loop. Creates keep the
   no-blind-retry rule. This has to be said out loud in `backend/mirror.md`, because a
   reader who does not see the reason will file it as a bug.

Also settled: `tags_sha256` is a **sibling** stamp in the `flywheel:` block, never
folded into `content_sha256` — `verify_mirror` and `push_legend` both rest on body
byte-identity, and folding would re-push every existing adopter's whole graph.
Colour and flag drift is **reported, never** `tags:update`; `tags:delete` is not
wired at all, because it un-tags every node that used the tag.

## Result

Nothing is built yet. This node is the intent.

Sequenced: local model → import → **comparison layer** → transport ops → push →
heal framework → skills and docs → viz last, gating nothing.

The acceptance test is in the field, not in CI: in neural-whoop, `heal tags --apply`
lands 22 creates and 188 assignments, `push --verify` then reports **0** drift, and a
second `heal tags` finds nothing.

## Known risk taken deliberately

Teaching the record skill to tag creates a taxonomy with **no invariant enforcing
it**. The `check` warning is the only brake, and it only exists once a repo has a
`tags.yml`. Whether this repo's own vocabulary stays coherent over the next few
months is the evidence for or against, and it is worth watching rather than
pre-solving.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: e2a69818add5f9a8f24576d7af8ff18f46bacc6a

## State Impact

- target: NEW retroactive-repair — A new capability: `hypergraph heal`, a registry of typed graph-diff repairs that carry a capability backwards into a repo that adopted before it existed. Distinct from `upgrade` (reversible copies) because it rewrites graph content and spends mirror writes. Opens as [open].
- target: blue-sun-8921 — Op 10 (tags) moves from future to shipped: names are the portable identity, assignment is an atomic replace, and a claim that exists only as a tag is invisible to every invariant.
- target: empty-forest-6305 — The mirror gains a tag surface (vocabulary + per-node assignment) and a comparison layer: Drift/GraphSide/diff_graphs sit above push_plan and verify_mirror, which is refactored onto them byte-identically.
- target: morning-crane-7863 — Adoption carries tag names forward; pointer-tag history is deliberately routed to the epoch marker as prose rather than modelled.
- target: fond-sail-3288 — The upgrade path splits in two: `upgrade` for reversible copies, `heal` for graph content. upgrade gains an offline pointer at heals that apply.
