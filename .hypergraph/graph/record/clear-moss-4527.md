---
node_id: e0627dc9-0d88-52ae-935d-78aa04cf6c1a
slug: clear-moss-4527
title: Tags travel, and heal carries them backwards
created_at: '2026-08-09T23:17:51+00:00'
parents:
- simple-ocean-1716
summary: 'Built the plan: tags: names in frontmatter + .hypergraph/tags.yml, import and push carrying them, a Drift/GraphSide/diff_graphs comparison layer that verify_mirror is refactored onto byte-identically, and `hypergraph heal` — a registry of typed graph repairs, detect-only until --apply. Trialled on a copy of the real neural-whoop repo: 188 nodes healed, push_plan stays free of creates and body updates, second run changes nothing. Two defects caught by running it: heal wrote untransliterated tag names, and push --plan counted tag ops as body updates.'
flywheel:
  node_id: 59e2de70-35eb-585a-88bf-bfe40af28a7b
  slug: tight-mountain-7190
  revision: 0
  pushed_at: '2026-08-11T12:29:46+00:00'
  content_sha256: 6b7b21edbc8e6ab67fb3182e2f8f68e281813d7e95c4d9b04cd2139f5d283e38
---
## What

Built what [rec: simple-ocean-1716] decided. Tags travel forward through `import` and
`push`; `hypergraph heal` carries them backwards into a repo that adopted before the
capability existed; and a graph comparison layer sits underneath both, with
`verify_mirror` refactored onto it.

Six commits, `754baf4..066330b`. 355 unit tests + 24 browser tests, all green.

## Why

Adoption's claim is that a project with a past keeps the past. neural-whoop's adoption
dropped 22 tags across 188 of 189 nodes [rec: fresh-spire-9002], and the backend had
implemented the operation all along. Fixing only the forward path would have left the
one repo the defect was measured on permanently missing its taxonomy.

## Method

**Phase 1 — the local model.** `tags:` is a list of names in node frontmatter,
between `summary` and `origin`, **omitted when empty** so no adopting repo gets its
whole graph rewritten for nothing. The vocabulary is a new committed
`.hypergraph/tags.yml` keyed by graph kind. `synth_tag` derives a colour pair from
`sha256(name)`, which is what keeps the file optional. New `hypergraph tags
{list,add,rm}`, because the record skill now teaches tagging and an agent hand-editing
a generated YAML file is how you get a duplicate name.

**Phase 2 — import.** Tag ids resolve through the **union** of `graph_tags` across all
nodes, with the parentless node's copy winning. `local_tag_name` transliterates
deterministically (`★ studio-baseline` → `studio-baseline`), reports every rename on
stderr, and keeps the original as `archive_name:`. `--fork` stamps `origin:` on each
tag definition so the first push creates the vocabulary fresh; a re-home stamps
`flywheel:` so it is a no-op. Pointer-tag chains go to `cache/import-report.json` plus
a loud stderr block.

**Phase 3 — the comparison layer.** `Drift`, `GraphSide`, `side_from_local`,
`side_from_export`, `diff_graphs`, `FIELD_COMPARATORS`. Three rules the old loops never
stated: a match key is **declared, never inferred** (a content hash is not a key — two
record nodes can share a body); ambiguity is **reported, never resolved**, with both
sides excluded; and a `Drift` carries **both** values so callers reconstruct the
wording they already had rather than inherit a new one.

`verify_mirror` now formats from `Drift`. Its two traps were both real: the
"pending update" check is *intra-file* (`flywheel.content_sha256` against the file's
own body, no second graph involved), so it lives in a separate `pending_push_drift`;
and its per-node interleaving is part of the output, so `GraphSide` keeps `records` in
file order rather than only the keyed dict.

**Phase 4–5 — transport and push.** `graph_tags` / `create_tag` / `assign_tags` on both
transports. `tags_sha256` is a **sibling** of `content_sha256` in the `flywheel:` block.
`push_plan` gains a second pass appended after the node ops, so an assignment always
sorts after the create that mints its node id. `push_tags` resolves the vocabulary by
name against the live root, never computes the next root revision, and writes
`tags.yml` after every create.

**Phase 6 — heal.** `Healer` records name/summary/since/reads/writes/after, a
`blocked_by` returning a *reason*, and `detect`/`apply`. `HEALERS` is the registry;
healer #2 costs one entry there and one comparator. Nothing is persisted — `detect`
re-derives, and a runtime check asserts every drift a healer *claimed* to heal is gone
from the next `detect`.

**Phases 7–8 — docs, skills, viz.** SPEC, INTERFACE op 10, local-adapter §10,
mirror.md (`## Tags`, `## Retroactive repair`), flywheel.md payloads, the record skill's
tagging step, the adopt skill's corrections. Viz emits `tags` + `tag_defs` and gets a
chip row that filters.

