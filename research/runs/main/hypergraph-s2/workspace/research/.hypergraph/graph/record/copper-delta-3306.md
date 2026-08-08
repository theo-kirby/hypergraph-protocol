---
node_id: 4353d677-93dc-5384-989d-79365418d2a1
slug: copper-delta-3306
title: Repository published to GitHub
created_at: '2026-08-08T22:09:09+00:00'
parents:
- dusty-marsh-2661
summary: ''
---
## What
Published the word2vec research repository to GitHub at https://github.com/boxwheel/word2vec-skipgram-text8. The repo contains the C training implementation, Python pipeline, baseline results (results.json), hypergraph memory graph, and STATE.md.

## Why
Required by the operating manual: work must be published continuously so it survives the ephemeral box.

## Method
Used git with .gitignore excluding large binaries (vectors.txt, text8, libtrain.so, venv/). Pushed to GitHub via `git push --force`.

## Result
Repository is live at https://github.com/boxwheel/word2vec-skipgram-text8 with the initial commit containing all source code, hypergraph files, and baseline results.

## Repo

- repo: none
- branch: main
- commit: d19403fd9a1a1c68b9c05a1876da37da6f917ce3

## State Impact

- target: quiet-path-5233 — repo published at https://github.com/boxwheel/word2vec-skipgram-text8
