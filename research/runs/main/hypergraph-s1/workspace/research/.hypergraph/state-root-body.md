# word2vec-cpu — project overview

CPU-only skip-gram word2vec with negative sampling, implemented from scratch (Cython + NumPy). Trained on text8, evaluated on the Google word analogy task.

Major components tracked as state nodes:
- `implementation`: Cython training loop correctness and performance
- `training-runs`: Hyperparameter sweeps and training outcomes
- `evaluation`: Analogy task metrics
- `publishing`: Git/GitHub state

## Reconciliation

high_water_mark: none
reconciled_at: null