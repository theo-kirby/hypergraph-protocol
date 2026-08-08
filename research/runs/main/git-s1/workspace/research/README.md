# Word2Vec Skip-Gram with Negative Sampling

A CPU-optimized word2vec implementation in Cython, trained on the text8 corpus.
Evaluated on the Google word analogy task.

## Best Result

| Metric | Value |
|--------|-------|
| Total accuracy | **22.03%** (2051/9310) |
| Semantic accuracy | **41.19%** (173/420) |
| Syntactic accuracy | **21.12%** (1878/8890) |
| Training time | 27.7 min (5 epochs, 4 vCPU) |

## Configuration

- dim=200, window=5, negative samples=15
- subsampling threshold=1e-5, initial lr=0.025 (linear decay)
- min_count=5, seed=42
- Corpus: text8 (17M tokens), Vocab: 71,290 words

## Quick Start

```bash
python3 -m venv venv && source venv/bin/activate
pip install cython numpy setuptools
python setup.py build_ext --inplace
python train.py
```

Results appear in `artifacts/results.json` and `artifacts/vectors.txt`.

## Repository Structure

- `word2vec/` — library: vocabulary building, Cython training loop, evaluation
- `train.py` — main training script
- `full_train.py` — training with NaN monitoring (reproducible baseline)
- `artifacts/` — metrics and output files for each run
- `data/` — text8 corpus and analogy questions
- `NOTES.md` — research log
- `DECISIONS.md` — design decisions
- `DEAD-ENDS.md` — failed approaches