import math
import numpy as np
from typing import List, Union
from app.indexing.bm25_index import code_tokenize

# Deterministic projection to 384 dimensions
EMBEDDING_DIM = 384
VOCAB_HASH_BINS = 4096

# Generate a fixed orthonormal-like projection matrix
_rng = np.random.RandomState(42)
_PROJECTION_MATRIX = _rng.randn(VOCAB_HASH_BINS, EMBEDDING_DIM).astype(np.float32)
# Normalize projection columns
_PROJECTION_MATRIX /= np.linalg.norm(_PROJECTION_MATRIX, axis=0, keepdims=True) + 1e-9

def _hash_token(token: str) -> int:
    """Hash token into a stable index in [0, VOCAB_HASH_BINS - 1]."""
    h = 2166136261
    for byte in token.encode('utf-8'):
        h = (h ^ byte) * 16777619
        h &= 0xFFFFFFFF
    return h % VOCAB_HASH_BINS

def generate_text_embedding(text: str) -> np.ndarray:
    """
    Generate a 384-dimensional dense semantic embedding vector for code or natural language query.
    Extracts code tokens, sub-tokens, character tri-grams, and projects into normalized dense vector.
    """
    tokens = code_tokenize(text)
    if not tokens:
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        vec[0] = 1.0
        return vec
        
    counts = np.zeros(VOCAB_HASH_BINS, dtype=np.float32)
    
    # 1. Word tokens
    for t in tokens:
        idx = _hash_token(t)
        counts[idx] += 1.0
        
        # 2. Sub-character 3-grams for typo resilience & syntax cues
        if len(t) >= 4:
            for i in range(len(t) - 2):
                ngram = t[i:i+3]
                counts[_hash_token(ngram)] += 0.5
                
    # Sublinear TF scaling: 1 + log(tf)
    nonzero_mask = counts > 0
    counts[nonzero_mask] = 1.0 + np.log(counts[nonzero_mask])
    
    # Dense projection
    dense_vec = counts @ _PROJECTION_MATRIX
    
    # L2 normalization for instant cosine similarity via dot product
    norm = np.linalg.norm(dense_vec)
    if norm > 1e-9:
        dense_vec /= norm
    else:
        dense_vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        dense_vec[0] = 1.0
        
    return dense_vec.astype(np.float32)

def generate_batch_embeddings(texts: List[str]) -> np.ndarray:
    """Generate dense embeddings for a batch of text chunks."""
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    return np.vstack([generate_text_embedding(t) for t in texts])

def compute_cosine_similarity(query_vec: np.ndarray, corpus_vecs: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query vector and matrix of corpus vectors."""
    if corpus_vecs.shape[0] == 0:
        return np.array([], dtype=np.float32)
    # Both are unit normalized, so dot product = cosine similarity
    sims = corpus_vecs @ query_vec
    return np.clip(sims, -1.0, 1.0)
