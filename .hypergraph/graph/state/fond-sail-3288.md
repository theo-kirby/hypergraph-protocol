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
  revision: 1
  pushed_at: '2026-08-09T16:30:11+00:00'
  content_sha256: a4ed4bd58449afebf5e7b712d5b93a1bde8848c411fd109f1d3a0d7abff9b267
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
prose intact and a `CLAUDE.md → AGENTS.md` symlink written through rather than broken;
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

## Negative knowledge

None yet.

## Provenance

- ancient-bluff-9706 — hypergraph upgrade and the version stamp, with both compatibility directions measured
- humble-rain-0304 — 0.0.7 published; the two-command update verified end-to-end from PyPI
- long-peak-1620 — the CI-template/CLI skew that showed copied artifacts drift out of step with the CLI
