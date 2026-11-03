from typing import List, Dict, Any, Optional
from app.indexing.vector_store import RepoIndex

def hybrid_search(
    index: RepoIndex,
    query: str,
    top_k: int = 8,
    file_filter: Optional[str] = None,
    alpha: float = 0.55
) -> List[Dict[str, Any]]:
    """
    Perform hybrid retrieval combining dense vector similarity and BM25 lexical search
    using Reciprocal Rank Fusion (RRF) and normalized weighted scoring.
    """
    # Fetch candidate pool (larger than top_k for high recall)
    vector_results = index.search_vector(query, top_k=top_k * 3, file_filter=file_filter)
    bm25_results = index.search_bm25(query, top_k=top_k * 3, file_filter=file_filter)
    
    # Map chunk id to metadata and ranks
    chunk_map: Dict[str, Dict[str, Any]] = {}
    
    # Find min and max for normalization
    vec_scores = [s for _, s in vector_results]
    bm25_scores = [s for _, s in bm25_results]
    
    min_vec, max_vec = (min(vec_scores), max(vec_scores)) if vec_scores else (0.0, 1.0)
    range_vec = (max_vec - min_vec) if (max_vec - min_vec) > 1e-6 else 1.0
    
    min_bm25, max_bm25 = (min(bm25_scores), max(bm25_scores)) if bm25_scores else (0.0, 1.0)
    range_bm25 = (max_bm25 - min_bm25) if (max_bm25 - min_bm25) > 1e-6 else 1.0

    # RRF constant
    k_rrf = 60.0
    
    # Process vector results
    for rank, (chunk, score) in enumerate(vector_results):
        cid = chunk["id"]
        norm_v = (score - min_vec) / range_vec
        if cid not in chunk_map:
            chunk_map[cid] = {
                "chunk": chunk,
                "vector_score": float(score),
                "bm25_score": 0.0,
                "norm_vec": norm_v,
                "norm_bm25": 0.0,
                "rrf_score": 1.0 / (k_rrf + rank + 1)
            }
        else:
            chunk_map[cid]["vector_score"] = float(score)
            chunk_map[cid]["norm_vec"] = norm_v
            chunk_map[cid]["rrf_score"] += 1.0 / (k_rrf + rank + 1)
            
    # Process BM25 results
    for rank, (chunk, score) in enumerate(bm25_results):
        cid = chunk["id"]
        norm_b = (score - min_bm25) / range_bm25
        if cid not in chunk_map:
            chunk_map[cid] = {
                "chunk": chunk,
                "vector_score": 0.0,
                "bm25_score": float(score),
                "norm_vec": 0.0,
                "norm_bm25": norm_b,
                "rrf_score": 1.0 / (k_rrf + rank + 1)
            }
        else:
            chunk_map[cid]["bm25_score"] = float(score)
            chunk_map[cid]["norm_bm25"] = norm_b
            chunk_map[cid]["rrf_score"] += 1.0 / (k_rrf + rank + 1)

    # Compute final combined scores
    final_items = []
    for cid, entry in chunk_map.items():
        chunk = entry["chunk"]
        combined_score = (alpha * entry["norm_vec"]) + ((1.0 - alpha) * entry["norm_bm25"])
        # Boost if present in both retrievers
        if entry["vector_score"] > 0 and entry["bm25_score"] > 0:
            combined_score *= 1.15
            
        final_items.append({
            "chunk_id": cid,
            "file_path": chunk["file_path"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "content": chunk["content"],
            "language": chunk["language"],
            "symbol_name": chunk.get("symbol_name"),
            "symbol_type": chunk.get("symbol_type"),
            "score": round(float(combined_score), 4),
            "vector_score": round(float(entry["vector_score"]), 4),
            "bm25_score": round(float(entry["bm25_score"]), 4),
            "rrf_score": round(float(entry["rrf_score"]), 5)
        })

    # Sort descending by combined score
    final_items.sort(key=lambda x: x["score"], reverse=True)
    return final_items[:top_k]
