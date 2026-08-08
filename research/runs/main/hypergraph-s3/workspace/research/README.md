# word2vec-skipgram-text8

Skip-gram with negative sampling (Mikolov et al. 2013) implemented from scratch
in Cython, trained on text8, evaluated on Google word analogy task.

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install numpy cython
python setup.py build_ext --inplace
python train.py
```

## Results (latest)

| Run | Dim | Epochs | Neg | Accuracy |
|-----|-----|--------|-----|----------|
| baseline | 100 | 5 | 5 | 21.46% |

Per-section breakdown in `artifacts/results.json`.

## Structure

- `word2vec/skipgram.pyx` — Cython inner training loop
- `word2vec/vocab.py` — vocabulary builder
- `word2vec/evaluate.py` — analogy evaluation
- `train.py` — main driver
- `artifacts/` — vectors and metrics

## Reproducibility

Seed 42, Python 3.12, Cython 3.x, numpy. Full configuration in
`artifacts/results.json` under `hyperparameters`.