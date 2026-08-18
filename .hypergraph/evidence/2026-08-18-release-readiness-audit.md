# 0.1.0 readiness audit — three independent review reports (2026-08-18)

Three parallel read-only reviews, each instructed to cite file:line and to verify
claims by execution where possible. Tree at commit 1a97029 (0.0.11). Collected
verbatim; the record node that attaches this file carries the synthesis.

---

## Report 1 — Conceptual layer (SPEC, README, backend/, templates, AGENTS.md)

### Core ideas

**Thesis.** Agent memory fails structurally, not for lack of context window (README.md:6-12, SPEC.md:7-13). Fix: split memory into two artifacts with different mutability and different topology, and make the distilled one *derived* rather than authored.

- **Record graph** — append-only, causally parented, one markdown file per node, topology = causality (SPEC.md:18-19, 193-195).
- **State graph** — mutable, single-writer, topology = *architecture*, not history (SPEC.md:20-23, 196-198).
- **Frontier** = open ∪ broken ∪ blocked — the entry point for an arriving agent (SPEC.md:53, 161).
- Cross-graph pointers are **markdown, never graph edges**, because edges would topologically merge the two DAGs (SPEC.md:49-52, INTERFACE.md:41-45).

**Genuinely novel:**
1. **I5's frontier-HWM.** "Reachability, never wall-clock" (SPEC.md:135-141) with a real failure mode named: a node authored pre-reconcile and merged post-reconcile is dropped permanently with no violation anywhere. Implemented correctly (tools/hypergraph.py:576-590). The sharpest idea in the spec.
2. **I7's typed negative knowledge**, especially the rule that generalizing N failures into "dead everywhere" is itself a decision requiring its own record node (SPEC.md:172-175).
3. **"Gaps, not tasks"** (SPEC.md:325-330): future work as falsifiable claims whose falsification channel is I2. "An empty frontier on a project with known ambitions is a defect, not an achievement" (SPEC.md:329-330).
4. **The record/state split *is* the git merge line** (SPEC.md:215-230) — a derivation, not an addition.

**Standard practice renamed:** the record graph is a lab notebook (the docs say so honestly, SPEC.md:33-35). **"Hypergraph" is the weakest naming claim**: what is implemented is a bipartite many-to-many relation — each `[rec: slug]` is a binary edge; a hyperedge with a distinguished center is an edge set. SPEC.md:116 itself says "Provenance is many-to-one".

### Contradictions and drift

1. **The mechanically-enforced set is wrong in SPEC.** SPEC.md:63-64 and :411 say I2/I4/I5/I6/I7. `check` also exits 1 on conflict markers (hypergraph.py:773), state-node `artifacts:` (:780-793), and **I1 under `--since`** (:982, exit at :1005) — so I1 *is* mechanically enforced in branch mode, contradicting SPEC.md:63. **`--since` appears nowhere in SPEC.md** despite being the PR gate README.md:109-110 and AGENTS.md:29 sell. Two enforced rules carry invariant label `"-"`.
2. **`heal` vs `upgrade --graph`.** SPEC.md:432-433 and README.md:143,169 declare `upgrade --graph` canonical and `heal` deprecated. backend/mirror.md:334-369 is written entirely in `heal` and never mentions `upgrade --graph`; local-adapter.md:184,:245-246,:287 use it live; SPEC.md:312 contradicts SPEC.md:432 within one file.
3. **The reconcile skill contradicts I5 directly.** skills/hypergraph-reconcile/SKILL.md:43: "record nodes created *after the HWM node*" — precisely the wall-clock rule SPEC.md:135-141 forbids. The code is right (hypergraph.py:576-590); the instruction is the pre-0.0.5 rule.
4. **Version labels stale.** SPEC.md:1 says v0.0.11; SPEC.md:459 heads the last section "Future work (out of scope for v0.0.5)". Pre-v0.0.5 migration prose still in the normative body (:141,:144).
5. **"The skills do not know the mirror exists" (SPEC.md:456, mirror.md:1-3) is false**: AGENTS.md:37-43 makes `sync` (which publishes) a non-negotiable; reconcile SKILL.md:75-89 explains `push` stand-down.
6. **Onboarding contract absent from the reference implementation.** SPEC.md:395-398 lists the AGENTS.md sentinel block + `.hypergraph/AGENTS.md`; this repo has neither, and `hypergraph-init` never writes one — only adopt (SKILL.md:210) does. **A day-zero project gets two graphs and no agent contract.**
7. Smaller: README.md:264 names a `self` fixture that does not exist (it is `epoch`); templates/record-node.md:19 says artifacts are pointed at "by title" (locally they are paths); SPEC.md:262 requires a "closure line" but never gives the string (the load-bearing literals live at hypergraph.py:5156,5183); `.hypergraph/config.yml:23-25` carries a stale `backend:`-selector comment contradicting INTERFACE.md:10-11.

