---
node_id: 27b5e379-8963-5a1f-ad51-c8ecdea567ae
slug: crisp-field-7816
title: skip-gram implementation
created_at: '2026-08-08T21:03:16+00:00'
parents:
- cold-lodge-3139
summary: ''
---
Status: superseded

## Current
Implementation complete: skip-gram with negative sampling in Cython. Three modules:
- `word2vec/vocab.py`: Vocabulary builder with min_count filtering, subsampling, and unigram^(3/4) noise distribution [rec: rising-forest-8621]
- `word2vec/skipgram.pyx`: Cython inner training loop with LCG random, dynamic window, linear LR decay, negative sampling [rec: rising-forest-8621]
- `word2vec/evaluate.py`: Word analogy evaluation on questions-words.txt [rec: rising-forest-8621]

Compiled with Cython. Working correctly.

## Intent
Skip-gram with negative sampling model is implemented and produces correct gradients.

## Negative knowledge
None yet.

## Provenance
- gentle-fjord-5359 — initial state skeleton
- rising-forest-8621 — implementation complete

## Reconciliation
- high_water_mark: early-hollow-8934
- reconciled_at: 2026-08-08T21:55:00+00:00
