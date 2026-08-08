# word2vec from scratch

A from-scratch implementation of skip-gram with negative sampling (Mikolov et al. 2013), trained on the `text8` corpus and evaluated on the Google word analogy task.

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate
pip install numpy
gcc -O3 -march=native -fPIC -shared -o word2vec_core.so word2vec_core.c -lm
python train.py
```

## Design

- **Core training loop in C** (`word2vec_core.c`), compiled to a shared library and called from Python via `ctypes`.
- Skip-gram with negative sampling (NEG), subsampling of frequent words, and linear learning rate decay.
- Vectors: input + output averaged as final embeddings.

## Files

- `word2vec_core.c` / `.so` — C training loop
- `train.py` — Python driver: vocabulary, subsampling table, negative table, evaluation, output
- `artifacts/vectors.txt` — final word vectors
- `artifacts/results.json` — accuracy metrics and hyperparameters

## Results (final: dim=200, window=8, neg=5, epochs=10)

| Category | Accuracy |
|----------|----------|
| **Total** | **31.43%** |
| Semantic | 33.28% |
| Syntactic | 30.11% |

- capital-common-countries: 69.17%
- gram6-nationality-adjective: 76.00%
- gram3-comparative: 47.00%
- capital-world: 36.62%

1717 questions skipped (OOV words). Training time: 17.6 min on 4 CPUs.

### Experiment log

| Run | dim | win | neg | eps | Total | Semantic | Syntactic | Time |
|-----|-----|-----|-----|-----|-------|----------|-----------|------|
| 1 | 100 | 5 | 5 | 5 | 22.70% | 19.78% | 24.77% | 4.3m |
| 2 | 200 | 5 | 5 | 5 | 23.17% | 19.81% | 25.56% | 6.2m |
| 3 | 200 | 5 | 5 | 10 | 30.06% | 30.19% | 29.97% | 12.0m |
| 4 | 200 | 8 | 5 | 10 | **31.43%** | **33.28%** | **30.11%** | 17.6m |

Key findings:
- More epochs (5→10) gave the biggest jump: +7pp accuracy
- Larger window (5→8) added another +1.4pp
- Wider vectors (100→200) alone helped only modestly (+0.5pp)
- The 30% gap vs the paper (~40-50%) is primarily due to corpus size (17M vs 100B words)