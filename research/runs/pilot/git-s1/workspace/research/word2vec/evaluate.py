"""Word analogy evaluation for word2vec vectors."""

import numpy as np
import json


def load_vectors(path):
    """Load vectors from word2vec text format. Returns (word2id, vectors)."""
    word2id = {}
    vectors = []
    with open(path, "r") as f:
        vocab_size, dim = map(int, f.readline().split())
        for i, line in enumerate(f):
            parts = line.strip().split()
            word = parts[0]
            vec = np.array([float(x) for x in parts[1:]], dtype=np.float32)
            word2id[word] = i
            vectors.append(vec)
    vectors = np.array(vectors, dtype=np.float32)
    # Normalize
    vectors = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12)
    return word2id, vectors


def evaluate_analogy(vectors, word2id, questions_path):
    """
    Evaluate word analogy task.

    Returns
    -------
    total_acc : float
    semantic_acc : float
    syntactic_acc : float
    total : int total questions attempted
    skipped : int questions skipped
    semantic_total : int semantic questions attempted
    syntactic_total : int syntactic questions attempted
    """
    with open(questions_path, "r") as f:
        lines = f.readlines()

    section = None
    semantic_correct = 0
    semantic_total = 0
    syntactic_correct = 0
    syntactic_total = 0
    skipped = 0

    # Pre-compute all normalized vectors once
    dim = vectors.shape[1]
    all_norms = np.linalg.norm(vectors, axis=1)
    all_vectors_normed = vectors / (all_norms[:, np.newaxis] + 1e-12)
    id2word = {v: k for k, v in word2id.items()}

    semantic_sections = {
        "capital-common-countries",
        "capital-world",
        "currency",
        "city-in-state",
        "family",
    }
    # Everything else is syntactic

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(":"):
            section = line[1:].strip().lower()
            continue

        parts = line.split()
        if len(parts) != 4:
            continue

        a, b, c, d_expected = parts
        # Skip questions containing OOV words
        if a not in word2id or b not in word2id or c not in word2id or d_expected not in word2id:
            skipped += 1
            continue

        idx_a = word2id[a]
        idx_b = word2id[b]
        idx_c = word2id[c]

        # Compute analogy vector: vec(b) - vec(a) + vec(c)
        query = (all_vectors_normed[idx_b] - all_vectors_normed[idx_a]
                 + all_vectors_normed[idx_c])
        query = query / (np.linalg.norm(query) + 1e-12)

        # Cosine similarity with all words
        scores = np.dot(all_vectors_normed, query)

        # Exclude a, b, c
        scores[idx_a] = -np.inf
        scores[idx_b] = -np.inf
        scores[idx_c] = -np.inf

        best_idx = np.argmax(scores)
        best_word = id2word[best_idx]

        is_correct = (best_word == d_expected)

        # Determine if semantic or syntactic
        if section in semantic_sections:
            semantic_total += 1
            if is_correct:
                semantic_correct += 1
        else:
            syntactic_total += 1
            if is_correct:
                syntactic_correct += 1

    total_correct = semantic_correct + syntactic_correct
    total_questions = semantic_total + syntactic_total

    total_acc = total_correct / total_questions if total_questions > 0 else 0.0
    semantic_acc = semantic_correct / semantic_total if semantic_total > 0 else 0.0
    syntactic_acc = syntactic_correct / syntactic_total if syntactic_total > 0 else 0.0

    print(f"Evaluation results:")
    print(f"  Total:        {total_correct}/{total_questions} = {total_acc:.4f}")
    print(f"  Semantic:     {semantic_correct}/{semantic_total} = {semantic_acc:.4f}")
    print(f"  Syntactic:    {syntactic_correct}/{syntactic_total} = {syntactic_acc:.4f}")
    print(f"  Skipped:      {skipped}")

    return total_acc, semantic_acc, syntactic_acc, total_questions, skipped, semantic_total, syntactic_total