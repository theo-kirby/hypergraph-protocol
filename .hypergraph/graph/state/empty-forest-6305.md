---
node_id: be944979-3508-5583-b6b8-bd96106ca7f5
slug: empty-forest-6305
title: Flywheel mirror
created_at: '2026-08-07T10:57:13.256136+00:00'
parents:
- cool-king-8586
summary: 'The optional one-way projection: push executes it behind one command, carries bodies, tags, artifacts and parent edges, degrades to exit 0; networked half in its own lazily-loaded module since 0.0.11, verified live end to end.'
flywheel:
  node_id: be944979-3508-5583-b6b8-bd96106ca7f5
  slug: empty-forest-6305
  revision: 16
  pushed_at: '2026-08-16T18:35:51+00:00'
  content_sha256: 6cff105348580f105f9ae400b42c5cd30c1abcb22d15d84d67d91a9e205d649f
  parents_sha256: a7a7d736bcfc7a886dc3bd4b6b138fcbabbc3a0bb49408b1c19e0413f4420ad9
  parents:
  - 9e687be1-1c80-56a2-bc0c-d4476edc0a2e
---
Status: working

## Current

An optional, one-way projection of the committed node files onto a hosted graph. The repo stays canonical; nothing here is ever read back as truth [rec: old-dawn-8747] [rec: silver-ember-3035].

