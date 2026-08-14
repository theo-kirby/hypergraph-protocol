---
node_id: 2df7ab48-c7cf-5b86-a321-7a6d0fe0cf2c
slug: shady-bay-7654
title: 'Artifacts land: op 9 as repo-relative paths, pushed to Flywheel, verified live'
created_at: '2026-08-14T11:19:00+00:00'
parents:
- early-mesa-8507
summary: 'Op 9 implemented in both halves: an `artifacts:` list of repo-relative paths on record nodes, with `hypergraph artifacts {ls,add,rm,mv}`, check warnings that never fail CI, a viz Evidence section, and `push` uploading each file as a real Flywheel artifact. Identity is `<path>@<sha12>` in the title, so the listing that supplies expected_revision is also the dedupe set; a journal covers the crash window and a partial batch raises rather than guessing. Live round trip verified the one load-bearing assumption: title and metadata both round-trip byte-identical. 324 tests pass; extensibility claim came in at zero new comparator entries and one healer.'
artifacts:
- .hypergraph/evidence/2026-08-14-live-artifact-round-trip.json
flywheel:
  node_id: f6c9cf38-4e65-519f-8a68-cdb66a9f0385
  slug: morning-surf-2060
  revision: 1
  pushed_at: '2026-08-14T11:21:59+00:00'
  content_sha256: 12b3783cfa5646307cd18fcadcf4806d767a556004ef3e4aade3f8ebb62b43b9
  artifacts_sha256: d4cb42847679b4f9229ad1b43e21cb23a46276c72a498cf23199c65deab81b65
  artifacts:
  - path: .hypergraph/evidence/2026-08-14-live-artifact-round-trip.json
    sha256: 749ea38de30cd889b21b1128eec69166fc3897316dd735c0692981ee3bf61aef
    artifact_id: 00d65fa2-738c-544a-9958-f7108a95ac7b
    uploaded_at: '2026-08-14T11:21:58.812615+00:00'
---
## What

Implemented **INTERFACE op 9** — artifacts — in both halves, and shipped them
together.

**Local.** A record node carries an `artifacts:` frontmatter list of repo-relative
paths. `check` reports paths that are wrong about the world; `hypergraph artifacts
{ls,add,rm,mv}` and `hypergraph new --artifact` author them; the viz panel renders an
**Evidence** section; `import --force` carries an existing list forward.

**Mirror.** `push` uploads each linked file as a real Flywheel artifact on the
mirrored node, with `artifacts:list`/`artifacts:upload`, a journal-backed recovery
path, and a per-node revision fold. `heal artifacts` records what a frozen archive
still holds under `origin.artifacts`.

Op 9 goes from *"not implemented — reference it by path from `## Method` / `## Result`"*
to implemented **as paths, not as custody of bytes**.

## Why

Follows `early-mesa-8507` and the tags chain behind it: op 10 established the pattern
this reuses wholesale — a *name* is the portable identity, the assignment lives in
frontmatter, a sibling `*_sha256` stamp keeps the body hash untouched, one
`FIELD_COMPARATORS` entry serves verify and heal alike. Op 9 is the same shape with
*path* where op 10 says *name*.

The cost of not having it was measured in the field. On another machine, agents
working inside a Hypergraph project kept calling **Flywheel MCP directly** — and
artifacts were where it showed first, because when an agent wants to attach a log or
a plot, the only artifact tool in reach was Flywheel's. That evidence then lived
*only* on Flywheel: `push` sends node bodies, tags, legend and lineage, never files.
So the repo — the graph of record, the thing that is supposed to travel offline —
did not hold the evidence its own claims rest on. Agents were reaching past the
protocol because the protocol had nothing there.

Six decisions were settled before any code:

1. **Repo-relative is canonical.** Input is cwd-relative like `git add`; storage is
   repo-root-relative, so a path survives a clone. No `repo_root:` config key — an
   absolute path committed into the repo goes stale the moment the checkout moves,
   and takes every artifact path with it. Git already knows.
2. **A missing file is a `check` warning and exit 0.** A gitignored 40 GB dataset
   absent on a fresh clone must not fail CI, or the feature is useless for exactly
   the evidence it exists to hold.
3. **Record nodes only.** State is rewritten on every reconcile, so a pointer hung
   there has no stable owner. `artifacts:` on a state node is a violation.
4. **Frontmatter-only edits are legal on committed record nodes.** `LocalNode.sha256`
   hashes the **body**, so append-only is untouched — the same property that already
   lets `push` stamp `flywheel:` and `heal tags` rewrite `tags:` on frozen nodes.
