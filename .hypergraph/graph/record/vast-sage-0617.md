---
node_id: 60d9ec8a-ba27-51ec-ba53-f8708d9c3999
slug: vast-sage-0617
title: 'Viz phase 3: cross-links get a focus mode, a bundled spine, and a barycentre-ordered state column'
created_at: '2026-08-09T09:56:25+00:00'
parents:
- smooth-wolf-8655
summary: Provenance opens with zero cross-links drawn instead of 177; 'all' bundles them into one ribbon per claim; barycentre ordering cuts crossings 13%.
flywheel:
  node_id: f9cb67ce-574c-5312-8829-161978f5c933
  slug: curly-sun-7938
  revision: 0
  pushed_at: '2026-08-09T10:47:13+00:00'
  content_sha256: 9ee35d4811ab5037fda5187c807b6e7c5b762dc61a068feec4de0b5515b937ea
---
## What

Made the Provenance view usable by not drawing the hairball. Cross-graph links
now have three modes — `focus` (default), `all`, `none` — with `focus` drawing
only the links of the selected or hovered node. In `all` they are bundled into
one ribbon per claim through a staggered vertical spine. The state column is
reordered by the barycentre of the record work each claim rests on.

## Why

Follows `smooth-wolf-8655`. Phase 1's axis-aware fit made the Provenance view
legible at 1.057 zoom, and legible was exactly enough to see that the problem was
never the zoom: 177 cross-graph links over 51 nodes drawn at once is a hairball
at any scale.

The density is genuine and was checked before this phase started — 86 of the 89
provenance links are *declared* in `## Provenance` sections, so filtering them
would hide real structure rather than noise. The fix therefore had to be about
*when* links are drawn, not which ones exist.

## Method

**`show.links`**, a third mode alongside the existing impact/provenance kind
checkboxes: the checkboxes say which kinds may be drawn, the mode says how many.
The control is hidden unless both graphs are on screen, via a general
`segHidden()` that also covers the layout-local controls from Phase 1.

Cross-links moved into their own SVG layer, rebuilt on demand rather than drawn
and dimmed. In `focus` mode the usual answer is "draw nothing", and the cheapest
way to draw nothing is to build nothing. Hovering a node reveals its links
without committing the panel to it; selecting does both.

One thing this broke and had to be fixed deliberately: `neighborhood()` derived
the highlight set from the *drawn* edges, which in focus mode is the empty set
before anything is selected — the selection would then have had no neighbourhood
to highlight. It now reads `DATA.links` directly, which is the source the
drawing is derived from rather than the other way round.

**Bundling.** In `all` mode each link routes through a waist shared by every link
of the same state node, on a vertical spine at mid-x. The waist sits at that
claim's own y, and its x is staggered across a 96px band by the claim's rank in
the column — without the stagger every bundle pinches at one x and the ribbons
are indistinguishable exactly where they are densest. Ribbons carry no
arrowheads: 177 of them is noise, and which column an end sits in already gives
the direction.

**Barycentre reorder.** The state column is ordered by the mean `chrono` of the
record nodes each claim links to — the barycentre sweep `layered_layout` already
runs within one graph, applied across the two. The record column was switched
from `seq` (layered order) to `chrono` at the same time, so "further down" means
"later" and the barycentre is measured against something the reader can see.

## Result

The Provenance view **opens with zero cross-links drawn**, against 234 drawn
edges before (57 parent edges + 177 cross-graph). Selecting
`wandering-rice-9747` draws its 10 and no others. `all` draws all 177 as twelve
ribbons.

The barycentre reorder was measured rather than assumed, by counting inverted
link pairs between the two columns:

| state column order | crossings |
| --- | --- |
| architecture (`seq`) | 4146 |
| **barycentre** | **3599** (−13.2%) |
| barycentre, root not pinned | 3582 |
| median instead of mean | 3673 |

−13% is a real but modest gain, and worth stating plainly: barycentre ordering
cannot do much when the links genuinely are dense. Pinning the state root to the
top costs 17 crossings out of 3599 (0.5%) and buys a fixed anchor where a reader
expects one, which is the better trade. Median ordering was tried and is worse
here, so mean stays.

Tests: 135 pass (was 133; +2 — the focus/all/none acceptance test, and control
visibility). The browser metrics now also record `crosslinks` per view, so a
future change that quietly starts drawing all 177 again fails the baseline.
Checker: 0 violations.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 95cf7d0d739859e6ca5d0d2400bae21d17fb3332

## State Impact

- target: polished-pond-2718 — the Provenance view no longer draws the hairball. Cross-graph links gained a mode — `focus` (default) | `all` | `none` — orthogonal to the existing impact/provenance kind checkboxes: the checkboxes say which kinds may draw, the mode says how many. In focus, only the selected *or hovered* node's links draw, so the view opens with **zero** cross-links against 234 drawn edges before (57 parent + 177 cross-graph); selecting one node draws its 10. Cross-links live in their own layer that is rebuilt on demand rather than drawn-and-dimmed, since the usual answer in focus mode is "draw nothing". In `all` mode every link of one claim routes through a shared waist on a vertical spine at mid-x, staggered across a 96px band by column rank (without the stagger all bundles pinch at one x and are indistinguishable where densest) and without arrowheads. The state column is reordered by the mean `chrono` of the record work each claim cites, and the record column switched from `seq` to `chrono` so the barycentre is measured against something visible. Measured by counting inverted link pairs: 4146 crossings in architecture order -> 3599 in barycentre order, a real but modest -13.2%; median ordering is worse (3673) and pinning the state root to the top costs 17 crossings (0.5%) for a fixed anchor. Barycentre ordering cannot do more than this when the links genuinely are dense — 86 of 89 provenance links are declared, which was checked before the phase began. One defect fixed along the way: `neighborhood()` derived its highlight set from the *drawn* edges, which is empty in focus mode before anything is selected, so a selection would have had no neighbourhood; it now reads DATA.links directly. Browser metrics now track `crosslinks` per view. Tests 133 -> 135, checker 0 violations.
