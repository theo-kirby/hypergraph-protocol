---
node_id: a0534824-61a1-5c1a-ab04-f3f0c65e7421
slug: early-hollow-8934
title: 'Baseline training: dim=100, epochs=5'
created_at: '2026-08-08T22:04:38+00:00'
parents:
- rising-forest-8621
summary: ''
---
## What
Trained the skip-gram model on text8 with baseline hyperparameters: dim=100, window=5, negative=5, epochs=5, subsample=1e-4, lr 0.025→0.0001, min-count=5, seed=42. Evaluated on questions-words.txt analogy task.

## Why
This is the first training run — a baseline to measure against. These are the default parameters from train.py, chosen as a reasonable starting point based on the original Mikolov et al. 2013 settings (though theirs used dim=300, negative=15 on a much larger corpus).

## Method
- Command: `python train.py --dim 100 --window 5 --negative 5 --epochs 5 --subsample 1e-4 --lr-start 0.025 --lr-end 0.0001 --min-count 5 --seed 42`
- Corpus: text8 (100MB raw, ~17M tokens before subsampling)
- Vocab: 71,290 words after min-count=5 filtering
- Tokens after subsampling: 9,387,002
- Training time: 829.7s (~13.8 min) on 4 vCPU

## Result
| Section | Accuracy | Correct/Asked |
|---------|----------|---------------|
| capital-common-countries | 0.4170 | 211/506 |
| capital-world | 0.2043 | 297/1454 |
| currency | 0.1023 | 22/215 |
| city-in-state | 0.1365 | 23/168 |
| family | 0.3357 | 47/140 |
| gram1-adjective-to-adverb | 0.0867 | 64/738 |
| gram2-opposite | 0.0635 | 32/504 |
| gram3-comparative | 0.3213 | 411/1279 |
| gram4-superlative | 0.0968 | 109/1126 |
| gram5-present-participle | 0.1259 | 131/1040 |
| gram6-nationality-adjective | 0.5562 | 893/1605 |
| gram7-past-tense | 0.1679 | 224/1334 |
| gram8-plural | 0.2372 | 316/1332 |
| gram9-plural-verbs | 0.1747 | 152/870 |
| **Total** | **0.2146** | **3,827/17,827** |
| Semantic | 0.1967 | |
| Syntactic | 0.2274 | |

Skipped 1,717 questions (1,716 due to OOV, 1 due to zero query norm).

Analysis: 21.5% total accuracy is a working baseline but substantially below what better hyperparameters should achieve. Syntactic accuracy (22.7%) slightly exceeds semantic (19.7%). The model is learning — "nationality-adjective" at 55.6% and "capital-common-countries" at 41.7% are the strongest categories. "gram2-opposite" at 6.3% and "currency" at 10.2% are the weakest.

## Repo

- repo: none
- branch: main
- commit: f3091d48cb793680025b12746dfc7d455a955388

## State Impact

- target: shady-crane-2280 — Status: done. First training complete with 21.5% total accuracy
- target: wise-field-3424 — Status: done. Baseline analogy accuracy measured at 21.5% total
