---
node_id: 660f2410-0a25-53f9-93ef-56bfeda81cf3
slug: noble-stream-7701
title: 'Docs say what 0.9.0 is: two files, one upgrade verb, six skills, dispatch'
created_at: '2026-08-16T18:06:30+00:00'
parents:
- simple-vale-9558
summary: ''
---
## What

Docs aligned with what 0.9.0 actually is. The two-file story lands everywhere a
reader forms a model of the tool: pyproject's header comment and description,
the module docstring (core offline, mirror module lazily loaded, the no-network
promise stated as *structural* with the test named), README's tools bullet and
repo map (which gain `tools/hypergraph_mirror.py` and `backend/lanes.md`),
SPEC's Tooling section, AGENTS.md's Map, and backend/mirror.md (which now names
its implementing file, twice — including the Transport note that previously
credited the wrong file with being stdlib-only). The fold story replaces the
two-verb story: SPEC Tooling and README describe `upgrade` as one verb with two
polarities and `--graph` as the boundary, with `heal` named as a deprecated
alias. Dispatch is documented for readers: README gains a `## Dispatch` section
after "Working in parallel" (the claim convention, the lane verbs, the
stand-down posture), the skills enumeration includes `hypergraph-dispatch`,
AGENTS.md's skill map line carries `dispatch`.

## Why

Every one of these lines previously described the pre-0.9.0 tool. Docs that
lag a release train adopters on the old model exactly when they upgrade into
the new one; the release commit sequence puts this pass immediately before the
version bump so nothing ships describing its predecessor.

## Method

Grep-driven: every mention of "single file", the five-skill enumeration, `heal`
as a command, and `tools/hypergraph.py` as "the whole CLI" was found and
rewritten in place. No invariant text in SPEC changed — Tooling and the
Collaboration/Forward-work additions from earlier units are the only SPEC
deltas this release.

## Result

Suite green (302 passed, 2 skipped) — the docstring edits left `--help` intact.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 6106ec016922416e806a0b6a6c5b236a19f78042

## State Impact

none: documentation alignment — every claim updated here restates deltas already declared by the fold, split, and dispatch record nodes
