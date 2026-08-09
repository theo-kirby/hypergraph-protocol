---
node_id: cf9bc02f-194d-556f-807c-967211e36a68
slug: clever-ledge-6588
title: A mode A adoption with no author in the room, and the twelve defects it found
created_at: '2026-08-09T19:22:27+00:00'
parents:
- open-eagle-4603
summary: neural-whoop adopted mode A by an agent with no author available. Three code bugs reproduced and fixed (config node_id vs node file, pull/export path collision, the I1 checker skipping paragraphs), nine documentation defects fixed plus a mode A walkthrough, and the project reframed as a substrate for autonomous research and engineering.
flywheel:
  node_id: f0b33eb5-ae8b-50b2-9e40-f22b8eab7a46
  slug: square-tree-1344
  revision: 0
  pushed_at: '2026-08-09T19:23:46+00:00'
  content_sha256: 3c2f70959db7c68f676be64e32e18e55fc66a1b36ced7a920bd9fccc1c75452e
---
## What

A second field adoption — neural-whoop, mode A, 189 legacy Flywheel nodes, run by an
agent with no author available — then the three code bugs and nine documentation
defects it found, then a reframing of what this project says it is.

## Why

cadex tested mode B. Every ordering and artifact defect below lives on the **mode A**
path, which mode B never exercises, and none of them had been hit before because this
project's own adoption and the two prior field adoptions were all run with their author
in the room. Running one without an author, on a graph nobody here wrote, is what made
them visible.

## Method

The adopting agent's report claimed thirteen defects. Each was checked against the
source or reproduced in a scratch repo rather than taken on trust, which mattered:
**one claim was wrong.** It reported that `hypergraph import` requires a config, so the
documented mode A outcome is unreachable by any ordering. It is reachable —
`import --graph-dir .hypergraph/graph` needs no config, and `adopt --init` then prints
`adopted existing`. The defect is real but smaller than reported: step 4's prose insists
`--init` comes first and then describes the result only the *other* order produces.

## Result

**Three code bugs, all reproduced before being fixed.**

1. **`adopt --init` wrote a `node_id` the node file disagreed with.** It derived the id
   from the slug unconditionally, but a mode A root arrives through `import --fork`,
   which preserves the archive's id verbatim. On neural-whoop the config claimed
   `8e92751d…` while the node file said `51aabea1…`. `check` does not compare them and
   `push` reads the config, so the project would have published under an id nothing
   else in the repo used. The adopting agent hand-corrected the YAML — the exact
   failure `--init` exists to prevent. It now reads the node's own id.
2. **`mirror pull` and `export` collided on `.hypergraph/cache/record.json`.** The pull
   wrote it, the first export overwrote it, and the legacy graph was gone — while step
   7 still needs it and it is the only record of what stayed on the archive. The pull
   now writes `legacy-record.json` / `legacy-state.json`.
3. **The I1 citation checker had a silent hole.** Claim units were `bullets or
   paragraphs` — either, never both — so **a `## Current` section containing any bullet
   had its prose paragraphs excluded from the check entirely**. It also treated a unit
   as one line, so a citation that wrapped read as missing; that produced 27 false
   warnings on neural-whoop and taught its agent to reflow correct prose. Units are now
   bullets *with* continuations, and paragraphs, with headings, fenced code and
   colon-lead-ins to a list excluded as structure rather than claims.

The third fix immediately earned itself: it found **3 uncited claims in cadex and 8 in
neural-whoop** that both repos' passing `check` had never looked at. cadex's were all
lead-ins and are now correctly silent; **seven real ones remain in neural-whoop and are
not fixed** — citing them requires reading the record nodes they derive from, and
guessing a slug to silence a warning is precisely the invented provenance I8 forbids.

**Nine documentation defects**, now fixed in the adopt skill, plus a **mode A
walkthrough** — the ordering that works, with the reason it is not the numbered one.
The costly ones were mechanical and undiscoverable: `## State Impact` is refused in a
body and must come from `--impact`, which itself prepends `- target: `, so a line
copied from the template yields `- target: target: …`; state slugs are minted and
cannot be chosen, so the readable `NEW <kebab-name>` targets never resolve; and
advancing the HWM to the marker rather than to the record tips left **111 nodes
unreconciled** on a wide DAG. Two skill instructions were also wrong outside mode B:
"the prehistory bodies say so" names the one artifact mode A does not have, and
contract reconciliation is two writes, not one — an amendment inside the sentinels does
not stop a reader following instructions three hundred lines above it.

**The framing changed.** This was described as "a protocol for keeping research projects
legible to fresh agents", which is a description of the mechanism, not the goal. It is
now stated as a **substrate for autonomous research and engineering**: the memory layer
an agent needs to carry work across months and contexts without a human holding the
thread, targeting a structural failure rather than a capability one — a chat log is not
memory, a codebase records only what was kept, a task list rots.

