# word2vec-cpu-baseline

A from-scratch word2vec skip-gram implementation with negative sampling in Cython, trained on text8 and evaluated on the Google analogy task. CPU-only (4 vCPU, 8 GB RAM).

## Best result so far

| Metric | Value |
|--------|-------|
| Overall analogy accuracy | **23.29%** (2168/9310) |
| Semantic (family) | 46.19% (194/420) |
| Syntactic | 22.20% (1974/8890) |
| Best single category | gram3-comparative: 54.05% |
| Training time | 36.5 min (5 epochs, text8) |

## Reproduce

```bash
cd ~/research
source venv/bin/activate
python build_vocab.py      # build vocab from artifacts/text8
python setup.py build_ext --inplace  # compile Cython
python main.py             # train + eval
```

Hyperparameters: dim=200, window=5, negative=15, epochs=5, subsample=1e-4, alpha=0.025, min_count=5, seed=42.

## Files

- `main.py` — pipeline: vocab → train → save vectors → evaluate
- `train.pyx` — Cython training loop (skip-gram with negative sampling)
- `build_vocab.py` — vocabulary builder with unigram noise table
- `evaluate.py` — Google analogy task evaluator
- `setup.py` — Cython build configuration