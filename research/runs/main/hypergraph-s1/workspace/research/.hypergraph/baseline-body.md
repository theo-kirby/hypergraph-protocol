## What

Built a complete skip-gram word2vec implementation with negative sampling from scratch: vocabulary builder, Cython-accelerated training loop, and analogy evaluation harness. Trained on text8 (dim=100, epochs=3) and evaluated on the Google word analogy task.

## Why

Establish a working baseline. The implementation uses no external NLP libraries (no Gensim) to keep full control over the training dynamics. Cython provides near-C speed on CPU. The text8 corpus and Google analogy task are standard benchmarks.

## Method

### Implementation
- `vocab.py`: Count-based vocabulary with min_count=5 filtering, unigram^(0.75) negative sampling table
- `word2vec_core.pyx`: Cython inner training loop — xorshift32 PRNG, fast sigmoid approximation, weight clipping at ±5.0, subsampling, dynamic window uniform [1, W], linear LR decay within each epoch
- `train_one_epoch.py`: Thin Python wrapper ensuring contiguous float32 arrays for Cython memoryviews
- `train.py`: Main script orchestrating vocab building, corpus conversion, weight init, multi-epoch training with chunk shuffling between epochs
- `evaluate.py`: Google analogy evaluation — cosine similarity with OOV handling, semantic/syntactic split

### Baseline Run
```
dim=100, window=5, neg_samples=5, subsample=1e-5, min_count=5
epochs=3, lr 0.025→0.0001 (linear decay per epoch), seed=42
corpus: text8 (100MB), 16.7M tokens kept, 71,290 word vocab
chunk shuffle between epochs (chunk_size=1000)
```

### Commands
```
python setup.py build_ext --inplace  # compile Cython
python train.py                       # train and save vectors
python evaluate.py                    # evaluate analogies
```

## Result

Training completed in 557.2s (9.3 minutes) on 4 vCPU / 8 GB RAM.

| Metric | Accuracy | Correct/Total | Skipped |
|--------|----------|---------------|---------|
| Total | 12.65% | 2,255 / 17,827 | 1,717 |
| Semantic | 8.25% | 612 / 7,416 | 1,453 |
| Syntactic | 15.78% | 1,643 / 10,411 | 264 |

Key observations:
- Syntactic accuracy (15.78%) is ~2× semantic (8.25%), consistent with the word2vec literature where syntactic relations are learned earlier
- High semantic skip rate (1,453/8,869 = 16.4%) due to OOV — many country/city names not in text8
- This is a baseline; more dims/epochs should improve substantially

## Repo

- repo: none (pre-publish)
- branch: N/A
- commit: N/A

