from fastapi import APIRouter, HTTPException, Depends
from app.auth import get_current_user
from app.models.schemas import DependencyGraphResponse
from app.indexing.vector_store import get_or_load_repo_index
from app.indexing.dependency_graph import build_repo_dependency_graph

router = APIRouter(prefix="/api/graph", tags=["Architecture & Dependency Graph"])

@router.get("/{repo_id}", response_model=DependencyGraphResponse)
async def get_dependency_graph(repo_id: str, current_user: dict = Depends(get_current_user)):
    idx = get_or_load_repo_index(repo_id)
    if not idx:
        raise HTTPException(status_code=404, detail="Repository index not found.")
        
    graph_data = build_repo_dependency_graph(idx.files_meta)
    return DependencyGraphResponse(**graph_data)
