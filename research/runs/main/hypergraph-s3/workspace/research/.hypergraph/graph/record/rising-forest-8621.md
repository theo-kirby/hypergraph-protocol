---
node_id: d9da107f-7d8c-5698-b49f-be5839cc8867
slug: rising-forest-8621
title: Skip-gram implementation in Cython
created_at: '2026-08-08T22:04:20+00:00'
parents:
- gentle-fjord-5359
summary: ''
---
## What
Implemented skip-gram with negative sampling (SGNS) from scratch in Cython. Three modules:
- `word2vec/vocab.py`: Vocabulary builder with min_count filtering, subsampling, and unigram^(3/4) noise distribution
- `word2vec/skipgram.pyx`: Cython inner training loop with LCG random, dynamic window, linear LR decay, and negative sampling
- `word2vec/evaluate.py`: Word analogy evaluation on questions-words.txt using cosine similarity with exclusion of input words

Also created `train.py` as the main driver script and `setup.py` for Cython compilation.

## Why
The project requires a from-scratch implementation of the Mikolov et al. 2013 skip-gram model. Cython was chosen for the inner loop (4 vCPU, no GPU) to achieve reasonable training speed on the 100MB text8 corpus.

## Method
- Language: Python 3.12 + Cython 3.x
- Compilation: `python setup.py build_ext --inplace`
- Key design decisions:
  - LCG random number generator for both window sampling and noise table lookups (deterministic per seed)
  - Sigmoid gradient uses numerical stability: clamp dot to [-6, 6]
  - Init scale: 0.5/dim (random normal)
  - W_in (center embeddings) used as output vectors per standard practice
  - Dynamic window: uniform random [1, window] per center word
  - Linear learning rate decay over all token updates
  - Noise table of size 100M for O(1) negative sampling

## Result
Implementation compiles and runs correctly. Compiled shared object at `word2vec/skipgram.cpython-312-x86_64-linux-gnu.so` (~950KB). Ready for training.

## Repo

- repo: none
- branch: main
- commit: f3091d48cb793680025b12746dfc7d455a955388

## State Impact

- target: crisp-field-7816 — Status: done. Implementation is complete and compiled