## Result

**The forward path, measured against the real 189-node archive.** `import --fork`
carries 22 tags onto 188 nodes, writes `tags.yml`, reconstructs the 6-hop
`studio-baseline` chain into `import-report.json`, and reports both `★` renames.

**The backward path, on a copy of the real neural-whoop repo.**

| step | result |
| --- | --- |
| `heal` | lists `tags [applies]` |
| `heal tags --offline` | 188 nodes + tags.yml would change; **writes nothing** |
| `heal tags --apply --offline` | 188 healed, 22 definitions |
| `push --plan` after | **0 creates, 0 body updates, 0 violations** — 188 tag ops |
| `heal tags --apply --offline` again | 0 changes, tree git-clean |

**The append-only proof holds.** `LocalNode.sha256` hashes the body alone, so a
frontmatter-only write produces no `update` op and cannot trip the append-only
violation. Verified in the field and asserted in
`test_heal_tags_changes_no_body_sha256_and_leaves_push_plan_empty`.

**Two defects the trial caught, both from running it rather than reading it:**

1. **Heal wrote raw archive names where import writes transliterated ones.** `heal`
   resolved tag ids through `side_from_export`, which returns the source's own names,
   so a healed repo got `★ studio-baseline` and an imported one got `studio-baseline`.
   Two spellings of one tag is the duplicate-definition failure by another route.
   Fixed by routing the healer's names through the same `import_tag_vocabulary`, with
   `test_heal_names_match_what_import_would_have_written` comparing a healed repo
   against a freshly imported one node for node.
2. **`push --plan` counted tag assignments as body updates**, by subtracting creates
   from the total. It reported "0 creates, 188 updates" on a graph where nothing's body
   had changed — exactly the reading that would make someone think a heal had violated
   append-only. Counted by op now (`plan_op_counts`).

**The refactor changed nothing.** The pre-refactor `verify_mirror` loop is kept verbatim
in the tests as the oracle and run against a graph carrying every drift kind
*interleaved* across nodes; the two agree finding-for-finding, string-for-string.

## Assessment

The extensibility claim is not yet evidence. `FIELD_COMPARATORS` has an `artifacts`
entry with no healer behind it, and `HEALERS` has one member. The claim that healer #2
costs one entry each is checked only by
`test_registry_names_unique_ordering_acyclic_archive_readers_never_write`, which
constrains the shape and cannot prove the cost. That is the thing to watch when
artifacts are attempted.

What is not built: the mirror phase has been exercised only against `FakeTransport`,
which models the two properties that matter (a create bumps the root revision, an
assignment bumps the node revision and is an atomic replace) but is not the host. The
field run against neural-whoop's live mirror is the remaining evidence.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 066330b88d5bca64cc3faa91caf4d0fb4e4ce22b

## State Impact

- target: empty-forest-6305 — The mirror gains a tag surface and a comparison layer: Drift/GraphSide/diff_graphs sit above push_plan and verify_mirror, which now formats from Drift with byte-identical findings (the old loop is kept in the tests as the oracle). push --verify --strict opts into title/parents/tags.
- target: blue-sun-8921 — Op 10 is implemented: names in frontmatter plus a committed tags.yml keyed by graph kind, with a colour synthesized from the name's digest so the file stays optional. INTERFACE and local-adapter §10 rewritten from "not implemented".
- target: morning-crane-7863 — import --fork now carries tag names and the vocabulary; pointer-tag chains are routed to cache/import-report.json and the epoch marker. Verified against the real 189-node archive: 22 tags, 188 nodes, both ★ renames reported.
- target: fond-sail-3288 — upgrade and heal are now two commands with two contracts: reversible copies vs graph content. upgrade prints the heals that apply, computed offline from blocked_by and never keyed off hypergraph_version.
- target: NEW retroactive-repair — Built and trialled offline end to end on a copy of neural-whoop, but the mirror phase has only met FakeTransport. Opens as [open] and stays there until the live field run.
- target: wandering-sun-8831 — check gains exactly one tag rule: where tags.yml exists, an undeclared name is a warning. Never a violation — no invariant reads a tag.
- target: dry-wildflower-2260 — The record skill teaches tagging (declared names only, never a hand-edit, nothing at all without a tags.yml); the adopt skill's claim that tag taxonomies do not travel was wrong and is fixed, and its step 6 now routes pointer-tag history into the epoch marker.
- target: polished-pond-2718 — The page gains a tag chip row that filters and changes no geometry or colour, asserted by rendering the same graph with and without tags and comparing every shape.