The name is now explained rather than asserted, and the two halves are separated by
maturity, which is the honest thing to publish: **the record graph is established
practice** — an append-only causal log is a lab notebook under another name — while
**the state graph, and the cross-graph citation structure that falls out of it, is the
novel half and under active development.** Whether a single-writer distillation stays
small and honest as its evidence base grows without bound, and whether agents orient
better against it than against raw history, is the open question. README, SPEC,
AGENTS.md, the CLI docstring, the package description and the shipped agents-block all
carry it.

## Negative knowledge

An adoption run with its author in the room cannot find the defects that matter to
adopters, because the author answers around them. Three prior adoptions passed over a
config whose `node_id` disagreed with its own node file, a pull that the next command
deleted, and an HWM rule that silently leaves a wide DAG unreconciled. What surfaced
all three was a run where nobody could be asked — the agent had to follow the written
workflow literally and report where it broke. The test for a documented workflow is
someone executing it without its author available, and the report has to be audited
rather than believed: thirteen claimed defects, twelve real, one confidently wrong.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: c1cf3059e927f8d02366f4c7c2f7ce578a82d29b

## State Impact

- target: morning-crane-7863 — Second field adoption: neural-whoop, mode A, 189 legacy Flywheel nodes, run by an agent with no author available — the first adoption of either mode without its author in the room, and the first real exercise of the mode A path. It checks 0/0 with the archive verifiably untouched (root still revision 28), identity preserved verbatim across all 189 nodes, an honest frontier and 43 negative-knowledge entries. It found nine documentation defects, now fixed: step 4's ordering prose insisted --init precede the import and then described the outcome only the other order produces; `## State Impact` is refused in a body and must come from --impact, which itself prepends '- target: ' so a template line copied verbatim yields '- target: target: …'; state slugs are minted and cannot be chosen, so readable NEW <kebab-name> impact targets never resolve; advancing the HWM to the marker rather than the record tips left 111 nodes unreconciled on a wide DAG; step 8 never said to install the skills or to check they are committable; 'the prehistory bodies say so' names the one artifact mode A does not have; contract reconciliation is two writes, not one; the gate is `sync`, not `render`; and the survey printed only the signal categories that fired. A mode A walkthrough now documents the ordering that works and why it is not the numbered one, and the marker guidance says not to write state-graph counts it cannot yet know.
- target: wandering-sun-8831 — The I1 citation checker had a silent hole and is fixed. Claim units were 'bullets or paragraphs' — either, never both — so a `## Current` section containing any bullet had its prose paragraphs excluded from the citation check entirely; a checker that quietly stops checking is the wrong direction to fail in, and most state nodes mix the two. Units were also single lines, so a citation that wrapped onto a continuation read as missing, which produced 27 false warnings on one adopted repo and taught its agent to reflow correct prose. A unit is now a bullet with its continuations, or a paragraph, with headings, fenced code blocks and colon lead-ins to a bullet list excluded as structure. The fix immediately found 3 uncited claims in cadex and 8 in neural-whoop that both repos' passing check had never looked at.
- target: fond-sail-3288 — Status broken -> working: the AGENTS.md block overwrite is fixed and shipping in 0.0.8, so the destructive behaviour is no longer live for any adopter who upgrades. upgrade replaces a block only while its digest matches a template this project shipped, and otherwise reports it, leaves it, and names the shipped template to merge against; --agents-block opts into overwriting. The 0.0.8 template is registered in SHIPPED_BLOCK_DIGESTS, so an adopter whose block is untouched still gets the refresh automatically.
- target: empty-forest-6305 — Two storage-path defects found by the first mode A adoption run without its author, both fixed. `adopt --init` derived the config's root node_id from the slug unconditionally, but a mode A root arrives through `import --fork` which preserves the archive's node_id verbatim — so on neural-whoop the config claimed 8e92751d… while the node file said 51aabea1…, check does not compare the two, and push reads the config, which would have published the graph under an id nothing else in the repo used. It now reads the node's own id. Separately, `mirror pull` and `export` both defaulted to .hypergraph/cache/record.json, so the first export destroyed the legacy pull that step 7 still needs and that is the only record of what stayed on the archive; the pull now writes legacy-record.json and legacy-state.json.
- target: weathered-union-7494 — The project's stated goal changed, across README, SPEC, AGENTS.md, the CLI docstring, the package description and the shipped agents-block. It was 'a protocol for keeping research projects legible to fresh agents', which describes the mechanism rather than the goal; it is now a substrate for autonomous research and engineering — the memory layer an agent needs to carry work across months and contexts without a human holding the thread, aimed at a structural failure rather than a capability one. The name is explained rather than asserted: a claim answers to many pieces of evidence and a piece of evidence bears on many claims, so the citations join sets to sets across two graphs. And the two halves are now separated by maturity in public: the record graph is established practice, while the state graph and the cross-graph structure that falls out of it are the novel half and under active development, with whether the projection stays honest at scale named as the open research question.