### Conceptual weaknesses

1. **I3 is unenforceable**: `--reconcile` is an honor-system flag (local-adapter.md:124-126, hypergraph.py:2655); no writer identity, no lease. mirror.md:36-39 admits a whole subsystem's correctness rests on it. SPEC.md:450 calling it "the mechanical I3 gate" oversells a self-attestation (and contradicts SPEC.md:99-105 calling I3 procedural).
2. **I8 is decorative**: no tool, no cadence, no record of a spot-check, no definition of "semantically equivalent"; no I8 proxy anywhere in the code.
3. **I2's `none:` escape**: checker requires only a non-empty reason (hypergraph.py:314-316); nothing detects a project where 90% of nodes declare `none:`. A `none:`-ratio warning is the obvious missing proxy.
4. **The epoch boundary uses the wall clock I5 forbids** (SPEC.md:283, hypergraph.py:288-300) — the same exposure I5 rejects for the HWM, unexamined.
5. **Provenance grows monotonically, nothing compacts it.** Measured here: largest `## Provenance` is 25 entries (wandering-sun-8831) citing ~27% of the record graph; four more ≥16. SPEC.md:209-211 compacts claims, says nothing about provenance. At scale this breaks both "readable in one sitting" and I8's spot-check affordability.
6. **Scaling unaddressed**: 92 record nodes → 525 KB record.json (5.7 KB/node → ~57 MB at 10k), fully loaded by `check` after every unit; flat directory; local adapter maps `list_children` to `grep -l` over every file (local-adapter.md:90-94) contradicting INTERFACE.md:30 "paged"; SLUG_RE will false-match prose at scale with no escaping convention.
7. **README honesty gap**: "≤ ~6 tool calls" stated as fact twice (README.md:31,:194) while the project's own frontier holds protocol-benchmark-4417 open with "no evidence yet shows it makes agent work better".
8. **Single-writer + teams**: no staleness bound, no bus-factor story (unreconciled is info, not violation — hypergraph.py:645,669), reconcile is judgment that does not shard, no per-subtree writer concept, `NEW` has no dedupe rule, `NEW` breaks the record→state audit direction, cross-branch I2 refuses impacts against unmerged siblings' state nodes.
9. **Negative knowledge has no lifecycle** — no un-wronging path when a high-confidence entry is falsified; confidence has no calibration rule.
10. **"Frontier" means two things** (SPEC.md:53 vs :55) two lines apart in the Vocabulary section.

### Missing for 0.1.0

