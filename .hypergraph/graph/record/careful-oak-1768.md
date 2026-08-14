---
node_id: c8d7c58d-5d62-5da3-a2c0-74a703c7a930
slug: careful-oak-1768
title: 'The state graph gets depth: 16 flat nodes to 25 at depth 2, and a size budget that could not be met'
created_at: '2026-08-14T13:40:41+00:00'
parents:
- autumn-glade-5802
summary: ''
flywheel:
  node_id: b1c3d7b6-6013-530f-915d-b3da57452f6e
  slug: lingering-unit-7823
  revision: 0
  pushed_at: '2026-08-14T13:40:53+00:00'
  content_sha256: 61c3b2c64c60916840e345d8a3100cd0aaac4811ece361c0a1aa15ece2b78a77
  parents_sha256: afcf7844203bb006d321d4c997e5f959679a9fec9fbdf6a1af1776c830ac931b
  parents:
  - 07bbab92-ad3f-510d-b621-70f401956689
---
## What

Reorganized and compacted this repo's state graph into the shape `[rec: late-sage-5549]` specified: 16 flat nodes became **25 nodes at depth 2**, with `Autonomous operation` and `State graph` born `open` because they are genuine gaps. Every declared impact was folded. The size budget was **missed**, and the arithmetic of why is the most useful thing this round produced.

## Why

`[rec: late-sage-5549]` states the direction. The short version: the Operator's model of the project and its state graph did not match, and the graph was missing the two things the project's own tagline claims. Doing the reorganization on this repo first — before any SPEC convention or `check` rule — is what earns the claim that the protocol teaches agents to build good state graphs, rather than asserting it.

## Method

One reconcile pass on `main`, single writer (SPEC I3), every write through `hypergraph update --expect --reconcile` or `hypergraph new state --reconcile`.

- **9 nodes created**: Record graph, State graph, Distribution, PyPI releases, GitHub repository, Self-host, Viz machinery, Views, Autonomous operation.
- **6 nodes re-parented**, one of which (`retroactive-repair-5104`) was Phase 1's live canary and the other five in this pass: `blue-sun-8921` → Protocol mechanics, `bitter-sound-9744` → Dogfooding, `weathered-union-7494` → Distribution, `fair-field-3265` → Autonomous operation, `fond-sail-3288` → Adoption.
- **5 retitled**: Protocol spec → Graph structure, Checker tooling → Protocol mechanics, Storage interface → Storage & node format, Storage and the optional mirror → Flywheel mirror, Publication → Announcement, Field dogfooding → Field.
- **Every node touched was compacted**: merged redundant claims, dropped superseded narrative (the record graph keeps it — SPEC.md:209), tightened prose. Negative knowledge was preserved verbatim and deduplicated *across* nodes where the same entry had been copied into two (the pi run-log entry, the vendor-stderr injection entry, the conflict-marker entry). Provenance was redistributed, never dropped.

## Result

**The topology landed and is verified against the live mirror.** `pytest` 337 passed / 2 skipped. `check` 0 violations / 0 warnings / 0 unreconciled. `push --verify` and `push --verify --strict` both **0 drift findings**, with `parents` in the default field set — which is the end-to-end proof that Phase 1's work holds against a real host and not only against `FakeTransport`. The five re-parents executed as `+1/-1` edge moves apiece; STATE.md regenerated as a nested tree with no renderer change, and the viz payload carries 25 state nodes at max depth 2 with 13 of them at depth 2.

**The frontier is honest and has doubled**: `Announcement`, `Autonomous operation`, `Protocol benchmark`, `State graph` — four real gaps, up from two. The two that were wrong before: `Publication` was `open` while five releases were live and index-verified, so a working capability was flying an open flag; and the tagline claim had no state node at all, so a known ambition had an empty frontier.

### The size budget was missed, and the arithmetic is the finding

| | before | after |
|---|---|---|
| node bodies | 164,387 B (160 KB) | 131,939 B (129 KB) |
| nodes | 16 | 25 |
| `## Current` | 112,853 B | 78,895 B (**−30%**) |
| `## Negative knowledge` | 32,213 B | 31,730 B |
| `## Provenance` | 17,680 B | 19,100 B |
| nodes over 6 KB | 10 | 10 |

Target was ≤ 60 KB total and no node over 6 KB. **Neither was met, and the second one cannot be met under the constraints the round set itself.** Negative knowledge preserved verbatim plus provenance never dropped is a **50.8 KB floor** — 39% of the target — before a single claim is written. Meeting 60 KB would mean 10 KB of claims across 25 nodes, roughly 400 bytes each, which is not a distilled projection but an index. And provenance *grew*, necessarily: splitting one node into three means three `## Provenance` sections citing overlapping record slugs, so depth trades against bulk rather than reducing it.

The per-node cap fails the same way for the same reason. `fair-field-3265` is 10.3 KB of which **6.9 KB is negative knowledge alone** — it exceeds the whole 6 KB cap before its first claim. Negative knowledge is the least recoverable content in the graph and was ordered preserved verbatim; the two rules are simply in contradiction at this graph's size.

**So the honest measurement for the deferred round is: the binding constraint on a state graph's size is not verbosity, it is accumulated negative knowledge and provenance, and neither is compressible by editing.** A size rule that ignores that will fire on graphs doing exactly what the protocol asks. Three shapes worth considering next round, none of them tried here: budget `## Current` alone rather than the whole body; let negative knowledge live on the node whose scope it names and be *linked* rather than copied, which is the dedupe done by hand here; or make the unit of "readable in one sitting" the frontier plus the architecture tree — which STATE.md already is at 6 KB — rather than the sum of every body.

### What the tooling could not do

- **`update --parent` moves a node but nothing moves a node's *content*.** Splitting `bold-field-1268` into Dogfooding + Self-host, or extracting the storage half of `empty-forest-6305` into `blue-sun-8921`, was manual copy-paste through body files. A `check` rule for provenance redistribution would have helped here and does not exist: nothing verified that every record slug cited before this pass is still cited after it.
- **`NEW <kebab-name>` impact targets never resolve to the nodes they create** — a known trap `[rec: clever-ledge-6588]` recorded from neural-whoop, hit again here at nine nodes. The declared names in `[rec: late-sage-5549]` and the minted slugs share nothing.
- **Nothing detects a state node whose frontmatter `summary:` contradicts its rewritten body** — the blind spot `[rec: green-field-8645]` recorded is exactly what a 25-node pass is most exposed to; every summary here was rewritten by hand.
- **The Frontier view's architecture-tree toggle was not clicked in a browser.** The extension was not connected. What was verified instead: the page's `DATA` payload carries all 25 state nodes with correct parent sets and a maximum depth of 2, the toggle's code is present, and the page fetches nothing external. That is evidence the data reaches the view, not evidence the view draws it.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 7a2af78d924a7b0114a4a3a954107e984515ae1e

## State Impact

- target: soft-hill-6082 — the measurement this round produced: the binding constraint on state-graph size is negative knowledge plus provenance, a 50.8 KB floor neither compressible by editing nor reducible by splitting
- target: cool-king-8586 — 16 flat nodes became 25 at depth 2; the frontier doubled from two gaps to four honest ones
- target: wandering-sun-8831 — three tooling gaps this pass hit: no content-move verb, NEW impact targets that never resolve, and no check on provenance redistribution
- target: empty-forest-6305 — five re-parents executed live as +1/-1 edge moves, with push --verify and --strict both at 0 drift
- target: hollow-rain-8997 — created open: the tagline claim now has a state node holding the gap
