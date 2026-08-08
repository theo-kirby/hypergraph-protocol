---
node_id: 5d6e80ee-4cf5-5b21-8334-3a8f1c642ee0
slug: dusty-marsh-2661
title: 'Baseline: dim=200 window=5 neg=10 epochs=15 → 32.43% accuracy'
created_at: '2026-08-08T22:03:42+00:00'
parents:
- wandering-rain-8497
summary: ''
---
## What
Ran the word2vec skip-gram baseline on text8 using the C implementation (libtrain.so). The pipeline (train.py) was invoked with dim=200, window=5, negative=10, epochs=15, subsample_t=1e-5, lr=0.025, seed=42, 4 threads. The resulting vectors were evaluated on the Google word analogy task (questions-words.txt).

## Why
Establish a measured baseline against which all further improvements can be compared. This is the starting point for the research.

## Method
```
source ~/research/venv/bin/activate
cd ~/research
# Parameters in train.py main() were edited to: DIM=200, NEG_SAMPLES=10, EPOCHS=15
python train.py
```

The C library was pre-compiled with:
```
gcc -O3 -march=native -fopenmp -ffast-math -shared -fPIC -o libtrain.so train.c -lm
```

Corpus: text8 (100MB, first 100M bytes of English Wikipedia)
Evaluation: questions-words.txt (Google analogies, 19,544 questions across 14 categories)
Vocabulary: min_count=5, resulting in 71,290 words

## Result
| Metric | Value |
|--------|-------|
| Total accuracy | 32.43% (5,781 / 17,827) |
| Semantic accuracy | 32.90% (2,440 / 7,416) |
| Syntactic accuracy | 32.09% (3,341 / 10,411) |
| Skipped questions | 1,717 (OOV) |
| Training time | 667.8s (~11.1 min) |
| Vocabulary size | 71,290 |
| Effective corpus tokens | ~16.7M (after OOV filtering) |

Hyperparameters: dim=200, window=5, neg=10, epochs=15, subsample_t=1e-5, lr=0.025 (linear decay to 0.0001*lr), seed=42, threads=4.

## Repo

- repo: none
- branch: none
- commit: none

## State Impact

- target: morning-delta-4057 — baseline established: 32.43% total accuracy (32.90% semantic, 32.09% syntactic) on 17,827 analogy questions with dim=200, window=5, neg=10, epochs=15, training time 667.8s
