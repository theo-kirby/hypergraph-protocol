---
node_id: 389b653a-38c5-543d-9bee-914f78317d71
slug: humble-mist-8524
title: 'U1: checker parsing trust — fences, duplicate headings, tight slug extraction'
created_at: '2026-08-18T11:44:27+00:00'
parents:
- lively-spring-9646
summary: ''
flywheel:
  node_id: 81d8d133-363b-5dae-8564-8ceec0c3f036
  slug: spring-mountain-7382
  revision: 0
  pushed_at: '2026-08-18T11:44:34+00:00'
  content_sha256: a1dde36aae1d82325b6f49c0b359a159eaf945062f44c785c6df5883d47f555d
  parents_sha256: a46bdfecfcc74043e4639169f11bfc949f3fd2d004d538cf34ae14e0ee509800
  parents:
  - 9083f871-21b1-500f-b44a-980d99519eba
---
## What

U1 of the 0.1.0 gate: the four checker parsing-trust defects the readiness audit reproduced live are fixed, and the repo's own graph is now a permanent regression net for every future checker change.

## Why

The audit (parent node) showed the checker could be lied to by legal markdown: a `## State Impact` heading inside a code fence counted as the section; a duplicated section heading silently merged bodies; `SLUG_RE.findall` over whole lines read URL tails ending in `-1234` as citations (both in provenance bullets and inside `evidence:` fields — the audit's claim that `check_negative_knowledge` scanned whole lines was wrong, it already scoped to the field, but `findall` inside the field still matched URL substrings); and an HTML comment above a `Status:` line failed I6. A checker that misparses is worse than none — it teaches agents to reformat correct prose.

## Method

- One fence tracker, `fence_mask(lines)`, extracted from `claim_units` and now shared by `split_sections`, the new `duplicate_headings`, and `claim_units` itself — a heading in a fence can never be structure to one parser and content to another.
- `split_sections` is first-wins on repeated headings (was: silent `setdefault` merge); `duplicate_headings(content)` reports repeats; duplicated **load-bearing** headings are violations (`state impact` → I2 on record nodes; `current` → I1, `provenance` → I4, `negative knowledge` → I7, `reconciliation` → I5 on state nodes).
- `check_provenance`: the slug is the bullet's leading token (`^-\s*(\S+)` fullmatching `SLUG_RE`), `[rec: …]` accepted anywhere as fallback, neither → the existing violation. `check_negative_knowledge`: `evidence:` split on commas, tokens kept only on `SLUG_RE.fullmatch`.
- `status_of(content)` strips `COMMENT_RE` before reading the first non-blank line; used by both `check_status_line` and `node_status`.
- `test_live_dogfood_graph_stays_green` exports this repo's committed `.hypergraph/graph/` through `export_graph_json` and asserts `run_check` with the real config yields zero violations — measured beforehand: the live graph has zero duplicate/fenced headings, all 268 provenance bullets are leading-token form, all `evidence:` fields are comma-separated pure slugs, so the tightened rules flag nothing real.

## Result

11 new tests in `tests/test_checker.py`; suite grows 302 → 313 passed, 2 skipped. `sync` on the live graph: 0 violations, 0 warnings, `push --verify` 0 drift. The four false-trust behaviors are each pinned by a test that fails on the old code.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 9396b3c393614b89fcabd6f96ce381f3305def41

## State Impact

- target: wandering-sun-8831 — checker parsing hardened: fence-aware sections, duplicate load-bearing headings are violations, provenance/evidence slugs are whole-token only, comment-tolerant status; the live graph is a pinned regression net (test_live_dogfood_graph_stays_green)