- **`push` executes the mirror rather than describing it.** It was a plan an agent carried out call by call; it is now transport (the `flywheel` CLI, with REST over `urllib` as an explicit fallback), a crash journal, a pacer, legend, lineage and verify behind one command, with `--plan` staying network-free for machines without the binary [rec: silver-ember-3035]. `sync` (export → render → check → push) is the only new verb an agent learns, and it says nothing about any hosted service.
- **The networked half is its own module since 0.0.11** [rec: blue-rain-3979]. Everything that resolves a credential, looks for a binary or opens a socket lives in `tools/hypergraph_mirror.py` (installed as `hypergraph_protocol_mirror.py`), loaded lazily through core's `_mirror()` with shared class identity, so `except LocalGraphError` still catches every `MirrorError`. The offline bookkeeping — `push --plan`, `--verify --against`, `--record-result`, legend and lineage — stays in core, and the old behavioral guarantee (no offline command resolves a transport) is now structural: a subprocess test proves offline commands never import the module at all.
- **A project with no mirror exits 0 as a no-op, never 2** — and that now covers *who* is running, not only whether a mirror is configured. A fork inherits the committed `mirror:` key and holds no credentials for it, so reconcile's unconditional publish step used to exit 2 on every outside contributor's machine. `publish_branch_block()` and `mirror_not_ours()` feed one `stand_down()`: print a line, exit 0, unless `--require-mirror`. Outside a git checkout the guard allows [rec: silver-ember-3035] [rec: placid-ridge-4035].
- **The dirty-tree guard was deliberately not built** despite being scoped alongside the branch guard: reconcile publishes *before* it commits, on purpose, so `push`'s frontmatter writes land in the same `git add`, which makes a dirty graph the expected state at push time. `heal` does guard on one, and that is not a reversal — it sits in no commit flow [rec: placid-ridge-4035] [rec: clear-moss-4527].
- **Behaviours that lived in prose became code, each closing its trap** [rec: silver-ember-3035]: null-parent substitution raises rather than guesses; a null `base_revision` is read live rather than defaulted; legend lookup pages past 500 children; verify mechanically refuses an archive id and treats truncation at `max_nodes` as a violation rather than as drift. **Degradation is tested, not assumed**: with no binary and no environment `push` exits 2 naming both remedies, while every offline command still exits 0 — and a test asserts none of them so much as calls `shutil.which`.
- **One typed comparison sits under everything that diffs two graphs** [rec: clear-moss-4527]. `Drift` / `GraphSide` / `diff_graphs` / `FIELD_COMPARATORS` mean `push_plan`, `verify_mirror` and every healer are downstream of one matcher instead of one loop each. Three rules the old loops never stated: a match key is **declared, never inferred** — a content hash is not a key, since two record nodes can legitimately share a body; an ambiguous key is **reported, never resolved**, with both sides excluded; and a `Drift` carries **both** values, so a caller reconstructs the wording it already had. `verify_mirror` was refactored onto it with byte-identical findings, the pre-refactor loop kept verbatim in the tests as the oracle.
- **The mirror carries tags**, reconciled against the live graph root **by name** and never by id, then assigned per node [rec: clear-moss-4527]. Four rules, each a bug if dropped: never compute the next root revision, because every creation bumps it; fold the bumped node revision back, because an assignment bumps it and verify calls revision skew drift; keep `tags_sha256` a *sibling* of `content_sha256` rather than folding it in; and report colour/flag drift rather than issuing an update, because deleting a definition un-tags every node that used it. **Three live-host behaviours broke it first and none was findable by reading** [rec: early-mesa-8507]: `tags:create` returns the graph *root node* rather than the tag; a `cluster:*` tag must cover a connected set of nodes, checked on every assignment, so order is part of the contract; and creating a tag bumps the committed revision of every node in the graph — 22 creations moved all 196.
- **The mirror carries artifacts, and the rules are the tag rules with one inversion removed** [rec: shady-bay-7654]. Identity is the **title** — `<repo-relative path>@<sha256[:12]>` — so "this title is attached" means exactly "these bytes, for this path, are attached", and the `artifacts:list` that supplies `expected_revision` is the same read that supplies the dedupe set. **Retry is safe for an atomic replace and unsafe for an append**: `tags:assign` may be re-issued, an upload may not, and even a 429 is ambiguous there because the upload is one process doing prepare + PUT + finalize. **Nothing is ever un-attached**, since the only un-attach destroys bytes — so changed bytes upload a new version, a dropped path leaves the mirror copy in place, and a broken item fails alone with the node's stamp withheld.
- **The mirror moves parent edges too, and that was a silent hole until this round** [rec: autumn-glade-5802]. An `update` op fires only when `content_sha256` moves and carries no parents, so a pure re-parent produced no mirror op at all and forked local topology from mirror topology forever, with `parents` sitting in the strict-only verify field set where nothing would notice. `push_parents` executes `nodes:add-parent` / `nodes:remove-parent` add-before-remove with all four optimistic locks, and `parents` is now a **default** verify field. What the mirror currently holds comes from an export and never from `nodes:get`, which reports `has_parents` and no parent ids at any projection — which is what made the first run a stamp rather than a write: 87 parent sets planned, 0 edges written.
- **Two costs are recorded rather than left to be discovered** [rec: shady-bay-7654]. "The mirror is a regenerable, one-way projection" now has a bounded exception — a node body is regenerable from the repo forever, but an artifact's bytes only while that file exists at that path, and gitignored evidence is permitted by design. And `push_plan` stopped being a pure function of `graph_dir`: it stats and hashes files across the repo, so its cost is proportional to evidence size. Its network-free guarantee survives untouched.
- **Verified live end to end throughout** [rec: silver-ember-3035] [rec: shady-bay-7654]: `mirror doctor` 0/0 with a write probe and an account match, a real push creating nodes parents-first and verifying 0 drift, a second run reporting `0 create(s), 0 update(s)` while making **zero calls** — the plan is a pure diff, so a synced graph asks the host nothing — an artifact title returning byte-identical with `metadata.hypergraph` intact, and `push --verify --strict` clean.
- An earlier conclusion that the mirror had been deleted was wrong and is corrected: every probe behind it used a key belonging to an unrelated account. That account id is now `mirror_account_id:` in config, so the check is mechanical [rec: sweet-aspen-3667] [rec: solemn-dawn-6752] [rec: silver-ember-3035].

## Negative knowledge

