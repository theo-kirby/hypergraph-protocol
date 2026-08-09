---
name: hypergraph-adopt
description: Bring a project with a past under the Hypergraph protocol - import an existing hosted graph as legacy history (mode A) or author honest prehistory from the repo itself (mode B), draw the adoption epoch, distill a real state graph, and install the AGENTS.md onboarding. Use hypergraph-init only for day-zero projects.
---

# Hypergraph Adopt

Conversion path for a repo **without** `.hypergraph/config.yml` that already has a
history: an existing hosted graph, a mature codebase, or both. Protocol:
[spec.md](references/spec.md) — especially *Adoption epochs*. Day-zero projects use
hypergraph-init instead; everything init does, this skill does *plus* the past.

## The CLI

Invocations below write `hypergraph …`. In a dev checkout of the protocol repo that is
`uv run tools/hypergraph.py …`; an adopter gets the bare `hypergraph` from
`uv tool install hypergraph-protocol`. Same tool, same flags — pick whichever resolves.

## Modes

- **Mode A — a legacy graph exists** on a hosted store: import it verbatim as the
  fork; the original graph is never modified and remains the archive.
- **Mode B — no graph**: author 1–3 "Prehistory" record nodes distilled from the repo
  itself. Honest summary, never event-by-event reconstruction.

The adopted project's graphs are node files committed in its repo, exactly as for a
day-zero project. Nothing to decide.

## Workflow

1. **Inventory.** Detect the mode; read the repo (README, docs, experiment logs,
   git shape). Mode A: resolve **all** graph anchors — the root(s) *plus any index
   nodes the repo's docs declare as anchors* (docs saying "node X is the system of
   record" make X an anchor even if it isn't the root). Then pull them in one call:
   ```
   hypergraph mirror pull --record-node-id <id> [--record-node-id <id>…] \
       [--state-node-id <id>] --out-dir .hypergraph/cache
   ```
   It writes `record.json` / `state.json` ready for step 2, prints a draft `archive:`
   block on stderr, and errors if a node is reachable from both graphs' anchors.
   Confirm the node count covers what the docs cite before proceeding.
2. **Bring in the history.**
   - **Mode A**: `hypergraph import --record <export> [--state <export>] --fork` —
     node_ids and slugs are preserved verbatim; this *is* the fork (the host has no
     native one — slugs are minted on create and immutable). **`--fork` is mandatory
     here**: it files the archive's ids under `origin:` as provenance, so the repo
     becomes the continuing graph and owns its whole history. Config must
     gain a mandatory `archive:` block naming the legacy roots, each with a `title` —
     **artifacts do not survive import** (node files have no artifact op), so
     the archive reference is the only pointer to them. For graphs above ~1000 nodes,
     offer
     **epoch-split**: import only the recent epoch and leave older history on the
     archive (never truncate — the archive keeps everything); it is also how you
     mirror less history when a full push would be thousands of creates.
   - **Mode B**: author the prehistory record node(s) from README/docs/CHANGELOG/git
     shape (`hypergraph new record` after the record root exists; they may parent on
     the root). Each covers a real era or workstream with `## State Impact` lines
     feeding step 4's distillation.
3. **Epoch marker.** One decision record node titled "Adopted Hypergraph"
   documenting the conversion (what was imported/authored, from where, what stayed
   on the archive). Parentage (SPEC: Adoption epochs): full-import mode A → parent =
   the **newest legacy node**; mode B → parent = the **newest prehistory node**
   (they resolve locally, and the CLI refuses a second parentless root per graph);
   epoch-split only → the marker becomes the record **root** of the local graph
   (`--root`, no other root exists locally) and records the archive lineage in its
   content, since local files cannot parent on slugs that don't resolve locally.
   Write `epoch: {marker: <slug>}` to the config so `check` exempts strictly-older
   nodes from I2.
4. **Distillation → state graph.** The state skeleton must reflect what is *actually
   known*, not an empty template:
   - Architecture components from the repo + graph (3–8 nodes, init granularity).
   - **Per-branch mining**: walk the legacy graph / repo docs for current-status
     claims, key decisions, and dead ends. If the graph exceeds one context window,
     fan out subagent readers per branch and merge their briefs.
   - **Id-prefix→slug resolution**: docs citing raw node-id prefixes (e.g.
     `b3ea0b95`) are mapped to slugs via the export before writing provenance —
     never cite a prefix.
   - Dead ends land as **negative knowledge** with real evidence slugs (legacy slugs
     are valid — they resolve in the imported record graph; in mode B cite the
     prehistory/marker nodes).
   - Statuses honest: a claim the docs contradict is `broken`, unverified is `open`,
     don't default everything to `working`.
   - **Interview the user** for invisible dead ends: "what did you try that didn't
     work and would waste a fresh agent's day?" — the graph can't tell you.
   - Every claim cites resolvable slugs (legacy or marker). `check` enforces this.
5. **Init tail** (init steps 5–8): advance the HWM to the marker; write
   `.hypergraph/config.yml` from [config.example.yml](references/config.example.yml)
   (`graph_dir`, `epoch:`, and `archive:` in mode A); gitignore `.hypergraph/cache/`;
   `hypergraph export` → `render` → `check` **exit 0**; commit.

6. **Onboarding install.**
   - Append [agents-block.md](references/agents-block.md) to the repo's `AGENTS.md`
     (create the file if absent) — idempotently: if `<!-- hypergraph:begin -->` is
     already present, replace the existing block instead of appending a second one.
   - **Contract reconciliation**: when the existing AGENTS.md prescribes a
     conflicting discipline (e.g. "commit findings as <other system> nodes"), amend
     those sections to route through hypergraph — never leave two contradictory
     contracts standing.
   - **Never break a CLAUDE.md→AGENTS.md symlink**: check with `ls -la` / `readlink`
     first and edit the symlink's *target*, not the symlink.
   - Write `.hypergraph/AGENTS.md`: the full onboarding — the four non-negotiables
     expanded, this project's graph roots and epoch, where the archive lives (mode
     A), the skills to use, and the check command verbatim.

## Guardrails

- The legacy graph is read-only throughout — the fork is the import; the archive is
  frozen. Never write, tag, or re-parent archive nodes.
- Record nodes at/after the marker follow full I2 discipline immediately — the epoch
  exempts only strictly-older history, and authoring is never exempted.
- Distilled claims must be derivable from cited nodes/docs (SPEC I8); when the
  source is ambiguous, say so in the claim rather than rounding up to certainty.
- Don't inflate the state graph: 3–8 components with honest statuses beat 20 nodes
  of aspiration. Negative knowledge is the highest-value cargo — mine for it.
- Mode A needs read access to the legacy graph. If `mirror pull` cannot reach it,
  authenticate first (`hypergraph mirror doctor` says what is wrong) — do not fall
  back to a repo-docs-only adoption of a graph-bearing project, which silently
  discards its memory.
