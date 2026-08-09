---
node_id: ba110564-bfd7-56fa-88a4-6d05ba89c2ed
slug: fond-sail-3288
title: Upgrade path
created_at: '2026-08-09T15:54:22+00:00'
parents:
- cool-king-8586
summary: ''
flywheel:
  node_id: 742f4d32-ea9c-54fc-a8d3-4b0067dfc1aa
  slug: round-thunder-5855
  revision: 4
  pushed_at: '2026-08-09T19:23:47+00:00'
  content_sha256: b62dc954eee8eb5ad5e6725afeaf83c60b70d62da4be7b5f924389187f481cad
---
Status: working

## Current

How a release reaches a project that already adopted the protocol. Three things
travel and they update by three different mechanisms, which is the whole reason this
needed building [rec: ancient-bluff-9706]:

- **The CLI** lives outside the repo; `uv tool upgrade hypergraph-protocol` handles it [rec: ancient-bluff-9706].
- **The node files** are never touched by an upgrade — measured, not assumed: the published 0.0.5 CLI checks a 0.0.6-written graph at 0 violations, because the format is additive markdown + frontmatter [rec: ancient-bluff-9706].
- **The copies** — the five skills under `.claude/skills/`, the sentinel AGENTS.md block, the CI workflows — are files inside the adopter's repo that `uv tool upgrade` cannot see; `hypergraph upgrade` refreshes them [rec: ancient-bluff-9706].

`upgrade`'s contract is **refresh what is already there, never install what is not**:
it will not drop CI into a repo that never had it, and that same rule is what stops a
repo-scoped command writing outside the repo it was pointed at. Skills are replaced
wholesale so a file removed upstream is pruned (plain `skills install` merges, so it
cannot); the AGENTS.md block is replaced between its sentinels with the adopter's own
prose *outside* them intact — but everything **inside** them is overwritten, which
is the defect below — and a `CLAUDE.md → AGENTS.md` symlink written through rather than broken;
drifted workflows are reported and left alone until `--workflows`, because they are
the one copied artifact adopters genuinely edit [rec: ancient-bluff-9706].

`hypergraph_version:` in the config records which release installed those copies — not
a compatibility floor. `check` compares it to the running CLI and names the remedy for
whichever half is behind; a missing stamp is an info, not a warning, because every repo
adopted before the stamp lacks one [rec: ancient-bluff-9706].

Shipped in **0.0.7** and verified from PyPI with published artifacts only: a repo installed from 0.0.6 — old skills, an old sentinel block, a 0.0.6 stamp — took the two documented commands (`uv tool install`, then `hypergraph upgrade`) and came out with 0.0.7's skills, a refreshed block with its own prose intact, and a re-stamped config [rec: humble-rain-0304]. That is the thing that was impossible before: a fix to a skill reaching a repo that already adopted, without anyone re-running adopt. Two
prior burns say the same gap bites in both directions — a shipped CI template once
called `check --since` before that flag existed [rec: long-peak-1620], and the 0.0.5
high-water-mark change needed a migration nobody could have known to run without
`check` naming it [rec: long-peak-1620].

**Broken, found on the first run against a repo that had used the feature it destroys.**
`upgrade` replaces the *whole* sentinel block with the shipped template, and the adopt
skill's step 8 deliberately writes per-project content into that block. On cadex it
deleted the clause reconciling the record graph with `docs/DECISIONS.md` — required
under "contract reconciliation" — and the epoch-marker note naming the marker slug and
prehistory count. The two skills disagree about who owns the inside of the sentinels:
`adopt` writes there, `upgrade` overwrites it. The same command already models the
right behaviour for `.github/workflows/`, reporting drift and leaving it alone
"because adopters customize these" — the block has exactly that property and the
opposite default. Everything else in the upgrade held: skills refreshed, config
stamped, prose outside the sentinels byte-identical [rec: vast-valley-5745].

**Fixed in the tree, not yet released** [rec: open-eagle-4603]. `upgrade` now replaces
a block only while its content digest matches one this project has shipped
(`SHIPPED_BLOCK_DIGESTS`, both templates recovered from git history as blobs);
anything else is reported as `customized`, left untouched, and the shipped template is
named so the adopter merges by hand. `--agents-block` opts into overwriting, exactly as
`--workflows` does. It needs no migration and no new config field — every repo adopted
before the fix classifies correctly on its first run, because the evidence is the block
itself. The nested-marker design was tried first and rejected: on cadex the ADR-log
clause is woven into the *middle of numbered item 2*, so no pair of markers separates
it. **Shipped in 0.0.8**, so the destructive behaviour is no longer live for an adopter who upgrades, and the status returns to `working` [rec: clever-ledge-6588]. The 0.0.8 template is registered in `SHIPPED_BLOCK_DIGESTS`, so a block still untouched is refreshed automatically and only an edited one is reported and left alone.

A second gap, smaller: on a repo adopted before the stamp, `check` emits only the
"predates the stamp" info, so the case where the **CLI** is the older half cannot be
reported at all. cadex ran a 0.0.6 CLI against 0.0.7 skills and nothing said so
[rec: vast-valley-5745].

## Negative knowledge

- [scope: sentinel markers around generated content | confidence: high | evidence: open-eagle-4603] Sentinels answer "where does our content go", never "who owns what is in here". The moment a workflow tells an agent to write project-specific prose inside them — which adopt's contract reconciliation must, because the amendment belongs in the sentence it qualifies — the region is shared, and a tool that replaces it wholesale destroys data by design. Ownership of shared prose is not recoverable from position in the file; it is recoverable from whether the bytes are still ours, which is a digest.
- [scope: shipping a command that rewrites files in someone else's repo | confidence: high | evidence: vast-valley-5745] `--dry-run` is not a convenience, it is the only thing between a destructive default and silent data loss. `upgrade` shipped on the belief that sentinels made the write safe; the sentinels are exactly where the unsafe content lives. A destructive default is invisible on any fixture that does not use the feature it destroys, so the test that would have caught this is an adopted repo with project-specific prose in its block — not a scratch repo with the template in it.

## Provenance

- ancient-bluff-9706 — hypergraph upgrade and the version stamp, with both compatibility directions measured
- humble-rain-0304 — 0.0.7 published; the two-command update verified end-to-end from PyPI
- long-peak-1620 — the CI-template/CLI skew that showed copied artifacts drift out of step with the CLI
- open-eagle-4603 — the fix: a block is ours to replace only while its digest is one we shipped
- vast-valley-5745 — first run on a real adopted repo: the sentinel block's project-specific half is overwritten, and a pre-stamp repo cannot report a CLI-is-older skew
