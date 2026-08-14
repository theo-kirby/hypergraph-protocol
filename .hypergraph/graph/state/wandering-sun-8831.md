---
node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
slug: wandering-sun-8831
title: Checker tooling
created_at: '2026-08-06T21:41:18.171074+00:00'
parents:
- cool-king-8586
summary: 'check/render/viz + local backend + epoch support + push --verify/--legend/--lineage + import --fork + artifacts; 324 tests green; known blind spots: unrecorded work, stale cache exports, frontmatter summary drift, archive-spliced verify exports.'
flywheel:
  node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
  slug: wandering-sun-8831
  revision: 16
  pushed_at: '2026-08-14T11:21:56+00:00'
  content_sha256: 2805dbcbf98dc63325eef5b63a82ae71d0d57d7f0f2693317cdb31df4cb0d80f
---
Status: working

## Current

- tools/hypergraph.py (single-file uv script, pyyaml only) implements `check` — mechanical validation of I2, I4, I5, I6, I7 over offline JSON exports with nonzero exit on violations, I1 proxied as warnings — and `render` — STATE.md with frontier first (broken → blocked → open) and architecture tree [rec: flat-pine-9555].
- Third subcommand `viz` added, reusing the checker's section/impact/citation parsers and export normalization to emit the interactive visualization (see the Visualization component) [rec: long-tree-4179].
- Five more subcommands implement the local backend — `export`, `import`, `new`, `update`, `push` — while the `check`/`render`/`viz` code paths were left untouched; the tool stays network-free, so Flywheel mirroring is emitted as a plan the skill layer executes [rec: old-dawn-8747].
- Adoption-epoch support: `check` resolves `epoch.marker` to a created_at cutoff and exempts strictly-older record nodes from I2 (one info finding with the count); an unresolvable marker is a violation; authoring-time validation is never exempted [rec: shady-quill-2790].
- Mirror-integrity subcommands: `push --verify --against <export>` reports missing nodes either side, body-hash and summary mismatches, and revision skew as DRIFT findings (exit 1), exempting the legend node and config-declared `mirror_roots` (the latter added after a false flag on a3go's fresh mirror roots); `push --legend` emits the mirror-only slug-legend body; `import` skips legend nodes [rec: careful-harbor-3902] [rec: humble-clover-7048]. `push --lineage` renders the mirror record root's body from the config `archive:` block (errors when there is none), and `push --plan` warns on stderr above 200 creates, naming incremental result-recording and epoch-split [rec: tender-moss-3792].
- `import --fork` splits the two jobs the `flywheel:` block was doing at once: the source graph's ids go to a new `origin:` block (immutable provenance, read by nothing), and `flywheel:` is omitted, so `push_plan` plans every imported node as a `create` under roots the project owns. Plain `import` is byte-identical to before — it still serves re-homing a graph you own. No logic change was needed in `push_plan` or `verify_mirror`, and `check` reads neither block, so I1-I8 are untouched [rec: tender-moss-3792].
- The tool now enforces protocol invariants at authoring time, not only at check time: `new` runs the real checker over a candidate node before writing it (a bad impact target exits 2 with nothing written), `--reconcile` gates every state write (I3), `update` refuses record nodes outright, and `new state` rejects pre-scaffolded bodies that would duplicate the CLI-generated template sections [rec: old-dawn-8747] [rec: careful-harbor-3902].
- Test suite green: 72 pytest cases over committed fixtures — checker (incl. 4 epoch cases), viz, and local backend (incl. verify/legend/drift, fork-import, and skills-install cases) [rec: tender-moss-3792]. The strongest local-backend guarantee is the round-trip: importing the clean fixture into node files and exporting back yields node-for-node identical graphs that still check clean [rec: old-dawn-8747].
- Two real defects in `check` were found by watching agents fail against it in the benchmark, not by review [rec: staid-field-2723]: `check --config <missing>` raised an unhandled `FileNotFoundError` from pathlib, naming the plumbing instead of the problem — two of three arm-C agents read that as "contents are wrong", wrote a one-line `backend: local` stub, and got "0 violations" because `find_root` had silently fallen back to guessing the roots. Both fixed: a missing or unparseable config exits with an instruction naming the file and what a config is for, and an inferred root now emits a warning when a config was supplied and declares none — a warning rather than a violation, because a freshly initialised graph has exactly one parentless node and a correct graph must not fail over how its root was located. `--version` added, which the benchmark's install pin and `preflight.py` both require [rec: staid-field-2723].
- Verified against real Flywheel exports: normalizes the live edge encoding (incoming_ids as parents), alongside parent_ids/parents fixture forms [rec: steep-cell-5173].
- **Both reproduced concurrency defects are fixed in v0.0.5** [rec: placid-ridge-4035], and each was found by construction rather than by review [rec: vast-rain-4873]. Unreconciled enumeration is now `unreconciled_nodes()` — set subtraction against `ancestors_of()` over the record DAG — and `check_hwm` names *every* unresolvable tip rather than the first. `check_conflict_markers()` rejects `<<<<<<<`, `>>>>>>>` and diff3's `|||||||` at line start, in both graphs and in `validate_node_content`, so the machine that would have committed the merge refuses before the one that would have checked it.
- A bare `=======` is deliberately **not** sufficient evidence: it is also a setext H1 underline, so it is reported only inside a node that already shows an unambiguous marker. Flagging it alone would fail honest documents [rec: placid-ridge-4035].
- New verbs: **`hypergraph hwm`** (frontier plus outstanding nodes) and **`hwm --suggest`**, the one-time migration aid that expresses the pre-0.0.5 timestamp rule as ancestry; and **`check --since <ref>`**, which fails a branch that changed files without adding a record node — the first mechanism that reaches a contributor who never read AGENTS.md [rec: placid-ridge-4035].
- Suite at **282 tests**, up from 250, with `tests/test_collaboration.py` carrying 32 of them including the literal two-branch reproduction from the investigation. Two older tests changed contract rather than breaking: `read_hwm` returns `[]` for `none`, and the no-transport degradation case now asserts exit 0 with the remedy still named, plus exit 2 under `--require-mirror` [rec: placid-ridge-4035].
- **A packaging defect made the sdist unbuildable, and every declaration in `pyproject.toml` was correct** [rec: long-peak-1620]. hatchling walks with `followlinks=True` and skips any directory whose `(st_dev, st_ino)` it has already seen; `.claude/skills/hypergraph-*` are the committed dogfooding symlinks into `skills/` and sort first, so it materialized the skills under `.claude/` and dropped the real tree as a duplicate. `skip-excluded-dirs = true` plus `exclude` fixes it — `exclude` alone made it worse. Suite to 283, the new test building an sdist and asserting it carries every path the wheel force-includes.

**The I1 citation checker had a silent hole, and it is fixed** [rec: clever-ledge-6588]. Claim units were `bullets or paragraphs` — either, never both — so a `## Current` section containing any bullet had its prose paragraphs excluded from the citation check **entirely**, and most state nodes mix the two. Units were also single lines, so a citation that wrapped onto a continuation read as missing; that produced 27 false warnings on one adopted repo and taught its agent to reflow correct prose. A unit is now a bullet with its continuation lines, or a paragraph, with headings, fenced code blocks and colon lead-ins to a bullet list excluded as structure rather than claims. The fix earned itself immediately: it found 3 uncited claims in cadex and 8 in neural-whoop that both repos' passing `check` had never looked at.

**`check` gains exactly one thing to say about tags, and it is a warning** [rec: clear-moss-4527]. Where `.hypergraph/tags.yml` exists, a tag name on a node that the vocabulary does not declare is reported; where it does not exist, `check` says nothing about tags at all. Never a violation: no invariant reads a tag, so failing a build over one would invent an obligation the spec does not carry. It is also the *only* brake on a taxonomy nothing enforces, now that the record skill teaches tagging — which makes whether this project's own vocabulary stays coherent a thing to watch rather than a thing that is settled [rec: simple-ocean-1716].

**`hypergraph artifacts {ls,add,rm,mv}` is the sixth local-backend verb, and `check` gained two rules for it** [rec: shady-bay-7654]. `artifacts:` on a state node is a **violation**; a path that is wrong about the world — moved, listed twice, resolving outside the repo, spelled in a case that only survives on macOS — is a **warning**, and untracked-by-git is one collapsed info line. `check` still **exits 0** on all of them, deliberately: an artifact is often a gitignored dataset a fresh clone was never going to have, and failing CI over its absence would make the feature useless for exactly the evidence it exists to hold. A project that declares no artifacts hears nothing at all, the same bargain the tag-vocabulary warning makes.

The command exists for the same reason `tags` does — a path hand-typed into YAML is normalized against nothing and wrong only on somebody else's machine — and it is the tool's first legal writer of frontmatter on a *committed record node*. That is sound because the append-only hash covers the **body**: `LocalNode.sha256` hashes content alone, and this command cannot reach the title, the summary or the body. `hypergraph update` still refuses record nodes outright, and a test asserts it was not weakened to make room [rec: shady-bay-7654].

Three smaller pieces landed with it [rec: shady-bay-7654]: `new --artifact` warns rather than refuses on a missing path (a whole node has been composed and validated by then, and `artifacts rm` fixes a typo a second later — `artifacts add` refuses instead, because there the typo is all there is to lose); `import` carries an existing `artifacts:` list forward, since no export can supply one and `--force` is exactly what a re-import after an upgrade needs; and `plan_op_counts` became a **4-tuple counted by op**, because adding a third op kind to a function that computed updates *by subtraction* would have reintroduced the exact bug its own docstring documents. Suite at **324 tests**, up from 280.

## Negative knowledge

- [scope: parsing flywheel_export_subgraph output | confidence: high | evidence: steep-cell-5173] the export encodes edges as incoming_ids/outgoing_ids, not parent_ids — a parser reading only parent_ids sees every node as a root.
- [scope: detecting protocol omissions with `check` | confidence: high | evidence: tiny-sunset-0847] the checker only sees declared-but-unreconciled impacts; work never recorded to the record graph is invisible to it by construction — repo HEAD sitting ahead of the newest record node's head_commit_sha is the detectable proxy (repo-drift check, SPEC future work).
- [scope: trusting `check`'s unreconciled count | confidence: high | evidence: little-bar-4131] the count is computed from cache exports, not the live graph — an agent that records after its last export leaves check reporting 0 unreconciled while the live graph is ahead; comparing the export's exported_at against recent activity is the fix (export-freshness check, SPEC future work).
- [scope: state-node frontmatter summaries under reconcile | confidence: medium | evidence: green-field-8645] `check` parses only node bodies — a reconcile that rewrites a body but not the frontmatter `summary:` leaves drift no invariant can catch; surfaced summaries then contradict the body (worst case observed: an "Open gap" summary on a working node).
- [scope: verifying an adopted project's mirror | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] `push --verify` proves nothing when the archive roots are spliced into the export it is given: the imported nodes' archive-owned ids resolve through the archive subgraph, so a mirror holding 3 record nodes of 111 exits 0. The export must cover the project's own `mirror_roots` alone.
- [scope: reporting tool errors to autonomous agents | confidence: high | evidence: staid-field-2723] an unhandled traceback is not an error message: it names the library that raised, not the thing the operator got wrong, and an agent will act on that misdirection. Two of three arm-C runs "fixed" a missing config by writing a stub that made the checker stop crashing and start guessing — the tool reported success throughout. Any failure an agent can cause needs an error that names the cause and the remedy.
- [scope: guarding CLI-generated markdown sections | confidence: high | evidence: sleepy-branch-3744] a substring test for a heading rejects prose that merely mentions it — anchor heading guards to line starts.
- [scope: validating files a merge tool can write | confidence: high | evidence: vast-rain-4873] `check` validates structure and citations but never the possibility that git itself wrote the file. A committed `<<<<<<< HEAD` block passes at 0 violations and reaches the public mirror. Any validator for files under version control has to reject conflict markers explicitly.

## Provenance

- clever-ledge-6588 — the I1 unit rule stopped checking paragraphs the moment a section had a bullet
- wandering-rice-9747 — component seeded at project init
- flat-pine-9555 — checker + renderer implementation and green test run (M3)
- steep-cell-5173 — live-export verification + edge-encoding fix (M5)
- long-tree-4179 — viz subcommand added sharing the checker's parsers
- morning-rain-7488 — suite to 22 tests (viz template/determinism cases)
- still-forest-9161 — viz test refresh under the unified view (count stays 22)
- tiny-sunset-0847 — blind-test finding: unrecorded work is invisible to check
- little-bar-4131 — cache-freshness facet: stale exports under-report unreconciled work
- old-dawn-8747 — five local-backend subcommands; authoring-time validation; round-trip guarantee
- sleepy-branch-3744 — corrected suite count (50) and the heading-guard fix
- green-field-8645 — audit found summary drift (22 vs 50 tests) and the frontmatter blind spot
- shady-quill-2790 — epoch support; suite to 54
- careful-harbor-3902 — verify + legend + pre-scaffolded-body guard; suite to 60
- humble-clover-7048 — mirror_roots verify exemption; suite to 62
- copper-moss-3669 — fork-import decision: the identity split and mirror-only verification
- staid-field-2723 — two `check` defects found through the benchmark's arm C: crashing on a missing config, and passing silently on one that declares no roots; `--version` added
- tender-moss-3792 — import --fork, push --lineage, scale guard, legend header; suite to 72
- northern-willow-0469 — mirror-only verify proven live on a3go
- vast-rain-4873 — two reproduced checker defects: timestamp-based HWM enumeration and undetected conflict markers
- placid-ridge-4035 — ancestry enumeration, conflict-marker detection, hwm and check --since; suite to 282
- long-peak-1620 — sdist packaging defect from the dogfooding symlinks; build-and-inspect test added
- clear-moss-4527 — the one tag rule check gained: an undeclared name is a warning, only where a vocabulary is declared
- shady-bay-7654 — `hypergraph artifacts`, the two artifact check rules, and plan_op_counts as a 4-tuple; suite to 324
