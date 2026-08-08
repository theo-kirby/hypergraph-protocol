---
node_id: 5a0b27b4-e73c-5396-accb-3680615950b7
slug: morning-delta-4057
title: Baseline evaluation results
created_at: '2026-08-08T22:02:43+00:00'
parents:
- peaceful-dusk-7235
summary: ''
---
Status: working

## Current
Baseline established by dusty-marsh-2661 [rec: dusty-marsh-2661]:
- Total accuracy: 32.43% (5,781 / 17,827) [rec: dusty-marsh-2661]
- Semantic accuracy: 32.90% (2,440 / 7,416) [rec: dusty-marsh-2661]
- Syntactic accuracy: 32.09% (3,341 / 10,411) [rec: dusty-marsh-2661]
- Hyperparameters: dim=200, window=5, neg=10, epochs=15, subsample_t=1e-5, lr=0.025 (linear decay), seed=42, threads=4 [rec: dusty-marsh-2661]
- Training time: 667.8s [rec: dusty-marsh-2661]

## Intent
Baseline word2vec evaluation results on text8 with the Google analogies task. Tracks the current best numbers and the hyperparameters that produced them.

## Negative knowledge
None yet.

## Provenance
- wandering-rain-8497 — initial project setup
- dusty-marsh-2661 — baseline run established these numbers
