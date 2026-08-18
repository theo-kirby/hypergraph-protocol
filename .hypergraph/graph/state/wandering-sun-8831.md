---
node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
slug: wandering-sun-8831
title: Protocol mechanics
created_at: '2026-08-06T21:41:18.171074+00:00'
parents:
- cool-king-8586
summary: 'Two files after the 0.0.11 split: an offline core and a lazily-loaded mirror module. The 0.1.0 gate hardened checker parsing (fences, duplicates, whole-token slugs), guarded export loading, and put sync/hwm under end-to-end test; 327 tests.'
flywheel:
  node_id: 2b993e9c-708e-5940-a67f-cf80aa0955e4
  slug: wandering-sun-8831
  revision: 24
  pushed_at: '2026-08-18T12:12:46+00:00'
  content_sha256: 15abc68649f84017c83e0501923869e8e36ebddadc199cdebccaf99d108060e2
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

The implementation is two files depending only on pyyaml: `tools/hypergraph.py`, the offline core, and `tools/hypergraph_mirror.py`, the optional mirror's networked half, loaded lazily and never imported by offline commands [rec: blue-rain-3979]. It is the mechanism half of the protocol: what enforces the invariants, what an agent actually runs, and what the two graphs are read and written by [rec: flat-pine-9555].

- **`check` validates I2, I4, I5, I6 and I7 mechanically** over offline JSON exports, exits nonzero on violations, and proxies I1 as warnings; `render` emits STATE.md with the frontier first (broken → blocked → open) above an architecture tree [rec: flat-pine-9555].
- **Invariants are enforced at authoring time, not only at check time.** `new` runs the real checker over a candidate node before writing it, so a bad impact target exits 2 with nothing written; `--reconcile` is the mechanical I3 gate; `update` refuses record nodes outright; and `new state` rejects a pre-scaffolded body that would duplicate the CLI-generated template [rec: old-dawn-8747] [rec: careful-harbor-3902].
- **Seven local-backend verbs**: `export`, `import`, `new`, `update`, `push`, `tags` and `artifacts`. The round-trip is the strongest guarantee — importing the clean fixture into node files and exporting back yields node-for-node identical graphs that still check clean [rec: old-dawn-8747].
- **Both concurrency defects are fixed and each was found by construction rather than by review** [rec: vast-rain-4873] [rec: placid-ridge-4035]. Unreconciled enumeration is set subtraction against `ancestors_of()` over the record DAG, and `check_hwm` names *every* unresolvable tip rather than the first. `check_conflict_markers()` rejects `<<<<<<<`, `>>>>>>>` and diff3's `|||||||` at line start in both graphs and in `validate_node_content`, so the machine that would have committed a merge refuses before the one that would have checked it. A bare `=======` is deliberately not sufficient evidence — it is also a setext H1 underline — and is reported only inside a node already showing an unambiguous marker.
- **`hwm`, `hwm --suggest` and `check --since <ref>`** followed from it: the frontier and what is outstanding, a one-time migration aid expressing the pre-0.0.5 timestamp rule as ancestry, and the first mechanism that reaches a contributor who never read AGENTS.md [rec: placid-ridge-4035].
- **The I1 citation checker had a silent hole and it is fixed** [rec: clever-ledge-6588]. Claim units were `bullets or paragraphs` — either, never both — so a `## Current` section containing any bullet had its prose paragraphs excluded from the citation check entirely, and most state nodes mix the two. Units were also single lines, so a wrapped citation read as missing, which produced 27 false warnings on one adopted repo and taught its agent to reflow correct prose. A unit is now a bullet with its continuation lines, or a paragraph, with headings, fenced code and colon lead-ins excluded as structure. It earned itself immediately, finding 3 uncited claims in cadex and 8 in neural-whoop that both repos' passing `check` had never looked at.
- **`check` says exactly one thing about tags and it is a warning** [rec: clear-moss-4527]: where `.hypergraph/tags.yml` exists, an undeclared name is reported; where it does not, nothing is said. Never a violation — no invariant reads a tag, so failing a build over one would invent an obligation the spec does not carry.
- **Two artifact rules, and `check` still exits 0 on all of them** [rec: shady-bay-7654]: `artifacts:` on a state node is a violation; a path that is wrong about the world — moved, listed twice, resolving outside the repo, or spelled in a case that only survives on macOS — is a warning, with untracked-by-git collapsed to one info line. Exiting 0 is deliberate: an artifact is often a gitignored dataset a fresh clone was never going to have, and failing CI over its absence would make the feature useless for exactly the evidence it exists to hold.
- **Two real `check` defects were found by watching agents fail against it, not by review** [rec: staid-field-2723]. `check --config <missing>` raised an unhandled `FileNotFoundError` naming the plumbing instead of the problem, and two of three agents read that as "contents are wrong", wrote a one-line stub, and got "0 violations" because root inference had silently fallen back to guessing. Both are fixed, and an inferred root now warns — a warning rather than a violation, because a freshly initialised graph has exactly one parentless node.
- **A packaging defect made the sdist unbuildable while every declaration in `pyproject.toml` was correct** [rec: long-peak-1620]. hatchling walks with `followlinks=True` and skips any directory whose `(st_dev, st_ino)` it has seen; the committed dogfooding symlinks sort first, so it materialized the skills under `.claude/` and dropped the real tree as a duplicate. `skip-excluded-dirs = true` plus `exclude` fixes it — `exclude` alone made it worse.
- **The viz cut (0.0.9)**: the tool drops from 12,599 to 8,376 lines (−34%) with no HTML, no JS and no browser dependency left anywhere — the embedded page template, the viz section, the sources, the bundler and the playwright dev-group dependency all removed, with the JSON exports as the contract an external renderer consumes. `viz` survived as a signpost stub until the 0.1.0 gate removed it outright — the CLI is 16 subcommands with no hidden entries, and `tag_def`, `artifact_abspath` and the unused numpy dev-dependency went in the same cut [rec: loyal-tide-3608] [rec: steady-ember-8009].
- **`heal` folded into `upgrade --graph` at 0.0.11** — one verb for bringing an adopted repo current, with the polarity rule stated once: copies write by default because `git checkout` reverses them, and everything behind `--graph` is detect-only until `--apply`. Bare `--graph` lists the registry; `heal` survives as a hidden deprecated alias through the 0.0.x series, and `--graph --dry-run` is a parser error rather than a silent no-op [rec: violet-shade-9541]. The alias's window closed at the 0.1.0 gate: `heal` is no longer a command (argparse rejects it, pinned by test), and the deprecation plumbing went with it [rec: steady-ember-8009].
- **The mirror split (0.0.11): offline commands never import the network half — structurally.** Everything that resolves a credential, looks for a binary or opens a socket moved to `hypergraph_mirror.py` (2,487 lines; core 6,025), loaded through `_mirror()`, which registers the running core module as `hypergraph_core` before exec so class identities never fork across core's three module names. The offline mirror bookkeeping — `push --plan`, `--verify --against`, `--record-result`, legend and lineage — stays in core, and a subprocess test proves that export, check, `push --plan` and a mirror-less push load no mirror module at all [rec: blue-rain-3979].
- **`dispatch` joined the local-backend verbs**: the local lane provider (worktrees on `lane/<slug>` branches, slug minted never named; the dispatch brief on stdin never argv; harvest refuses dirty and reports arrived record nodes; teardown refuses while unharvested). With no agent configured, `open` provisions the lane and stands down at exit 0 with the manual steps — field-proven by the first acceptance dispatch [rec: dry-spark-3491] [rec: idle-crow-3832].
- **The 0.1.0 readiness audit found the checker could be lied to by legal markdown, and the gate's first three units closed the mechanics half** [rec: lively-spring-9646]. Reproduced live: fence-blind `split_sections` (a fenced example `## State Impact` counted as the section; duplicated headings merged silently), `SLUG_RE.findall` over whole lines reading URL tails ending in `-1234` as citations, inconsistent comment stripping on I6, a bare traceback on a missing export, and five sites sorting timestamps as strings. Fixed: one shared fence tracker; first-wins sections with duplicated load-bearing headings as violations; provenance slugs as the bullet's leading token with `[rec: …]` fallback and `evidence:` split on commas with fullmatch-only tokens; comment-stripped status; `load_export_json` exiting 2 with the regenerate instruction; `created_key` (chronological across `Z`/`+00:00`/offset spellings) at all five ordering sites [rec: humble-mist-8524] [rec: falling-snow-3475]. The repo's own committed graph is now a permanent regression net: `test_live_dogfood_graph_stays_green` exports it and asserts zero violations on every suite run [rec: humble-mist-8524].
- **`sync` and `hwm` are test-held end to end** [rec: witty-chart-7035]: offline sync writes exports and STATE.md without importing the mirror module, a violation exits 1 before any transport is built, the publish path stamps frontmatter through a fake host, `--no-push` stops after check, and a parity test pins the push Namespace `cmd_sync` hand-builds against every `push` subparser option — a forgotten flag now fails loudly. `hwm --tips` prints the record graph's childless tips, the frontier a fold-everything reconcile writes, with reachability semantics rather than the timestamp cutoff `--suggest` deliberately keeps for migration only.
- **The suite is at 340 tests** over committed fixtures — checker, local backend, collaboration, mirror, the split's structural guarantees, the upgrade fold, dispatch, and since the 0.1.0 gate the live-graph regression net and the sync/hwm end-to-end set [rec: violet-shade-9541] [rec: blue-rain-3979] [rec: dry-spark-3491] [rec: witty-chart-7035].

