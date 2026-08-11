---
node_id: 37786c1f-0c4e-579d-83e5-d0229162e321
slug: lean-field-0101
title: The lab moved out; the substrate is now an image, and it caught two defects on its first live run
created_at: '2026-08-11T12:28:07+00:00'
parents:
- sweet-wave-7885
summary: research/ became the private hypergraph-labs repo, which consumes this package from PyPI as a stranger does; its environment is now a digest-pinned image, and a trivial counting mission found two silent tool-dispatcher failures in the substrate before passing.
flywheel:
  node_id: 6236dee4-14b2-53c5-a181-708519d10638
  slug: black-sky-2207
  revision: 0
  pushed_at: '2026-08-11T12:29:46+00:00'
  content_sha256: a9c2391a16042360ccb6ffd3a3c43018f6b6d9f9ea1ca691713fde30b0705918
---
## What

Moved the benchmark lab out of this repo into a private sibling,
**`hypergraph-labs`**, and rebuilt its substrate on `chassis` — turning the
container environment from a provisioning procedure into an image with a digest.
Then proved the new rig on live boxes, where a five-line mission found two
defects in that substrate before it passed.

`research/` is gone from this repo. What is left here is the protocol.

## Why

Follows `sweet-wave-7885` and, behind it, `staid-field-2723` — which reclassified
the nine-run E1 as **not a controlled experiment** on four defect classes. One of
those was a *provisioning-procedure* defect: `flywheel setup --mode mcp --yes`
exited non-zero, so two of three arms ran with a broken memory system and nothing
noticed. The procedure that produced it was ~469 lines of bash piped over ssh,
carrying hard-won lessons like "`npm install -g --prefix` is load-bearing" and
"pi rewrites its process title" — and every one of those lines was an unversioned
experimental variable.

`chassis` (a third sibling repo, which does not run this protocol) makes the
environment an artifact with a digest. That is the reason to adopt it, and it
holds even for single-agent runs where its multi-agent features do nothing: the
image ref becomes a recorded constant in METRICS rev-2 rather than a hope.

Four decisions were settled with the Operator and are not relitigated: chassis is
the substrate, adopted now; chassis changes land on `main` and stay **general,
never arm-aware**; the repos are **siblings, not submodules**, so labs consumes
this package from PyPI exactly as a stranger does; and `hypergraph-infrastructure`
is *not yet* — a directory in labs until it has a second consumer.

This node exists in this repo because the split is a fact about **this** repo:
where the lab went, why, and what it now depends on.

## Method

`gh repo create theo-kirby/hypergraph-labs --private`. Moved the tracked tree
only — 151 files, 7.7 MB; the 2.9 GB of harvested workspaces was already
gitignored and stayed on disk. `research/boxlab/` → `labs/`, `research/lab.py` →
`labs/cli.py`, and `eval/ primers/ runs/ METRICS.md` to the labs root. Two test
files went with the code: `tests/test_boxlab.py` and `tests/test_analogy_eval.py`.

**History did not follow.** Provenance is a prose citation: labs' record root
names this repo's graph, and its first record node cites `southern-ridge-1802` and
`protocol-benchmark-4417` by slug. Cross-repo provenance stays prose deliberately
— whether it should be a mechanism is a research question for the protocol, not a
chore for this plan.

In this repo: deleted `research/`, dropped its `.gitignore` block, and replaced
`tests/test_packaging.py::test_research_tree_exists_and_is_undeclared`. That test
asserted `research/` exists so the allow-list assertions would not go vacuous;
with the tree gone it would fail for the wrong reason. Its replacement,
`test_the_allow_lists_are_not_vacuous`, pins the same property directly: both
hatchling allow-lists are non-empty, and `tests/` and `.hypergraph/` still exist
to be excluded.

Labs then adopted the protocol with `hypergraph-protocol 0.0.8` **from PyPI** —
the fourth adopter, and the first that is a genuine stranger to this repo. Two
roots, six seeded components, `check` at 0 violations.

## Result

Both repos green: this one 280 passed / 1 skipped after `research/` was removed,
labs 106 passed / 1 skipped. Labs is at `check`: 0 violations.

The rig works. Three spikes, three boxes, one trivial counting mission; the third
passed on every criterion — ledger `1,2,3`, verdicts `1,2,3`, both image ids
recorded, three pi transcripts harvested, box stopped, 0 leak findings. The
cold-start property is confirmed from the transcripts rather than assumed: three
separate session files, one user turn each, and a relaunch that opens by planning
to read the ledger because it has no memory of the sessions before it.

**The result worth carrying back into this repo is the two failures.** Both were
defects in chassis, and both failed the same way:

1. `sudo --preserve-env=` needs the `SETENV:` sudoers tag; the rule did not carry
   it, so every tool call was refused and the `verdict` tool never ran.
2. With that fixed, the per-run verdict file could not be written: created by the
   agent user in `/tmp`, appended to by root, and `fs.protected_regular` refuses
   that cross-uid `O_CREAT` open in a world-writable sticky directory — root
   included, because the check runs ahead of the capability check.

In both cases the tool errored, pi handed the error to the model as an ordinary
tool result, the model judged it environmental and finished the rest of the task,
and `run-agent` exited 0. Nothing downstream contradicted a run in which the tool
dispatcher had never once worked.

That is precisely the E1 defect class, reproduced in miniature and caught for a
few cents by a mission that does nothing but count. It is the argument for the
substrate stated as evidence rather than as a plan — and it is also the sharper
version of a harness-hygiene lesson this repo already holds: **an agent's exit
status does not attest that its tools were available.**

Deliberately out of scope, each its own decision: choosing the real mission,
METRICS rev-2, the nine-run relaunch, E2 (multi-agent on one graph),
`publish-repo` as a dispatched tool, and publishing 0.0.9.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 3a6ec59c319d3a668610482564b32c6ddf71c31d

## State Impact

- target: protocol-benchmark-4417 — the lab now lives in the private hypergraph-labs repo (roots light-raven-6945 / silver-fountain-4956); the relaunch's environment is a digest-pinned image with both ids recorded per run, closing the provisioning-procedure defect class that made E1 uncontrolled. The relaunch itself is still not run.
- target: bitter-sound-9744 — a fourth adopter, and the first that consumes the published package from PyPI rather than reaching into this checkout; adopted at 0.0.8, check at 0 violations.
- target: fair-field-3265 — new negative knowledge: an agent's exit status does not attest that its tools were available. Two chassis defects made every tool call fail while the harness reported the task complete at exit 0.
- target: weathered-union-7494 — new claim: 0.0.8 is now consumed from the public index by a repo with no path to this source tree, which is the adoption route the publication describes.