5. **Changed bytes → upload the new version, supersede the old, never delete.**
   Regenerating a plot stays ordinary repo work. Evidence is versioned, not frozen.
6. **No opinion on gitignore.** Untracked artifacts upload with one warning line that
   the mirror will be the only copy. What gets committed is the agent's call.

## Method

**Landed in 15 steps**, ordered so steps 1–3 and 6–7 changed no behaviour and step 10
was the first that could write to a mirror.

**Path plumbing.** `normalize_artifact_path` tries **lexical** containment first and
`realpath` only as a fallback. The order is the point: a symlink into `/Volumes/big`
is the pointer the author meant, and resolving past it rewrites their path into one
that means something else elsewhere. The fallback exists for the reverse case —
darwin's `/tmp` → `/private/tmp`, where two spellings are one directory. A separate
`read_artifact_path` resolves a path *read back* from frontmatter against the repo
root rather than cwd; confusing the two makes `check` report every artifact missing
when run from a subdirectory. `artifact_case_mismatch` does one `os.scandir` per
segment — the only detector for works-on-macOS-fails-on-Linux-CI.

**Two subtleties that are easy to get backwards, both closed deliberately.**
A path outside the repo is *stored and warned* locally (a path list in a markdown file
is a strange but legal thing to write) and a **hard refusal at upload** — only there
does `artifacts: ../../.ssh/id_rsa` become an instruction to send a file somewhere.
And `FIELD_COMPARATORS["artifacts"]` already existed and means *mirror artifact
objects*: `side_from_local` was wired to `flywheel.artifacts` (the ids), never
`node.artifacts` (the paths), so the comparator diffs id-sets against id-sets and the
`flywheel:` block is the path→id translation table that makes it work with no mapping
step. Wiring it the other way diffs paths against store ids and reports every node as
drifted, forever.

**Identity and idempotency — the highest-risk part.** An artifact upload is an
**append**, and a repeated append duplicates. `artifact_title(path, sha) →
"<path>@<sha[:12]>"` makes *"this title is already attached"* mean exactly *"these
bytes, for this path, are already attached"*. Two guards:

- **Guard A — the listing, always.** `artifacts:list` returns the records *and*
  `node_revision`, so the read the upload needs for its lock is the same read that
  supplies the dedupe set. One fact carries the design.
- **Guard B — the journal**, for the crash window between request and fold. A
  partially-present batch **raises**, naming node and titles, leaving the intent
  pending: re-uploading would duplicate the half that landed, and `artifacts:delete`
  is not wired. Ambiguity is reported, never resolved.

**The append/atomic-replace generalization.** `mirror_call` gained `attempts=`; batches
pass `attempts=1`. 409 is not re-read-and-reissued and 429 is not retried, because the
tags inversion — where a conflicting assignment may safely be re-issued — is a property
of *atomic replace*, not a general rule. Appends keep no-blind-retry in full. This is
the rule the tags exception was always an instance of, and it is now written down in
`mirror.md` as such.

**Ordering: after tags, before the legend.** `tags:create` bumps the revision of *every*
node in the graph; an artifact finalize bumps exactly one. Whichever runs second
invalidates the first's stamps — but artifacts are immune by construction, since their
`expected_revision` comes from a listing taken microseconds earlier rather than from
frontmatter. Putting the immune phase last means no third resync sweep has to exist.
The `execute_push` split became **three-way**: `o["op"] != "tags"` would have swept
artifact ops into the node loop, a real breakage. `plan_op_counts` became a 4-tuple
counted by op — adding a third op kind to a function that computed updates *by
subtraction* would have reintroduced the exact bug its own docstring documents.

**Contract, verified against the installed CLI rather than guessed.** Two findings
changed the design: `artifacts:list` exposes `--limit` and **no `--offset`**, and the
server clamps `limit` to 200. So the CLI transport cannot page at all, and past 200
artifacts on one node it **raises** and points at `--transport rest` — a truncated
listing reads as "these are not attached" and re-uploads everything after it. REST does
prepare → raw PUT → finalize by hand: the signed PUT goes to an external object store,
so it must not reuse `_request` (which would send our bearer token to a third party and
stamp `Content-Type: application/json` onto a PNG), and the Idempotency-Key is derived
from `sha256(node_id:batch_sha256)` rather than random, since reusing a key with a
different payload hash is a 409.