## Negative knowledge

- [scope: detecting protocol omissions with `check` | confidence: high | evidence: tiny-sunset-0847] the checker only sees declared-but-unreconciled impacts; work never recorded to the record graph is invisible to it by construction — repo HEAD sitting ahead of the newest record node's head_commit_sha is the detectable proxy (repo-drift check — a candidate not yet built).
- [scope: trusting `check`'s unreconciled count | confidence: high | evidence: little-bar-4131] the count is computed from cache exports, not the live graph — an agent that records after its last export leaves check reporting 0 unreconciled while the live graph is ahead; comparing the export's exported_at against recent activity is the fix (export-freshness check — a candidate not yet built).
- [scope: state-node frontmatter summaries under reconcile | confidence: medium | evidence: green-field-8645] `check` parses only node bodies — a reconcile that rewrites a body but not the frontmatter `summary:` leaves drift no invariant can catch; surfaced summaries then contradict the body (worst case observed: an "Open gap" summary on a working node).
- [scope: reporting tool errors to autonomous agents | confidence: high | evidence: staid-field-2723] an unhandled traceback is not an error message: it names the library that raised, not the thing the operator got wrong, and an agent will act on that misdirection. Two of three arm-C runs "fixed" a missing config by writing a stub that made the checker stop crashing and start guessing — the tool reported success throughout. Any failure an agent can cause needs an error that names the cause and the remedy.
- [scope: guarding CLI-generated markdown sections | confidence: high | evidence: sleepy-branch-3744] a substring test for a heading rejects prose that merely mentions it — anchor heading guards to line starts.
- [scope: running the test suite from a worktree | confidence: high | evidence: idle-crow-3832] `test_push_reports_actionably_when_no_transport_exists` asserts on the ambient checkout's branch, so the suite fails (1 test) in any worktree not on `main` — found by the first dispatch running the suite inside its lane. The test should pin its branch; until then, verify from the main checkout.

## Provenance

- wandering-rice-9747 — component seeded at project init
- flat-pine-9555 — checker and renderer implementation, green test run (M3)
- long-tree-4179 — the viz subcommand sharing the checker's parsers
- old-dawn-8747 — the local-backend subcommands, authoring-time validation, the round-trip guarantee
- sleepy-branch-3744 — the heading-guard fix and a corrected suite count
- green-field-8645 — the audit that found summary drift and the frontmatter blind spot
- tiny-sunset-0847 — blind-test finding: unrecorded work is invisible to check
- little-bar-4131 — stale exports under-report unreconciled work
- shady-quill-2790 — epoch support in the checker
- careful-harbor-3902 — the pre-scaffolded-body guard
- staid-field-2723 — two check defects found through the benchmark's arm C; --version added
- vast-rain-4873 — two reproduced checker defects: timestamp HWM enumeration and undetected conflict markers
- placid-ridge-4035 — ancestry enumeration, conflict-marker detection, hwm and check --since
- long-peak-1620 — the sdist packaging defect from the dogfooding symlinks
- clever-ledge-6588 — the I1 unit rule stopped checking paragraphs the moment a section had a bullet
- clear-moss-4527 — the one tag rule check gained
- shady-bay-7654 — hypergraph artifacts and the two artifact check rules
- autumn-glade-5802 — update --parent/--root, cycle detection in local_graph, suite to 337
- late-sage-5549 — renamed to Protocol mechanics, with storage and retroactive repair as children
- loyal-tide-3608 — the viz cut: −34% of the file, the suite to 283, playwright out
- violet-shade-9541 — heal folds into upgrade --graph; the polarity rule stated once
- blue-rain-3979 — the mirror split: two files, the no-network promise made structural
- dry-spark-3491 — the dispatch verb: local lanes as worktrees
- idle-crow-3832 — the lane-unclean suite finding from the first acceptance dispatch
- vast-birch-5192 — Operator directive: the release label is 0.0.11, not 0.9.0
- lively-spring-9646 — the 0.1.0 readiness audit: checker trust defects reproduced live
- humble-mist-8524 — U1: fence-aware sections, duplicate-heading violations, whole-token slugs, the dogfood regression net
- falling-snow-3475 — U2: guarded export loading, chronological created_at ordering
- witty-chart-7035 — U3: sync/hwm end-to-end tests, the push-Namespace parity pin, hwm --tips
- steady-ember-8009 — U5: the viz stub and the heal alias removed; dead code and numpy cut
