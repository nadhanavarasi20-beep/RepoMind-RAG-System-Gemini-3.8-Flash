import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from app.config import settings
from app.indexing.embeddings import generate_text_embedding, generate_batch_embeddings, compute_cosine_similarity
from app.indexing.bm25_index import RepoBM25Index

class RepoIndex:
    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.chunks: List[Dict[str, Any]] = []
        self.vectors: np.ndarray = np.zeros((0, 384), dtype=np.float32)
        self.bm25_index: Optional[RepoBM25Index] = None
        self.symbols_map: Dict[str, List[Dict[str, Any]]] = {}
        self.files_meta: Dict[str, Dict[str, Any]] = {}

    def build(self, chunks: List[Dict[str, Any]], symbols_map: Dict[str, List[Dict[str, Any]]], files_meta: Dict[str, Dict[str, Any]]):
        self.chunks = chunks
        self.symbols_map = symbols_map
        self.files_meta = files_meta
        
        # Build vectors
        texts_to_embed = [
            f"File: {c.get('file_path', '')}\nSymbol: {c.get('symbol_name', '') or ''}\n{c.get('content', '')}"
            for c in chunks
        ]
        self.vectors = generate_batch_embeddings(texts_to_embed)
        
        # Build BM25 index
        self.bm25_index = RepoBM25Index(chunks)

    def search_vector(self, query: str, top_k: int = 10, file_filter: Optional[str] = None) -> List[Tuple[Dict[str, Any], float]]:
        if len(self.chunks) == 0 or self.vectors.shape[0] == 0:
            return []
            
        q_vec = generate_text_embedding(query)
        sims = compute_cosine_similarity(q_vec, self.vectors)
        
        results: List[Tuple[Dict[str, Any], float]] = []
        for i, score in enumerate(sims):
            chunk = self.chunks[i]
            if file_filter and file_filter not in chunk.get("file_path", ""):
                continue
            results.append((chunk, float(score)))
            
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def search_bm25(self, query: str, top_k: int = 10, file_filter: Optional[str] = None) -> List[Tuple[Dict[str, Any], float]]:
        if not self.bm25_index:
            return []
        raw = self.bm25_index.search(query, top_k=top_k * 2)
        if file_filter:
            filtered = [r for r in raw if file_filter in r[0].get("file_path", "")]
            return filtered[:top_k]
        return raw[:top_k]

    def save(self):
        index_dir = settings.STORAGE_DIR / "indices"
        index_dir.mkdir(parents=True, exist_ok=True)
        
        meta_file = index_dir / f"{self.repo_id}_meta.json"
        vec_file = index_dir / f"{self.repo_id}_vec.npy"
        
        payload = {
            "repo_id": self.repo_id,
            "chunks": self.chunks,
            "symbols_map": self.symbols_map,
            "files_meta": self.files_meta
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            
        np.save(str(vec_file), self.vectors)

    @classmethod
    def load(cls, repo_id: str) -> Optional["RepoIndex"]:
        index_dir = settings.STORAGE_DIR / "indices"
        meta_file = index_dir / f"{repo_id}_meta.json"
        vec_file = index_dir / f"{repo_id}_vec.npy"
        
        if not meta_file.exists() or not vec_file.exists():
            return None
            
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            vectors = np.load(str(vec_file))
            
            idx = cls(repo_id)
            idx.chunks = data.get("chunks", [])
            idx.symbols_map = data.get("symbols_map", {})
            idx.files_meta = data.get("files_meta", {})
            idx.vectors = vectors
            idx.bm25_index = RepoBM25Index(idx.chunks)
            return idx
        except Exception as e:
            print(f"Error loading index for {repo_id}: {e}")
            return None


# Global active index cache
_ACTIVE_INDICES: Dict[str, RepoIndex] = {}

def get_or_load_repo_index(repo_id: str) -> Optional[RepoIndex]:
    if repo_id in _ACTIVE_INDICES:
        return _ACTIVE_INDICES[repo_id]
    loaded = RepoIndex.load(repo_id)
    if loaded:
        _ACTIVE_INDICES[repo_id] = loaded
    return loaded

def cache_repo_index(repo_id: str, index: RepoIndex):
    _ACTIVE_INDICES[repo_id] = index
    index.save()