**Verification.** `pytest -m "not live"`, then end-to-end on this repo's own graph and
live mirror: attach → `check` exit 0 → `git mv` → warning, still exit 0 → `artifacts
mv` clears it → viz Evidence renders → `push --plan` → `mirror doctor` → `--dry-run` →
real push → `artifacts:list` → second push → `push --verify --strict`.

## Result

**Tests: 324 pass** (was 280; +44), 2 live tests deselected. `check` 0 violations,
0 warnings. `sync` clean.

**Live mirror round trip, run for real on 2026-08-14 (CLI 0.1.108).** This settles
what was the design's one unverified load-bearing assumption — the identity rule reads
`title`, whose contract is *"display label"*:

| checked | result |
| --- | --- |
| `title` round-trip | **byte-identical**: `backend/flywheel-host.md@128f0c512bf7` |
| `metadata.hypergraph` round-trip | **intact** — `{path, sha256}` came back whole |
| revision bump | 0 → 1, exactly one for the batch |
| `artifact_id` from the listing | present; never taken from the upload response (`{}`) |
| second push | uploaded nothing — Guard A dedupe holds against the real host |
| `push --verify --strict` | 0 drift findings |

So the corroborating `metadata` check is **real rather than aspirational**, and the
live test now asserts it: a host that starts normalizing titles becomes a test failure
instead of a silent duplicate-upload bug.