1. Day-zero onboarding contract written by init. 2. CHANGELOG + versioning policy (what a minor bump may change; whether invariant numbers are stable; whether check output is a contract). 3. A single CLI reference (~18 subcommands, exit codes stated in three places that don't agree). 4. A worked end-to-end example with real nodes (the only real examples are tools/fixtures/local-graph/, mentioned once). 5. A general invariant-migration story. 6. A failure/recovery decision tree. 7. Any empirical results section. 8. A trust model for agent-written node bodies read as authoritative (mirror.md:490-494 has the reasoning, never generalized). 9. Repo-growth guidance.

### Removal candidates

- **backend/flywheel.md (296 lines)** — vendor API errata, "not agent-facing" by its own first line; belongs in the mirror module or docs/internal.
- **backend/mirror.md (506 lines)** — the largest doc in the project, longer than SPEC.md, for the optional feature. mirror.md + flywheel.md = 802 lines = **34% of the conceptual layer**.
- SPEC "Future work" (:459-487) — argues for its own deletion (:461-463).
- The viz signpost surface (~30 doc lines + a command that exits 2 + a config key nothing reads).
- backend/lanes.md provider table (N=1); the valuable contract notes are dispatch rules and belong there.
- Duplicated pitch/invariant text across SPEC/README/AGENTS/agents-block (the mechanism behind the drift above).

### Sizes

mirror.md 506 / SPEC.md 486 / local-adapter.md 312 / flywheel.md 296 / README.md 282 / config.example.yml 107 / lanes.md 90 / INTERFACE.md 79 / AGENTS.md 67 / templates 87 — conceptual layer total **2,355 lines**; backend/ is 54% of it. Skills SKILL.md total 851 lines (adopt alone 363 = 43%). Code 8,779 lines. Live graph: 92 record nodes / 8,591 lines; 25 state / 1,270.

---

## Report 2 — Implementation layer (tools/, tests/, packaging)

### Sizes

tools/hypergraph.py **6292** lines (208 functions, 459-line `main()`); tools/hypergraph_mirror.py **2487**; tests/ 5430 lines, **302 passed, 2 skipped in 11.52s** (skips are the double-env-gated live-mirror tests). Implementation:test ratio 0.62.

### Verified defects (each reproduced live)

1. **`load_graph` raw traceback** (hypergraph.py:193): `check` against a missing/malformed export raises bare FileNotFoundError — the exact failure class load_config's own docstring (:674-690) documents as having cost two benchmark runs. Same hole at :3444 and :2904. Highest-value single fix.
2. **`split_sections` is fence-blind** (:231-247): a fenced example `## State Impact` is parsed as a real declaration, and duplicate headings are silently merged by `setdefault` (:240) — false violations AND false passes on I2. `claim_units` (:444-450) already tracks fences correctly; the fix exists in-file.
3. **`SLUG_RE.findall` over free prose** (:405, :498): `https://github.com/org/repo-name-1234` in a provenance line → hard I4 violation, exit 1. `data-set-2024`, `a-b-c-1234` also match.
4. **Comment stripping inconsistent**: check_status_line (:376) and node_status (:387) do not strip HTML comments while three neighbours do — a leading `<!-- generated -->` fails I6 and renders `[?]` in STATE.md.
5. **String-sorted timestamps** at five sites (:2096 export "INTERFACE op 8", :590, :1418, :1082, :614): mixed `Z`/`+00:00` (Flywheel exports emit `Z`) sorts wrong — verified. Fix: sort by parse_ts with string tie-break.
6. **`install.sh` fails on the second run**: `_links_into` (:4101-4107) fires on the symlink `--link` itself created; documented install command exits 2 when repeated.
7. **`check_version_skew` 0.9.0 loop** (:4213-4216): a repo stamped `hypergraph_version: 0.9.0` (the retracted release) is told to upgrade the CLI — which resolves to 0.0.11 and re-stamps, forever.
8. **Dispatch claim closure is substring-based** (:5188 `"Dispatch closed:" in content`, :5182 title startswith): the lane protocol rides on two English literals in prose; any descendant merely quoting the phrase closes the claim. Also :5163 misnames `reconciled_at` as `_err`.
9. **`push --plan` writes to disk** (artifact hash cache, :3428) despite "network-free" help text, and its cache path (:3316) ignores the `cache_dir:` config key that export and sync honour.
10. Minor: push journal never rotated (mirror.py:819-855, 124 KB here, whole-file re-parse ×3 per pass); Pacer.backoff comment claims jitter that is not implemented (mirror.py:1088-1091); `dispatch ls` runs `git branch --merged` once per lane (:5148-5150).

### Checker gate worth knowing

Version-skew, tag-vocabulary, and artifact-path checks **only run when `--config` is passed** (hypergraph.py:884-890). Bare `hypergraph check` silently skips three checks.

### Dead code / stale deps

`tag_def` (:1496) and `artifact_abspath` (:1767) — zero callers. `numpy>=1.24` in pyproject.toml:31 — nothing imports it; the justifying comment describes tests that moved to the private lab repo on 2026-08-11.

### Duplication

Export-JSON shape normalization ×3 (:194-197, :3444-3447, :2904-2908) + a fourth field-aliasing variant (:2859). Four git-subprocess helpers with three error policies (:5348 swallows, :5112 raises, :2416 returns None, :797 wraps). `cmd_sync` hand-builds a 20-field argparse.Namespace (:5017-5040) duplicating push's flag surface.

### Test coverage holes

**`sync`: zero invocations** — the flagship agent-facing verb, the one the reconcile skill mandates, and the one with the hand-built Namespace. **`hwm` CLI: zero invocations.** Also untested: mint_slug, topo_order (incl. cycle guard), summary_line truncation, artifact_case_mismatch, merge_artifact_records, survey_git, upgrade_workflows, version_tuple, stamp_config_version; fenced-block parsing; slug false-positives; mixed-offset ordering; malformed export JSON. `render` has one test.

### Packaging

pyproject is correct and unusually well-defended: five version locations, four held in step by tests; test_packaging.py:100 builds a real sdist. Wheel verified byte-identical to tree; `dist/` fresh and gitignored. Minor: sdist ships no tests/; templates/github-actions/hypergraph-check.yml will never refresh a workflow an adopter saved under the repo's own older filename (upgrade_workflows matches by filename, :3968). Slug space 201M (birthday 50% at ~16.7k nodes) — fine; the real collision path is concurrent minting on separate branches (taken-set is working-tree only, :2503).

### Removal candidates (code)

viz stub + subparser + config keys (two releases past the cut); `heal` hidden alias; tag_def; artifact_abspath; numpy; `hwm --suggest` (pre-0.0.5 migration aid, zero coverage) — deliberate keep/cut decision; `push --strict` (its own help text says every strict field false-positives on a correct graph).

---

## Report 3 — Skills layer

### Ground truth

The symlink story holds: all 6 `.claude/skills/` entries and all 29 `references/` entries are tracked relative symlinks that resolve. The hatchling followlinks trap is pinned by pyproject.toml:57-70 + tests/test_packaging.py:100. Caveats: `skills/.DS_Store` is untracked and **not gitignored** while `force-include` takes `skills` wholesale — the next wheel built on this machine ships it; AGENTS.md:51 "skills load at session start" — only frontmatter does.

### Per skill (lines / verdict)

- **orient — 59 / strongest per byte.** Deliverable shape, ranking rule, stop rule, tie-break (node files beat STATE.md). One overclaim: :28 "no tool budget at all" vs its own frontmatter and README's "≤ ~6".
- **init — 85 / crisp, two mechanical defects.** :52-53 tells the agent steps 3/4 may need inverting without deciding (the only numbered workflow that declines to give an order); :59-60 compresses the CAS into `--expect $(… --print-sha)` — sha read at shell-expansion time, teaching the anti-pattern the lock prevents — and never says the `## Reconciliation` block must be hand-composed into `--body` (update has no `--hwm` flag; only `new` does, hypergraph.py:5920). adopt:185-186 says it; init doesn't.
- **record — 121 / strong, mildly over-weight.** Tagging section (:59-71) re-argues SPEC.md:378-382; `tags rm` exists (hypergraph.py:5959) and no skill mentions it; :80 mandates a per-unit `export` whose output is gitignored and regenerated by the next sync.
- **reconcile — 110 / good, one ambiguity, one false claim.** :63-69 never shows the multi-tip HWM syntax (SPEC.md:124 and the live root cool-king-8586.md:21 with six slugs do); `hwm --suggest` is pointed at only in the v0.0.5-migration bullet. :20-21 "this is the only skill that ever passes it [--reconcile]" is **false** — init passes it (:45,:48,:82-83, calling itself "one of the two places") and adopt passes it (:185); SPEC.md:104 agrees with reconcile. Three documents, three different writer counts; the true answer is three.
- **dispatch — 113 / best-designed new skill, one lifecycle hole.** Target grammar, claim convention, and guardrails are the best agent instructions in the layer. **`hypergraph dispatch close` is never mentioned** (CLI has open/ls/harvest/close, hypergraph.py:6208) while :103 names the abandoned-lane failure whose remedy it withholds.
- **adopt — 363 / weakest.** 43% of the layer's bytes for a once-per-repo operation; ships a numbered order it says at :299-301 is wrong for Mode A, plus a corrective §4, plus a parallel walkthrough — three representations of one procedure; :82 documents recovering from following its own instructions; factual error at :292 (`--slug` on state nodes "is refused" — the flag exists and is honored, hypergraph.py:5907,:2522; tests/test_local_backend.py:164 shows it succeeding). Its "four traps" (:279-297) are the highest-value 19 lines in the repo.

### Drift with distribution consequences

**`hypergraph upgrade` never installs a skill absent from the target** (hypergraph.py:3896-3897 `if not dst.exists(): continue`). Consequence: **no repo that adopted before 0.0.11 will ever receive hypergraph-dispatch from `upgrade`**, and nothing in templates/agents-block.md tells them to re-run `skills install`. A new skill is invisible to every existing adopter.

Also: templates/agents-block.md:19-20 (the block adopters install) still states the old `export` + `check` gate while every skill now says `sync`; adopt:210 writes "the four non-negotiables" where this repo's AGENTS.md has five; tests/test_upgrade.py:3 says "the five skills" (six since dispatch); the "## The CLI" preamble is duplicated ~verbatim across all six skills; "never write state nodes" is restated seven times.

### Missing workflows

1. **Recovering from a bad reconcile** — the most likely destructive event; recovery requires rewinding the HWM, which no document authorizes or describes. 2. **Merging a branch that carries record nodes** — fragments exist in three places, no skill owns the procedure; the multi-tip HWM a merge produces is exactly what reconcile under-specifies. 3. **upgrade/version-skew workflow** (needed doubly given the new-skill gap). 4. **`check --since` in the record skill** — the PR gate is absent from the skill a contributor actually runs. 5. Mirror setup for adopters. 6. `heal` (a full subcommand) mentioned once, parenthetically.

### Payload

In-repo: 851 lines / 51 KB + symlinks — free. **Installed: 347,970 B across 29 real files, of which 78% is six copies of spec.md (176,832 B) + six of local-adapter.md (94,092 B)** — copytree materializes the symlinks (hypergraph.py:4118-4119). Context cost at session start is fine (~450 tokens of frontmatter). On invoke: orient ~740 tok (excellent), record/reconcile/dispatch ~1,600-1,800 (fine), **adopt ~5,600 with ~17k if it follows its own reference pointers** — the one place weight and purpose fight.

### Merge candidates

init into adopt (adopt:11 already claims the superset; each spends ~30% of its wordcount on routing); the six CLI preambles → one sentence; record's tagging essay → 3 lines; adopt's numbered steps → replaced by the walkthrough it endorses.
