---
node_id: 27fef7d4-de86-570b-9722-68d715b0eac1
slug: morning-rain-7488
title: 'Viz: force-directed Hypergraph view with hyperedge blobs (recorded retroactively)'
created_at: '2026-08-07T13:05:06.796393+00:00'
parents:
- long-tree-4179
summary: Force-directed hyperedge-blob view added to viz by a blind-test agent; recorded retroactively.
flywheel:
  node_id: 27fef7d4-de86-570b-9722-68d715b0eac1
  slug: morning-rain-7488
  revision: 0
  pushed_at: '2026-08-07T18:12:00.956635+00:00'
  content_sha256: 080f9d82a6ad832145bf304714e89afb2df16c59d5050f460f661eed53f3bc36
---
## What

Added a fourth viz tab — a force-directed Hypergraph view that renders the actual hyperedge structure: each state node's contributing record set (via declared State Impacts) is drawn as a convex-hull blob around the member record nodes. The prior side-by-side combined view was renamed Combination. Recorded retroactively by the reconciling agent on behalf of the authoring agent (see Method).

## Why

Extends the viz subcommand (long-tree-4179): the blob rendering shows many-to-one provenance as a single visual object instead of a fan of lines. Feature requested by the Operator as a blind test of protocol discoverability — the authoring agent was told nothing about Hypergraph.

## Method

Authored by a fresh agent with no protocol context: ~370 lines in tools/hypergraph.py's viz template — hyperedges() derives membership from impact links; deterministic force simulation (pairwise repulsion, spring edges, cluster cohesion) with FNV-1a hash-seeded symmetry breaking and zero Math.random so layouts reproduce across loads; convexHull + padded blobPath rendering; categorical palettes stepped for light and dark themes; per-view pan/zoom state extended to four views. Two tests added asserting tab structure/order and determinism (no Math.random in template); suite 22 green. The agent refreshed .hypergraph/cache/ from live exports as feature input data and regenerated viz.html, but committed nothing to git and recorded nothing — this node, written by the reconciling agent from the working-tree diff, closes that gap (I1).

## Result

Four tabs live: Record, State, Combination, Hypergraph. 22/22 tests green; viz.html regenerates cleanly from this repo's own exports; README updated to match (commit 57c7c0f). Landed in commit 57c7c0f together with the onboarding fix motivated by how this work was produced (see child node).

## Repo

- repo: https://github.com/theo-kirby/hypergraph
- branch: main
- commit: 57c7c0f9b1bbca9f3f0a80f089c6c1894b0aec58

## State Impact

- target: polished-pond-2718 — new claim: fourth force-directed Hypergraph tab with deterministic hyperedge blobs; combined view renamed Combination
- target: wandering-sun-8831 — new claim: suite now 22 tests (2 new viz template/determinism cases)