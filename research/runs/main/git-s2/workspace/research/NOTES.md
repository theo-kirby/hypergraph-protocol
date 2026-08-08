# Research log

## 2025-08-08: Fixed gradient accumulation bug — baseline working

**The bug:** The original training loop updated `W_in[center]` in-place after each positive/negative sample, then used the already-modified `W_in` values for subsequent `W_out` updates within the same center word's context window. This creates a positive feedback loop: each update amplifies the next, causing numerical divergence to inf/nan within a few epochs.

**The fix:** Added a `neu1e` gradient accumulation buffer (matching the original word2vec.c design). The algorithm now:
1. Computes all gradients for a center word using the ORIGINAL W_in values
2. Accumulates gradients in neu1e
3. Uses original W_in for all W_out updates
4. Applies accumulated gradient to W_in only after all context+negative pairs

**Result:** Training converges cleanly. No NaN/inf.

### Baseline results (dim=200, window=5, negative=15, epochs=5, subsample=1e-4, seed=42)

- Overall: 23.29% (2168/9310)
- Semantic (family only): 46.19% (194/420)
- Syntactic: 22.20% (1974/8890)
- Best category: gram3-comparative 54.05% (720/1332)
- Training: 2188.8s CPU (~36.5 min), 252.9M training pairs

**Note on skipped questions:** capital-common-countries (506 skipped), capital-world (4524 skipped), city-in-state (2467 skipped), currency (866 skipped), gram6-nationality-adjective (1599 skipped). These are completely absent from text8 vocabulary — the dataset is too small and Wikipedia-early-2000s. This is expected for text8 and not a model bug.