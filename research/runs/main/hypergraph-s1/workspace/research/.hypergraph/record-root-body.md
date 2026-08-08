## What

Root node for the word2vec-cpu record graph. This graph is an append-only log of every unit of work: experiments, decisions, dead ends, and findings. Nodes are immutable; corrections are new child nodes, never edits.

## Why

The Hypergraph protocol (SPEC.md) requires one parentless record root per project. All record nodes descend causally from this root.

## Method

Created via `hypergraph new record --root` during project initialization.

## Result

Record graph established. All future work will be recorded as descendants of this node.

## Repo

- repo: https://github.com/boxwheel/word2vec-cpu
- branch: main
- commit: TBD (pre-init)