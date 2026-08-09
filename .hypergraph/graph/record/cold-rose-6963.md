---
node_id: b53696c7-25ba-50f3-867b-7b7bd0c2c298
slug: cold-rose-6963
title: 'Viz phase 5: live mode — the page polls a sibling data file and pulses what is new'
created_at: '2026-08-09T10:05:45+00:00'
parents:
- hollow-path-2087
summary: viz --live writes a sibling JSON the page polls; new nodes pulse. Explicitly not self-contained, and it needs http rather than file://.
flywheel:
  node_id: 2ba5c561-1984-5eec-a23a-446c12f02348
  slug: patient-scene-6637
  revision: 0
  pushed_at: '2026-08-09T10:47:13+00:00'
  content_sha256: c51f67a929ebb04e9a834a1de2bcd8b5fe28515148ee70f008aede67d825efda
---
## What

Added `viz --live`: the page is written alongside a sibling `viz.data.json`,
polls it on an interval, and redraws with a pulse ring around whatever appeared
since the last poll. Off unless the flag asks for it.

## Why

Follows `hollow-path-2087`. Three of the four audiences for this page are served
by a static file; the fourth — watching a run land work — is not. A page that has
to be regenerated and reloaded by hand is not a status board.

This is the one output that deliberately breaks the single-file property the rest
of the overhaul was built to preserve, so it is a flag, it is documented as such
in `--help` and the README, and the default path still fetches nothing.

## Method

`viz --live -o viz.html` writes both files and embeds `DATA.live = {url,
interval_ms}`. `js/live.js` runs only when that key exists — without it not a byte
of network code executes, which is what keeps
`test_render_viz_emits_selfcontained_html` meaningful rather than merely passing.

Change detection is a cheap signature (node counts, link count, both
`exported_at` stamps, the high-water mark), not a deep compare. On a change the
payload is adopted and **every** derived cache is dropped — `bySlug`, the
hyperedge index, the spine ranks, the blob field cache, and all cached layouts.
That list is the whole risk in this feature: a cache that survives a data swap is
a drawing that looks live and is not.

The pulse is a ring with a SMIL `<animate>` rather than a CSS keyframe, so it
behaves the same in the exported SVG and leaves nothing behind.

`--live` requires `-o`, because a sibling file needs something to be a sibling of.

## Result

Verified end to end in `tests/browser/test_live.py` over a real local http server:
the page loads, the indicator appears, a node appended to the served JSON shows up
in the timeline within one poll, the header reads "+1 new", and the new node
carries exactly one pulse ring. No page errors.

**The constraint worth writing down: live mode cannot work from `file://`.**
Browsers block cross-file `fetch`, so a live page must be served over http. Rather
than fail silently, the indicator turns amber and reads "live off — serve over
http" after three consecutive failures, polling stops, and the CLI prints the
`python3 -m http.server` line it needs when it writes the files.

Tests: 143 pass (was 140; +3 — the live round trip over http, the default output
still carrying no live key and no `http://`, and `--live` without `-o` exiting 2).
Checker: 0 violations.

Not done: there is no way to refresh *only* the data file — `viz --live` rewrites
both. That is cheap enough here (a 280 KB JSON) and a `--format json` output would
be a second thing to keep in sync for no gain yet, so it waits until something
actually needs it.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: hg-viz
- commit: 27c14b3a44a3ddf26a493b1f16975b7d0b9c1e3f

## State Impact

- target: polished-pond-2718 — `viz --live` adds a live status mode: the page is written alongside a sibling `viz.data.json`, polls it on an interval (`--live-interval`, default 5s), and redraws with a SMIL pulse ring around every node that appeared since the last poll. It is the one output that deliberately breaks the single-file property, so it is a flag, it is documented in --help and the README, and `js/live.js` executes no network code at all unless `viz --live` set DATA.live — which is what keeps the self-contained test meaningful rather than merely passing. Change detection is a cheap signature (node/link counts, both exported_at stamps, the high-water mark); on a change every derived cache is dropped — bySlug, the hyperedge index, spine ranks, the blob field cache and all cached layouts — because a cache that survives a data swap is a drawing that looks live and is not. Verified end to end over a real local http server: a node appended to the served JSON appears within one poll, the header reads "+1 new", and the node carries exactly one pulse ring, with no page errors. Load-bearing constraint recorded: live mode cannot work from file:// because browsers block cross-file fetch, so the directory must be served over http; the page turns its indicator amber and stops polling after three failures rather than failing silently, and the CLI prints the `python3 -m http.server` line when it writes the files. `--live` requires -o. Deferred: no way to refresh only the data file — `viz --live` rewrites both, which is cheap at 280KB and avoids a second output format to keep in sync. Tests 140 -> 143, checker 0 violations.
