---
node_id: eca2eaa0-5208-5d86-8d59-0a34155f602b
slug: gentle-fjord-5359
title: 'word2vec from scratch: project initialization'
created_at: '2026-08-08T21:01:33+00:00'
parents: []
summary: ''
---
## What
Initialize the word2vec implementation project. Set up memory graphs and plan the approach.

## Why
This is the root node for the word2vec mission - implementing skip-gram with negative sampling from Mikolov et al. 2013 papers, training on text8, evaluating on the Google word analogy task.

## Method
- Language: Python 3.12 with Cython for the inner training loop
- Data: text8 corpus + questions-words.txt evaluation set
- Hypergraph local backend for record keeping

## Result
Project initialized. Approach: Cython-compiled skip-gram with negative sampling. Key decisions:
- Cython for inner loop performance (4 vCPU, no GPU)
- dim=100, window=5, negative=5, subsampling t=1e-4, epochs=5 as starting point
- Will adjust based on wall-clock timing

## Repo
Not yet published.

## State Impact

- target: NEW setup — project initialized, dependencies installed (numpy, cython, gcc)
- target: NEW implementation — skip-gram with negative sampling implementation needed
- target: NEW training — training on text8 needed
- target: NEW evaluation — analogy evaluation needed
