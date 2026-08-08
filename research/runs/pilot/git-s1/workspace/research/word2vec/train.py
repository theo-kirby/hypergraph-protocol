#!/usr/bin/env python3
"""Train word2vec skip-gram with negative sampling on text8 and evaluate on analogy task."""

import sys
import os
import time
import json
import numpy as np

# Add this directory to path for the Cython module
sys.path.insert(0, os.path.dirname(__file__))

from vocab import build_vocab, corpus_to_ids, build_subsample_prob, build_neg_table
from evaluate import evaluate_analogy, load_vectors


def main():
    # ---- Hyperparameters ----
    dim = 100
    window = 5
    neg_samples = 5
    epochs = 5
    subsample_thresh = 1e-4
    alpha_start = 0.025
    alpha_end = 0.00025
    min_count = 5
    seed = 1

    data_dir = os.path.expanduser("~/research")
    artifacts_dir = os.path.join(data_dir, "artifacts")
    text8_path = os.path.join(data_dir, "text8")
    questions_path = os.path.join(data_dir, "questions-words.txt")
    vectors_path = os.path.join(artifacts_dir, "vectors.txt")
    results_path = os.path.join(artifacts_dir, "results.json")

    print("=" * 60)
    print("Word2Vec Skip-Gram with Negative Sampling")
    print(f"  dim={dim}, window={window}, neg={neg_samples}, epochs={epochs}")
    print(f"  lr: {alpha_start} -> {alpha_end}")
    print(f"  subsample: {subsample_thresh}, min_count={min_count}, seed={seed}")
    print("=" * 60)

    # 1. Build vocabulary
    word2id, id2word, counts, vocab_size = build_vocab(text8_path, min_count=min_count)
    print(f"Vocabulary size: {vocab_size}")

    # 2. Convert corpus to IDs
    data = corpus_to_ids(text8_path, word2id)
    print(f"Corpus tokens: {len(data)}")

    # 3. Build subsampling probabilities
    subsample_prob = build_subsample_prob(counts, subsample_thresh)

    # 4. Build negative sampling table
    negtable = build_neg_table(counts, table_size=100_000_000)

    # 5. Train
    print("\nImporting Cython training module...")
    import w2v_core

    print("Starting training...")
    t0 = time.time()
    W_in, W_out = w2v_core.train(
        data,
        vocab_size=vocab_size,
        dim=dim,
        window=window,
        neg_samples=neg_samples,
        epochs=epochs,
        alpha_start=alpha_start,
        alpha_end=alpha_end,
        seed=seed,
        negtable=negtable,
        subsample_prob=subsample_prob,
    )
    training_time = time.time() - t0
    print(f"Training completed in {training_time:.1f}s ({training_time/60:.1f} min)")

    # Use W_in (input vectors) as the final word vectors (standard practice)
    vectors = W_in.copy()

    # 6. Save vectors
    print(f"Saving vectors to {vectors_path}...")
    with open(vectors_path, "w") as f:
        f.write(f"{vocab_size} {dim}\n")
        for i, word in enumerate(id2word):
            vec = vectors[i]
            vec_str = " ".join(f"{x:.6f}" for x in vec)
            f.write(f"{word} {vec_str}\n")
    print("Vectors saved.")

    # 7. Evaluate
    print("\nEvaluating on analogy task...")
    word2id_eval, vectors_eval = load_vectors(vectors_path)
    total_acc, sem_acc, syn_acc, total_q, skipped, sem_total, syn_total = evaluate_analogy(
        vectors_eval, word2id_eval, questions_path
    )

    # 8. Save results
    results = {
        "total_accuracy": float(total_acc),
        "semantic_accuracy": float(sem_acc),
        "syntactic_accuracy": float(syn_acc),
        "total_questions": int(total_q),
        "skipped": int(skipped),
        "semantic_total": int(sem_total),
        "syntactic_total": int(syn_total),
        "hyperparameters": {
            "dimension": dim,
            "window": window,
            "negative_samples": neg_samples,
            "epochs": epochs,
            "subsampling_threshold": subsample_thresh,
            "learning_rate_start": alpha_start,
            "learning_rate_end": alpha_end,
            "min_count": min_count,
            "seed": seed,
        },
        "training_time_seconds": float(training_time),
    }

    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_path}")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()