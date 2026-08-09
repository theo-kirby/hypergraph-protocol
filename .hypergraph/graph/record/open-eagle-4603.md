---
node_id: 96d82dbf-5c06-50a0-a2e6-29aa84a0107b
slug: open-eagle-4603
title: upgrade keeps a block the adopter edited, by asking whether the bytes are still ours
created_at: '2026-08-09T18:16:19+00:00'
parents:
- vast-valley-5745
summary: 'Fixes the cadex defect: upgrade replaces an AGENTS.md block only while its digest matches a template this project shipped, otherwise it reports and steps back. --agents-block overwrites deliberately, mirroring --workflows. Needs no migration — the evidence is the block itself. Not yet released.'
flywheel:
  node_id: 9cd5a8d2-9512-56d9-af98-3643b7bbd3ab
  slug: rough-truth-2861
  revision: 0
  pushed_at: '2026-08-09T18:17:00+00:00'
  content_sha256: 2316b1c8aa1c2800a3ee0f11717a71414a0a64152ae2253a330365e9a1e97133
---
## What

`hypergraph upgrade` no longer overwrites an AGENTS.md block the adopter has
edited. It replaces the block only while that block is still, byte for byte,
something this project shipped; anything else is reported and left alone, with
the shipped template named so the adopter can merge by hand. `--agents-block`
overwrites deliberately, mirroring `--workflows`.

## Why

Fixes the defect `vast-valley-5745` found on cadex: adopt's step 8 writes
per-project content *inside* the sentinels, and upgrade treated the whole block
as ours. It deleted cadex's contract-reconciliation clause and its epoch note.

## Method

The obvious fix — a nested "preserve this" region inside the block — does not
work, and knowing why picked the design. On cadex the project-specific content
was not a separate section: the ADR-log clause is **woven into numbered item 2**,
a sentence inside a sentence of ours. No pair of markers separates that.

What is answerable is a different question: *did anyone edit this?* So
`SHIPPED_BLOCK_DIGESTS` holds the content digest of every agents-block this
project has ever shipped — both of them, recovered from git history as blobs
rather than retyped. A block whose digest is in the set is one we wrote and
nobody touched, so replacing it loses nothing. A block whose digest is not in the
set belongs to the adopter.

That choice has a property worth naming: it needs no migration and no new config
field. Every repo adopted before today is classified correctly on its first run,
because the evidence is the block itself.

Three details:

- `block_digest` hashes the **stripped** block. Files gain and lose a trailing
  newline as editors touch them; counting that as an edit would report every
  adopter as customized.
- `extract_agents_block` was split out of `replace_agents_block`, which could
  only answer "is there a block" by trying to replace it.
- The digest set is hand-maintained, so `test_shipped_block_digest_is_registered`
  is the tripwire: change the template without registering its digest and the
  test fails. Without it, the next template edit would make every adopter's
  untouched block look customized — the failure mode inverted, and silent again.

## Result

Five new tests in `tests/test_upgrade.py`; 316 passed, 1 skipped (was 311). The
existing fixture wrote a literal `OLD BLOCK`, which no release ever shipped —
under the new rule that is an edit, so the fixture now carries **0.0.6's real
block**, verbatim, and the pair of tests reads as the two real cases: an adopter
who never touched theirs gets it refreshed, an adopter who did gets it left
alone.

Verified against the repo that exposed it. `upgrade --dry-run` on cadex, whose
block carries both restored paragraphs:

```
  would refresh  .claude/skills/hypergraph-adopt
  …
  customized     AGENTS.md   (local edits inside the sentinels — pass
                              --agents-block to overwrite)
  unchanged      .hypergraph/config.yml   (hypergraph_version: 0.0.7)

upgrade: 5 item(s) would be refreshed to 0.0.7, 1 block(s) left alone
```

The five skill directories still refresh, which is right — they are wholesale
copies with no per-project content in them.

Docs: the adopt skill's step 8 now tells the agent to write the contract
amendment inside the sentinels and says it will survive; README states the block
gets the same protection as workflows.

**Not yet released.** The fix is in the tree. Every adopter runs 0.0.7 from PyPI,
where the destructive behaviour is live, so `fond-sail-3288` stays `broken` until
a release carries this. cadex's block therefore keeps a warning, now scoped to
"0.0.7 and earlier", which retires itself when the CLI there moves past it.

## Negative knowledge

Sentinel markers answer "where does our content go", never "who owns what is in
here". The moment a workflow instructs an agent to write project-specific prose
inside them — which adopt's contract reconciliation must, because the amendment
belongs in the sentence it qualifies — the region is shared, and a tool that
replaces it wholesale is destroying data by design. Ownership of shared prose is
not recoverable from position in the file; it is recoverable from whether the
bytes are still ours, which is a digest.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: d0c22ad09c379c83732098cf4e02b328f82cc557

## State Impact

- target: fond-sail-3288 — The overwrite defect is fixed in the tree: upgrade now replaces an AGENTS.md block only while its content digest matches one of the templates this project has shipped (SHIPPED_BLOCK_DIGESTS, both recovered from git history), and otherwise reports it as 'customized', leaves it untouched, and names the shipped template to merge against. --agents-block opts into overwriting, exactly as --workflows does. No migration and no new config field: every repo adopted before today classifies correctly on its first run, because the evidence is the block itself. Five new tests, including a tripwire that fails if the template changes without its digest being registered — without it the next template edit would make every untouched block look customized. Status stays broken: every adopter runs 0.0.7 from PyPI, where the destructive behaviour is live, so this is not true for anyone until a release carries it. New negative knowledge: sentinels answer where our content goes, never who owns what is inside them.