The listing is captured verbatim in
`.hypergraph/evidence/2026-08-14-live-artifact-round-trip.json` — the only durable
record of that run, since the artifact itself was verification scaffolding and was
deleted from the mirror afterwards. One field is redacted and the file says which:
`storage_url`, a signed S3 URL carrying credentials and a one-hour expiry. (This node
is also the feature's first user: that path is in its own `artifacts:` list.)

The removal path was exercised too: dropping the path from `artifacts:` re-stamped to
empty, performed **no mirror write at all**, kept the entry in `flywheel.artifacts`,
and printed one line saying the mirror copy was left in place.

**Tests that protect a property nothing else does.**
`test_artifacts_add_leaves_the_body_sha256_untouched` is the load-bearing one for
decision 4, with `..._leaves_the_push_plan_empty` and `..._verify_mirror_clean` beside
it and `test_update_still_refuses_record_nodes` proving the refusal was not weakened to
make room. `FakeTransport` grew `artifacts()`/`upload_artifacts()`, stores real bytes,
bumps the revision **once per batch** (a fake that bumped per item would let a broken
fold pass), and **raises `AssertionError` on a duplicate title** — the artifact
analogue of the duplicate-`commit_new` assertion. A blind retry cannot pass the crash
test.

**The extensibility claim came in under budget.** The comparison layer was built with
a comment admitting `artifacts` was a speculative entry — *"a claim with no second
instance is not evidence"*. Op 9 needed **zero** new comparator entries and **one**
registry entry; the only real work was teaching `side_from_local` which block to read
the ids from. That comment has been rewritten to point at `HEAL_ARTIFACTS`.

**Three things this genuinely strains, recorded rather than papered over.**

1. **"The mirror is a regenerable, one-way projection" bends here, and it is now a
   documented bounded exception.** A node body is regenerable from the repo forever;
   an artifact's bytes are regenerable only while that file exists at that path.
   Decision 6 makes "delete it in a later commit and the mirror holds the only copy"
   reachable *by design*. SPEC's speculative "artifacts (op 9), which the shipped
   storage does not implement" was replaced by a real open item: artifact **custody**.
2. **"Duplicates are the only unrecoverable failure" gained a second species.** A
   duplicate artifact is milder than a duplicate node — nothing points at it — but
   `artifacts:delete` stays unwired, so it is permanent clutter. Guard A makes it
   nearly unreachable; accepting the residual is the **first place the never-delete
   stance costs something**, and `mirror.md` says so.
3. **`push_plan` stopped being a pure function of `graph_dir`.** It now stats and
   hashes files across the repo. Its *network-free* guarantee survives — the test
   pinning "builds no transport at all" still passes — but its "reads only the graph
   directory" property does not, and its cost is now proportional to evidence size.
   Hence `repo` as an explicit parameter and a `(size, mtime_ns)` stat cache.

**No healer for the normal case, and that difference from tags is the point.** An
adoption that predated tags *lost the names*; an adoption that predated artifacts lost
nothing, because there was nothing local to lose. A repo adding paths to old record
nodes is served by `push`, since the plan fires on the absent stamp. `HEAL_ARTIFACTS`
exists only to inventory what a frozen archive still holds, under `origin.artifacts` —
frontmatter only, offline-capable, `git checkout`-reversible, and deliberately **not**
a repatriation: those bytes are not in the repo, so re-uploading them would leave the
mirror holding evidence the repo cannot regenerate.

**Docs reconciled, not appended.** Every sentence that this made false was rewritten in
place: `INTERFACE.md` op 9 (plus two new contract notes — a repo-relative path is the
portable identity, and artifacts attach to record nodes and nothing else),
`local-adapter.md` §9 (rewritten from "not implemented", including the paragraph
insisting prose and list are both required — the prose is the claim, the list is its
index), `SPEC.md` :201/:273/:438, `README.md`, `mirror.md` (new `## Artifacts`),
`flywheel.md` (new `### Artifacts`), and `lineage_content`, whose pinned substring
*"Artifacts did not survive the import"* stays true while its reason clause was
corrected — so the test pinning it needed no change.

**And the step that decides whether any of this reaches the field:**
`skills/hypergraph-record/SKILL.md` step 7 now says commit the files (or don't),
explain them in `## Method`/`## Result`, **and enumerate them** — with a guardrail
naming `artifacts:` as the one frontmatter key that may be edited on a committed
record node, and the body as the thing that still may not be.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: c4abd58d8dfb15df428579382531a4bb400d5f2a

## State Impact

- target: blue-sun-8921 — INTERFACE op 9 is implemented, as repo-relative *paths* rather than custody of bytes: a path is the portable identity exactly as a slug is for a node and a name is for a tag, and a store's artifact id is bookkeeping. Two new contract notes: op 9 travels paths, and artifacts attach to record nodes and to nothing else. The 'artifacts are optional; the shipped implementation omits them' clause is now false and was rewritten — a store need not hold them, but this adapter implements both optional ops (9 and 10) without asking the store for anything.
- target: wandering-sun-8831 — the CLI gained `hypergraph artifacts {ls,add,rm,mv}` and `new --artifact`, plus two checks: `artifacts:` on a state node is a violation, and path problems (moved, duplicated, outside the repo, case-mismatched, untracked) are warnings and infos that leave `check` at exit 0 — a gitignored dataset absent on a fresh clone must not fail CI. A project declaring no artifacts hears nothing at all. `check` and `push`/`sync`/`mirror` gained `--repo`; `plan_op_counts` became a 4-tuple counted by op rather than by subtraction.
- target: empty-forest-6305 — `push` now uploads the files record nodes point at as real Flywheel artifacts, ordered after tags and before the legend so the phase immune to revision invalidation runs last and no third resync sweep exists. Recovery rests on title-as-identity with a listing-based dedupe and a journal; 409 and 429 are neither reissued nor retried, because an upload is an **append** and the tags retry inversion is a property of *atomic replace* — the generalization that rule was always an instance of. Two costs are now recorded rather than discovered: 'the mirror is a regenerable projection' has a **bounded exception** (an artifact's bytes are regenerable only while that file exists at that path, and gitignored evidence is permitted by design), and 'duplicates are the only unrecoverable failure' gained a milder second species that `artifacts:delete` stays unwired to fix. `push_plan` also stopped being a pure function of graph_dir — it stats and hashes across the repo, network-free but no longer graph-dir-only.
- target: retroactive-repair-5104 — `HEAL_ARTIFACTS` is healer number two, and it makes the framework's extensibility claim measured rather than hopeful: zero new comparator entries, one registry entry. It inventories what a frozen archive still holds under `origin.artifacts` — frontmatter only, offline-capable, git-checkout-reversible, and deliberately never a repatriation. The **normal case needs no healer at all**, and that difference from tags is the finding: an adoption predating tags lost the names, an adoption predating artifacts lost nothing, so a repo adding paths to old nodes is served by `push` alone.
- target: polished-pond-2718 — the viz panel gained an **Evidence** section on record nodes, rendering paths as plain code with no link (the page is emailed and committed, so a broken file:// reads worse than the path) and no existence flag baked in (a 'missing' computed at render time becomes a stale claim about somebody else's machine). The state-node payload has no `artifacts` key at all, and that absence is the documentation for 'evidence lives on record nodes'. STATE.md deliberately does not change.
- target: dry-wildflower-2260 — hypergraph-record step 7 is the step that decides whether any of this reaches the field, and it was rewritten: commit the files or don't, explain them in `## Method`/`## Result`, **and enumerate them** with `hypergraph artifacts add` or `--artifact`. New guardrail naming `artifacts:` as the one frontmatter key that may be edited on a committed record node — the append-only hash covers the body — while the body still may not be, and `hypergraph update` still refuses record nodes outright.
