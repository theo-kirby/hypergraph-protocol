---
node_id: de6c1e68-b3e7-56d9-bf14-69bff6cd0c05
slug: kind-valley-8040
title: 'First live mirror push: Flywheel mints its own slugs, so the mirror fails check on its own'
created_at: '2026-08-07T18:22:49+00:00'
parents:
- sleepy-branch-3744
summary: '7-op push applied cleanly, but Flywheel-minted slugs make the projection internally inconsistent: 25 dangling-pointer violations against a Flywheel export of a graph that checks 0/0 locally.'
flywheel:
  node_id: a35a0131-7578-586d-81e2-93e5025ecb30
  slug: blue-cell-4752
  revision: 0
  pushed_at: '2026-08-14T13:14:10+00:00'
  content_sha256: 8121491289b55a369870437d4ce3556a28f6ad0f30907ca1a5d828bceca64196
  parents_sha256: bc64b4960798a930a15aec2038450a80aa55aa8728de6d8693ed072f202fead0
  parents:
  - cdc0228f-517a-56db-8805-6a4423910f8b
---
## What

Ran the first real Flywheel mirror push from the local backend and measured what
the deferred slug-translation decision actually costs. It is worse than the
tradeoff paragraph originally claimed, so the adapter doc was corrected.

## Why

`mirror: flywheel` was switched on for this repo during the migration. The push
path had only ever been exercised against fixtures, where every node was created
in one plan and nothing read the result back as a graph.

## Method

`hypergraph push --plan` produced 2 creates + 5 updates with no violations. A
small executor drove the flywheel CLI (`nodes:commit-new` for creates,
`lease:acquire` → `nodes:commit` → `lease:release` for updates), then
`hypergraph push --record-result` folded the returned ids back into frontmatter.
Verification: re-export both roots from Flywheel and run `check` against the
export, comparing with `check` over the local files.

## Result

The push itself worked exactly as designed: 7 ops applied, revisions advanced as
predicted (`base_revision` from frontmatter matched every time — no 409), and a
second `push --plan` came back empty.

Two findings:

1. **Flywheel mints its own slug on create, so the mirror is internally
   inconsistent.** The node authored locally as `old-dawn-8747` exists there as
   `purple-dawn-2034`, while every `## Provenance` line, `[rec: …]` citation and
   the HWM still say `old-dawn-8747`. `check` against a Flywheel export therefore
   reports **25 I4/I5/I7 dangling-pointer violations** on a graph that checks
   clean (0/0) from the node files. Pre-migration nodes are unaffected because
   `import` preserved their slugs — only nodes created after the switch diverge.
   The mirror is a readable projection for sharing and cloud-agent access; it is
   not an independently valid graph, and it must never be the thing you check.

2. **The plan's `parent_flywheel_ids` carries `null` for a parent that is itself
   a create in the same plan.** Harmless — topological ordering means the id is
   known by then — but the executor has to substitute it, and the adapter doc
   did not say so. Now documented.

This is the evidence the deferred slug-translation decision was missing. Keeping
it deferred still looks right (translation would make the mirror non-identical to
source, breaking the byte-identical `content_sha256` change detector and forcing
two-way translation on every update), but the cost is now measured rather than
assumed.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 4d405a0bc0441d20aa7806c6b69fda21307147a3

## State Impact

- target: empty-forest-6305 — negative knowledge: the Flywheel mirror is a readable projection, not an independently checkable graph; measured cost of deferring slug translation
- target: blue-sun-8921 — local-adapter.md corrected: mirror-consistency limits stated precisely, plus the null parent_flywheel_ids substitution rule for chained creates
