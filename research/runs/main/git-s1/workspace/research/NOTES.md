# Research Log

## 2026-08-08 — Session 2: Reproduced and fixed baseline

**Status:** Baseline established with 22.03% total accuracy.

The previous session ended with NaN in all vectors (0% accuracy). On re-running
with the same code and freshly compiled Cython, the NaN did not reproduce.
The most likely cause: the previous run used a stale `.so` file (timestamps
show artifacts were written at 21:39, while the `.so` compiled at 21:56).

**Full training (5 epochs, full corpus):**
- dim=200, window=5, neg=15, subsample=1e-5, lr=0.025 (linear decay to 0.005)
- Total: 22.03% (2051/9310), Semantic: 41.19% (173/420), Syntactic: 21.12% (1878/8890)
- 10,234 questions skipped (OOV words)
- Training time: 1660.8s (27.7 min) on 4 vCPU
- Max vector magnitude remained <2.0 throughout training — no divergence

**Key observations:**
1. W_out initialized to zeros works but is unusual — W_in doesn't change until
   W_out grows. Original word2vec initializes both randomly.
2. Semantic accuracy (41.2%) is much higher than syntactic (21.1%), which is
   typical for skip-gram on text8.
3. 10,234/19,544 (52%) questions skipped due to OOV — the text8 vocabulary
   (first 100MB of Wikipedia) is limited.

**Next steps to investigate:**
- Initialize W_out randomly (match original word2vec more closely)
- Try different hyperparameters (window, dim, neg, subsample)
- Evaluate effect of training corpus size
- Try hierarchical softmax vs negative sampling

## 2026-08-08 — Session 1 (prior): Initial implementation

Built Cython skip-gram with negative sampling. First training run produced NaN
in all vectors (0% accuracy). Session ended before debugging. Evidence:
`artifacts/results.json` shows 0.0 accuracy, `artifacts/vectors.txt` is all NaN.
Training time was 1875s — longer than the successful run (1661s), which could
indicate the NaN appeared mid-training and the computation was already corrupted.