- [scope: mirroring a local graph to a hosted store | confidence: high | evidence: old-dawn-8747, kind-valley-8040] the host mints its own slug on create, so nodes authored locally after the switch live there under a different slug while the markdown still cites the local one — `check` against a mirror export reported 25 dangling-pointer violations (I4/I5/I7) on a graph that checks 0/0 from the node files. The mirror is a readable projection, never the thing you check.
- [scope: deferring slug translation on push | confidence: medium | evidence: kind-valley-8040] translation would make the mirror non-identical to source, breaking the byte-identical `content_sha256` change detector and forcing two-way translation on every update; the cost of *not* translating is measured (above) rather than assumed. Still deferred [rec: silver-ember-3035].
- [scope: parsing a hosted graph export | confidence: high | evidence: steep-cell-5173] the export encodes edges as incoming_ids/outgoing_ids, not parent_ids — a parser reading only parent_ids sees every node as a root.
- [scope: verifying an adopted project's mirror | confidence: high | evidence: copper-moss-3669, northern-willow-0469 | decision: copper-moss-3669] `push --verify` proves nothing when the archive roots are spliced into the export it is given: the imported nodes' archive-owned ids resolve through the archive subgraph, so a mirror holding 3 record nodes of 111 exits 0. The export must cover the project's own `mirror_roots` alone.
- [scope: idempotency for writes to a service reached through a CLI | confidence: high | evidence: silver-ember-3035] duplicate mirror nodes are the only unrecoverable failure in this path, and shelling out to a CLI means no `Idempotency-Key` header can be injected — so idempotency has to be owned locally. An intent fsynced *before* each request, resolved on the next run **by looking** (page the intended parent's children, match title + body sha256), is the whole mechanism. Blind retry is never an option: a create whose outcome is ambiguous must be inspected, not repeated.
- [scope: untyped success responses from mutating endpoints | confidence: high | evidence: silver-ember-3035] every mutating endpoint's documented success schema in the live OpenAPI is literally `{}`, so no response field may be assumed. In particular **never default a missing `revision` to 0**: `revision: 0` is a real value — this repo's own mirror record root sits at 0 — and a wrongly-defaulted 0 makes every subsequent update conflict forever. Probe the shape and fail loudly.
- [scope: paging a children endpoint before matching on a singleton | confidence: high | evidence: silver-ember-3035] the legend node is located among the record root's children by exact title. Without a cursor loop, a root with more than one page of children silently fails to find the existing one and creates a second — on every push. A lookup that decides whether to create is a duplicate generator if it can return a false negative.
- [scope: executing mirror pushes by hand instead of from plan bytes | confidence: high | evidence: careful-harbor-3902] `push --plan` cannot detect manual-push byte deviations — frontmatter shas are stamped from local bytes, so a hand-transcribed mirror write that drifts (lost newline, dropped blank line) looks clean to the planner; only `push --verify` against a fresh export catches it. Largely retired now that the CLI pushes plan bytes itself.
- [scope: exempting a store's own structure from a drift check | confidence: high | evidence: autumn-glade-5802] "exempt the configured roots" and "exempt the roots with no local counterpart" are the same rule only for an adopted project. A re-homed one mirrors into the very roots its node files declare, so exempting by id refuses to detach a node from the graph root and leaves it double-parented forever. The live canary landed in exactly that state and the drift check is what reported it.

## Provenance

- old-dawn-8747 — the adapter and this repo's migration onto it
- kind-valley-8040 — first live mirror push; measured mirror-consistency limits
- steep-cell-5173 — live-export verification and the edge-encoding fix
- careful-harbor-3902 — verify and the slug legend close the projection-trust gap
- copper-moss-3669 — the archive-spliced verify diagnosed
- northern-willow-0469 — mirror-only verification proven live on a3go
- sweet-aspen-3667 — the mirror believed unreachable (superseded)
- solemn-dawn-6752 — the correction: wrong account, not a missing mirror
- silver-ember-3035 — push becomes executing: transport, crash journal, pacer, doctor/roots/pull
- calm-sand-3399 — config schema migrated
- placid-ridge-4035 — publish-branch gate, not-the-owner stand-down, dirty-tree guard rejected
- long-peak-1620 — the REST transport proven in CI
- clear-moss-4527 — the graph comparison layer and the mirror's tag surface
- early-mesa-8507 — the live tag push: three host behaviours FakeTransport had not modelled
- shady-bay-7654 — the mirror's artifact surface and the append-vs-atomic-replace rule
- autumn-glade-5802 — the mirror moves parent edges, and verify sees topology by default
- late-sage-5549 — narrowed to the mirror once storage moved to Storage & node format
- blue-rain-3979 — the split: the mirror's networked half becomes its own lazily-loaded module
- vast-birch-5192 — Operator directive: the release label is 0.0.11, not 0.9.0
