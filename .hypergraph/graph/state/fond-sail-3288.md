---
node_id: ba110564-bfd7-56fa-88a4-6d05ba89c2ed
slug: fond-sail-3288
title: Upgrade path
created_at: '2026-08-09T15:54:22+00:00'
parents:
- morning-crane-7863
summary: 'How a release reaches a repo that already adopted: three things travel by three mechanisms, upgrade refreshes only reversible copies, and a customized AGENTS.md block is now detected by digest rather than overwritten.'
flywheel:
  node_id: 742f4d32-ea9c-54fc-a8d3-4b0067dfc1aa
  slug: round-thunder-5855
  revision: 8
  pushed_at: '2026-08-14T13:37:28+00:00'
  content_sha256: bd7870d52b41608d64d2def8bf2ed9b18adbc9cecc76da342948f504f901f317
  parents_sha256: 437819574dd587d939fe237b83326a9f0d60c63e5db173f7d30329bb8d01fc22
  parents:
  - 67d32718-3dcf-5321-978a-212599c531b4
---
Status: working

## Current

How a release reaches a project that already adopted the protocol. Three things travel and they update by three different mechanisms, which is the whole reason this needed building [rec: ancient-bluff-9706]:

- **The CLI** lives outside the repo; `uv tool upgrade hypergraph-protocol` handles it [rec: ancient-bluff-9706].
- **The node files** are never touched by an upgrade — measured, not assumed: the published 0.0.5 CLI checks a 0.0.6-written graph at 0 violations, because the format is additive markdown plus frontmatter [rec: ancient-bluff-9706].
- **The copies** — the five skills, the sentinel AGENTS.md block, the CI workflows — are files inside the adopter's repo that `uv tool upgrade` cannot see; `hypergraph upgrade` refreshes them [rec: ancient-bluff-9706].

`upgrade`'s contract is **refresh what is already there, never install what is not**: it will not drop CI into a repo that never had it, and that same rule is what stops a repo-scoped command writing outside the repo it was pointed at. Skills are replaced wholesale so a file removed upstream is pruned; a `CLAUDE.md → AGENTS.md` symlink is written through rather than broken; drifted workflows are reported and left alone until `--workflows`, because they are the one copied artifact adopters genuinely edit [rec: ancient-bluff-9706].

`hypergraph_version:` in the config records which release installed those copies — **not** a compatibility floor. `check` compares it to the running CLI and names the remedy for whichever half is behind; a missing stamp is an info, not a warning, because every repo adopted before the stamp lacks one [rec: ancient-bluff-9706].

Shipped in 0.0.7 and verified from PyPI with published artifacts only: a repo installed from 0.0.6 took the two documented commands and came out with 0.0.7's skills, a refreshed block with its own prose intact, and a re-stamped config — the thing that was impossible before [rec: humble-rain-0304]. Two prior burns say the gap bites in both directions: a shipped CI template once called `check --since` before that flag existed, and the 0.0.5 high-water-mark change needed a migration nobody could have known to run without `check` naming it [rec: long-peak-1620].

**It shipped broken, and the first run against a repo that had used the feature it destroys is what found that** [rec: vast-valley-5745]. `upgrade` replaced the *whole* sentinel block with the shipped template, while the adopt skill's step 8 deliberately writes per-project content into that block; on cadex it deleted the ADR-log reconciliation clause and the epoch-marker note. The two skills disagreed about who owns the inside of the sentinels. **Fixed and shipped in 0.0.8** [rec: open-eagle-4603] [rec: clever-ledge-6588]: a block is replaced only while its content digest matches one this project has shipped (`SHIPPED_BLOCK_DIGESTS`, both templates recovered from git history as blobs); anything else is reported as `customized`, left untouched, and the shipped template named so the adopter merges by hand. `--agents-block` opts into overwriting, exactly as `--workflows` does. It needs no migration and no new config field, because the evidence is the block itself. A nested-marker design was tried first and rejected: on cadex the clause is woven into the middle of a numbered item, so no pair of markers separates it.

**The path has two halves and the split is the point** [rec: clear-moss-4527]. `upgrade` refreshes *copies* and every effect of it is `git checkout`-reversible; **`hypergraph heal`** repairs *graph content* and spends a mirror-write budget that cannot be un-spent. So they are separate commands with opposite defaults, and `upgrade` closes by listing the heals that apply, computed offline from each healer's `blocked_by`. Heals are deliberately **not keyed off `hypergraph_version:`** — letting `upgrade` bump the stamp while a graph repair was outstanding would make it assert something it never checked.

A smaller gap remains: on a repo adopted before the stamp, `check` emits only the "predates the stamp" info, so the case where the **CLI** is the older half cannot be reported at all — cadex ran a 0.0.6 CLI against 0.0.7 skills and nothing said so [rec: vast-valley-5745].

## Negative knowledge

- [scope: sentinel markers around generated content | confidence: high | evidence: open-eagle-4603] Sentinels answer "where does our content go", never "who owns what is in here". The moment a workflow tells an agent to write project-specific prose inside them — which adopt's contract reconciliation must, because the amendment belongs in the sentence it qualifies — the region is shared, and a tool that replaces it wholesale destroys data by design. Ownership of shared prose is not recoverable from position in the file; it is recoverable from whether the bytes are still ours, which is a digest.
- [scope: shipping a command that rewrites files in someone else's repo | confidence: high | evidence: vast-valley-5745] `--dry-run` is not a convenience, it is the only thing between a destructive default and silent data loss. `upgrade` shipped on the belief that sentinels made the write safe; the sentinels are exactly where the unsafe content lives. A destructive default is invisible on any fixture that does not use the feature it destroys, so the test that would have caught this is an adopted repo with project-specific prose in its block — not a scratch repo with the template in it.

## Provenance

- ancient-bluff-9706 — hypergraph upgrade and the version stamp, with both compatibility directions measured
- humble-rain-0304 — 0.0.7 published; the two-command update verified end to end from PyPI
- long-peak-1620 — the CI-template/CLI skew that showed copied artifacts drift out of step
- vast-valley-5745 — the first run on a real adopted repo: the sentinel block's project-specific half overwritten
- open-eagle-4603 — the fix: a block is ours to replace only while its digest is one we shipped
- clever-ledge-6588 — shipped in 0.0.8, so the destructive behaviour is no longer live
- clear-moss-4527 — the path splits: upgrade for reversible copies, heal for graph content
- late-sage-5549 — re-homed under Adoption, which is what it is a tail of
