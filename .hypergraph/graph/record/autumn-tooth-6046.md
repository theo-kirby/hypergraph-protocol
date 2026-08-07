---
node_id: cdbea53e-8865-5138-b033-948b4690daf3
slug: autumn-tooth-6046
title: hypergraph — record
created_at: '2026-08-06T21:40:37.319141+00:00'
parents: []
summary: Append-only record graph root for the hypergraph project.
flywheel:
  node_id: cdbea53e-8865-5138-b033-948b4690daf3
  slug: autumn-tooth-6046
  revision: 0
  pushed_at: '2026-08-07T18:12:00.956635+00:00'
  content_sha256: 64113cbbd14933a748be1dd0407416595246df44f8642ca9e947a95d4d7977fc
---
Record root for the hypergraph project (https://github.com/theo-kirby/hypergraph).

Append-only historical log under the Hypergraph protocol: every unit of work becomes one child record node with `## What / ## Why / ## Method / ## Result / ## Repo / ## State Impact` sections. Record nodes are immutable once committed; corrections are new child nodes. Topology is causal — parents chosen by "this work followed from that result", never root-spam.

Companion state graph root: see the project's .hypergraph/config.yml (cross-graph pointers are markdown slugs, never edges).