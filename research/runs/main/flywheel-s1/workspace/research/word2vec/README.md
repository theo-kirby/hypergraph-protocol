# word2vec-skipgram-text8

Skip-gram with negative sampling (Mikolov et al. 2013) implemented from scratch
in C (training loop) with Python driver, trained on text8, evaluated on Google
word analogy task.

## Results

| Run | Dim | Window | Neg | Epochs | Accuracy | Training Time |
|-----|-----|--------|-----|--------|----------|---------------|
| baseline | 100 | 5 | 5 | 15 | **21.51%** | 46.6 min |

### Per-category breakdown

| Category | Accuracy |
|----------|----------|
| **Total** | **21.51%** |
| Semantic | 32.14% |
| Syntactic | 21.01% |
| family | 82.62% |
| gram6-nationality-adjective | 60.51% |
| gram3-comparative | 50.63% |
| gram9-plural-verbs | 34.09% |
| capital-common-countries | 31.03% |
| gram8-plural | 29.70% |
| capital-world | 20.10% |
| gram7-past-tense | 18.04% |
| gram2-opposite | 13.82% |
| gram5-present-participle | 13.41% |
| city-in-state | 13.28% |
| gram4-superlative | 12.50% |
| gram1-adjective-to-adverb | 9.62% |
| currency | 3.81% |

Full metrics in `artifacts/results.json`.

## Reproducibility

Seed 42, Python 3.12, numpy. Full configuration in `artifacts/results.json`.

## Flywheel

Experiment record: node `red-bush-4406` (public) with training artifacts.