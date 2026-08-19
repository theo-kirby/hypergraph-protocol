---
node_id: 248be4ec-7346-5d57-9f0f-b4145dd7b2f5
slug: young-ivy-4144
title: 'Public docs rewritten: README and PyPI surface go structure-first'
created_at: '2026-08-19T16:18:30+00:00'
parents:
- scarlet-dawn-9811
summary: 'Operator-directed rewrite: README 281→132 lines, structure-and-vision-first with an ASCII diagram of the record→views→frontier loop; absolute links for PyPI; pyproject description cut to two sentences.'
flywheel:
  node_id: ec960c65-6920-5ec6-8282-31b753fd4139
  slug: winter-tree-2994
  revision: 0
  pushed_at: '2026-08-19T16:18:59+00:00'
  content_sha256: 03e2342d51885920ce2ab50d82b354d10d121d201ce643a0fb3b65db466ebdb6
  parents_sha256: b1ddbafee92926f0114fc29e7eed24f6533b071f0dffcd02d1c158eb014b9619
  parents:
  - 1b18363c-95ba-5ccf-9b44-6505c0c11dd2
---
## What

Rewrote the public-facing documentation — README.md (the GitHub front page and,
via `readme = "README.md"`, the PyPI project page) and the pyproject `description`
(the PyPI summary line). 281 lines became 132.

## Why

Operator directive: the README had grown verbose and read as slop. The ask was a
simple, elegant, concise front door that leads with the vision — an agent-native
environment for autonomous research and engineering, where structure and
discipline produce better results — explains how the structure works, and leans
into the hypergraph nature, rather than walking every feature.

## Method

Reorganized around three load-bearing sections instead of eleven: **The
structure** (an ASCII diagram of record → reconcile → views → frontier → orient;
record graph as ground truth; views as distilled projections with the state graph
as view #1; the sets-to-sets citation structure as the "why hypergraph" answer),
**The discipline** (the four verbs — orient, record, reconcile, dispatch — with
the parallel-work rule and the `check --since` PR gate in one paragraph), and a
compressed **Honest status**. Install/Quickstart kept minimal and ordered to
satisfy `test_readme_names_the_pypi_install_path`; deep material (mirror,
visualization, dev checkout) reduced to pointers; the repo map dropped — the
"Going deeper" table replaces it. All doc links switched to absolute GitHub URLs
so they resolve on the PyPI page, where relative links were broken. The pyproject
description was cut to two sentences leading with "agent-native substrate".

## Result

README.md is 132 lines (from 281) with the vision and the structure in the first
two screens. Full suite green — five consecutive runs at 386 passed / 2 skipped
(one run showed a non-reproducing failure in
`test_import_preserves_flywheel_identity_and_is_idempotent`, an unrelated test
that passed on every re-run including three isolated ones; the changed files are
prose only). `sync` exit 0; STATE.md untouched by the rewrite. The new PyPI
summary and page ship at the 0.0.13 publication.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 7affd40d7bf355baf1faf4b70c0972825223130d

## State Impact

- target: damp-basin-8974 — the README front door is rewritten structure-first at 132 lines (Operator directive against verbosity); doc links are absolute so the PyPI page resolves them; the package description leads with agent-native substrate
