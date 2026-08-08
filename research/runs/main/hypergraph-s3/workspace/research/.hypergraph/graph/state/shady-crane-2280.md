---
node_id: 04fada21-fbe0-5978-92a4-95c4495be703
slug: shady-crane-2280
title: model training
created_at: '2026-08-08T21:03:16+00:00'
parents:
- cold-lodge-3139
summary: ''
---
Status: open

## Current
Baseline training complete with dim=100, window=5, negative=5, epochs=5 [rec: early-hollow-8934].
- Accuracy: 21.46% total (19.67% semantic, 22.74% syntactic)
- Vocab: 71,290 words, 9.4M tokens after subsampling
- Training time: 829.7s
- Results saved to artifacts/results.json, artifacts/vectors.txt

Room for improvement: the baseline result (21.5%) is below what better hyperparameters should achieve on text8. Further training runs with larger dim, more epochs, and more negative samples are planned.

## Intent
Model trained on text8 corpus with measurable accuracy.

## Negative knowledge
None yet.

## Provenance
- gentle-fjord-5359 — initial state skeleton
- early-hollow-8934 — baseline training result (21.5%)

## Reconciliation
- high_water_mark: early-hollow-8934
- reconciled_at: 2026-08-08T21:55:00+00:00
