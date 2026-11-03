import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from app.auth import get_current_user
from app.models.schemas import SearchRequest, SearchResponse, SearchResultChunk
from app.indexing.vector_store import get_or_load_repo_index
from app.indexing.hybrid_retriever import hybrid_search

router = APIRouter(prefix="/api/search", tags=["Search & Retrieval"])

@router.post("", response_model=SearchResponse)
async def execute_search(payload: SearchRequest, current_user: dict = Depends(get_current_user)):
    t0 = time.perf_counter()
    
    index = get_or_load_repo_index(payload.repo_id)
    if not index:
        raise HTTPException(status_code=404, detail="Repository index not found or repository not ready.")
        
    mode = payload.mode.lower()
    top_k = min(payload.top_k or 8, 30)
    
    results = []
    if mode == "vector":
        raw = index.search_vector(payload.query, top_k=top_k, file_filter=payload.file_filter)
        for chunk, score in raw:
            results.append(SearchResultChunk(
                chunk_id=chunk["id"],
                file_path=chunk["file_path"],
                start_line=chunk["start_line"],
                end_line=chunk["end_line"],
                content=chunk["content"],
                language=chunk["language"],
                score=round(float(score), 4),
                vector_score=round(float(score), 4),
                bm25_score=0.0,
                symbol_name=chunk.get("symbol_name"),
                symbol_type=chunk.get("symbol_type")
            ))
    elif mode == "bm25":
        raw = index.search_bm25(payload.query, top_k=top_k, file_filter=payload.file_filter)
        for chunk, score in raw:
            results.append(SearchResultChunk(
                chunk_id=chunk["id"],
                file_path=chunk["file_path"],
                start_line=chunk["start_line"],
                end_line=chunk["end_line"],
                content=chunk["content"],
                language=chunk["language"],
                score=round(float(score), 4),
                vector_score=0.0,
                bm25_score=round(float(score), 4),
                symbol_name=chunk.get("symbol_name"),
                symbol_type=chunk.get("symbol_type")
            ))
    else:  # hybrid
        hybrid_items = hybrid_search(
            index=index,
            query=payload.query,
            top_k=top_k,
            file_filter=payload.file_filter
        )
        for item in hybrid_items:
            results.append(SearchResultChunk(
                chunk_id=item["chunk_id"],
                file_path=item["file_path"],
                start_line=item["start_line"],
                end_line=item["end_line"],
                content=item["content"],
                language=item["language"],
                score=item["score"],
                vector_score=item.get("vector_score"),
                bm25_score=item.get("bm25_score"),
                symbol_name=item.get("symbol_name"),
                symbol_type=item.get("symbol_type")
            ))
            
    retrieval_ms = round((time.perf_counter() - t0) * 1000, 2)
    
    return SearchResponse(
        query=payload.query,
        mode=payload.mode,
        results=results,
        total_found=len(results),
        retrieval_ms=retrieval_ms
    )

@router.get("/symbols")
async def lookup_symbols(
    repo_id: str = Query(...),
    q: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    index = get_or_load_repo_index(repo_id)
    if not index:
        raise HTTPException(status_code=404, detail="Repository index not found.")
        
    query_str = (q or "").lower().strip()
    matches = []
    
    for fpath, symbols in index.symbols_map.items():
        for sym in symbols:
            name = sym.get("name", "")
            if not query_str or query_str in name.lower():
                matches.append({
                    "name": name,
                    "type": sym.get("type", "symbol"),
                    "file_path": fpath,
                    "line": sym.get("line", 1)
                })
                if len(matches) >= 50:
                    break
        if len(matches) >= 50:
            break
            
    return {"symbols": matches, "total": len(matches)}
