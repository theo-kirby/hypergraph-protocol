---
node_id: 3721ae89-a62b-5243-bfad-00ea1cbf28b0
slug: windy-eagle-6074
title: 'Lanes land spec-first: the provider seam and SPEC''s Dispatch section'
created_at: '2026-08-16T17:57:16+00:00'
parents:
- blue-rain-3979
summary: ''
---
## What

The lane-provider seam, spec-first: `backend/lanes.md` (new, INTERFACE.md house
style) defines the five abstract operations a lane provider must satisfy —
`provision(spec)→lane`, `inject`, `run`, `harvest`, `teardown` — and SPEC.md
gains `### Dispatch and lanes` under Collaboration (with a one-line
cross-reference from Forward work). One provider is named as shipping: local
(git worktree + `lane/<slug>` branch). Box is documented as the future provider,
deliberately with no code.

## Why

Dispatch is the loop `hollow-rain-8997` says is missing, and the box/fleet layer
is the part most likely to change — so the boundary goes in as a documented seam
rather than baked-in mechanics, exactly the mirror's pattern (a tool property
the protocol never reads). Spec lands before code so the CLI (next unit) is an
implementation of a stated contract, not the other way round.

## Method

The contract notes bake in the sibling lab repo's hard-won lane rules: the
provider mints lane identity, never the agent (the `fair-field-3265` fleet
lesson — self-named lanes collide silently); scripts and credentials travel on
stdin, never argv (argv is world-readable process state); exit status attests
the harness ran, never that the work succeeded; harvest strictly precedes
teardown, with teardown *refusing* while unharvested; redaction happens in
memory before the first write. Local harvest is shown to be a git merge — the
record graph's own merge story doing the work — which is why the local provider
is nearly free. SPEC addition stays at protocol altitude: dispatch enters
through the record graph as a decision node, the node is an advisory lane claim
(never a lock — worst case is duplicated work, absorbed by the merge story),
and contributors-record/maintainer-reconciles covers dispatched agents because
they are contributors by definition.

## Result

`backend/lanes.md` committed (five-op table + contract notes + local-provider
mapping + the box paragraph); SPEC.md carries the new subsection and
cross-reference. No invariant text changed; no code. Suite unchanged at 293
passed, 2 skipped.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 4acbd88ae17f65fc0fc654bfff0561f1b668baba

## State Impact

- target: gilded-vale-8087 — Collaboration gains Dispatch and lanes: dispatch enters through the record graph, the Dispatch: decision node is an advisory lane claim, dispatched agents are contributors by definition; lanes are a tool property behind backend/lanes.md (provision/inject/run/harvest/teardown; local provider named, box documented not built)
- target: hollow-rain-8997 — the missing loop now has a stated seam: dispatch is specified at protocol level before any code; the claim-avoidance and closure conventions are defined
