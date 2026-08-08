# Design decisions

## Cython implementation over pure Python
**Chosen:** Cython with typed memoryviews, no bounds checking, xorshift32 PRNG.
**Why:** Pure Python training loop would be ~50-100× slower. Need to process ~250M pairs. Cython gets ~115K pairs/s, completing 5 epochs in ~36 min.

## Gradient accumulation (neu1e) over in-place updates
**Chosen:** Accumulate W_in gradient in a separate buffer, apply after all context words processed.
**Rejected:** In-place update of W_in after each sample.
**Why:** The original word2vec.c uses neu1e accumulation. Our initial in-place approach caused numerical divergence because modified W_in values fed into subsequent W_out updates, creating amplification. The neu1e approach matches the reference implementation and is numerically stable.

## Single-threaded training
**Chosen:** Single thread.
**Why:** The hogwild-style parallelism in original word2vec improves throughput on many-core machines but introduces non-determinism. On our 4-vCPU box, the benefit is marginal and the complexity of lock-free concurrent updates isn't worth it for a baseline. Multi-threading can be added later as an experiment.

## text8 dataset
**Chosen:** text8 (first 100MB of English Wikipedia, cleaned).
**Why:** Standard benchmark, fast to iterate on. Many named-entity categories (capitals, cities, currencies) are completely absent, which is a known limitation.

## W_in + W_out for final vectors
**Chosen:** sum of input and output embedding matrices.
**Why:** Common practice in word2vec literature. Input vectors capture word-as-center behavior, output vectors capture word-as-context behavior. Summing gives better analogy performance than using either alone.

## seed=42
**Chosen:** Fixed seed.
**Why:** Reproducibility over variance analysis. We can sweep seeds later if needed.