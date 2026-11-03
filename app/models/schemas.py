from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ----------------- Auth Schemas -----------------
class UserRegister(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="Valid email address")
    password: str = Field(..., min_length=6, description="Password at least 6 characters")
    full_name: str = Field(..., min_length=2)

class UserLogin(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    created_at: str
    last_login: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# ----------------- Ingest Schemas -----------------
class GitHubIngestRequest(BaseModel):
    repo_url: str = Field(..., description="Public GitHub repository URL (e.g. https://github.com/owner/repo)")
    branch: Optional[str] = "main"

class FileTreeItem(BaseModel):
    name: str
    path: str
    type: str  # 'file' or 'directory'
    language: Optional[str] = None
    size: Optional[int] = 0
    lines: Optional[int] = 0
    children: Optional[List["FileTreeItem"]] = None

FileTreeItem.model_rebuild()

class RepoResponse(BaseModel):
    id: str
    name: str
    source_type: str
    source_url: Optional[str] = None
    total_files: int
    total_lines: int
    total_symbols: int
    languages: Dict[str, int]
    status: str
    status_message: str
    created_at: str

# ----------------- Search & Retrieval Schemas -----------------
class SearchRequest(BaseModel):
    repo_id: str
    query: str
    mode: str = "hybrid"  # 'hybrid', 'vector', 'bm25'
    top_k: int = 8
    file_filter: Optional[str] = None

class SearchResultChunk(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    score: float
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    mode: str
    results: List[SearchResultChunk]
    total_found: int
    retrieval_ms: float

# ----------------- Citations & RAG Evaluation -----------------
class CitationItem(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    snippet: str
    symbol: Optional[str] = None
    relevance_score: float

class RAGEvaluation(BaseModel):
    context_relevance: float = Field(..., ge=0.0, le=1.0, description="Relevance of retrieved chunks to question")
    groundedness: float = Field(..., ge=0.0, le=1.0, description="Degree to which answer is supported by evidence")
    faithfulness: float = Field(..., ge=0.0, le=1.0, description="Absence of ungrounded statements")
    latency_ms: float
    tokens_used: Optional[int] = 0
    eval_notes: Optional[str] = None

class EvidenceItem(BaseModel):
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    snippet: str
    score: float
    retrieval_method: str

# ----------------- Chat Schemas -----------------
class ChatMessageRequest(BaseModel):
    repo_id: str
    session_id: Optional[str] = None
    message: str
    search_mode: Optional[str] = "hybrid"
    top_k: Optional[int] = 6

class ChatMessageResponse(BaseModel):
    session_id: str
    message_id: str
    role: str = "assistant"
    content: str
    model: str
    citations: List[CitationItem]
    evidence: List[EvidenceItem]
    evaluation: RAGEvaluation
    gemini_status: str  # 'active', 'quota_exceeded', 'model_error', 'fallback_evidence_only'
    gemini_error_detail: Optional[str] = None

# ----------------- Graph Schemas -----------------
class GraphNode(BaseModel):
    id: str
    label: str
    type: str  # 'module', 'file', 'class', 'function'
    size: int = 1
    language: Optional[str] = None

class GraphLink(BaseModel):
    source: str
    target: str
    type: str  # 'imports', 'calls', 'defines'
    weight: int = 1

class DependencyGraphResponse(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]
    total_modules: int
    total_dependencies: int

# ----------------- System & Settings -----------------
class GeminiStatusResponse(BaseModel):
    configured_model: str
    api_key_configured: bool
    verified_available: bool
    status_code: Optional[int] = None
    status_message: str
    last_checked: str
    quota_limited: bool = False

class SettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
