import time
import json
import secrets
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException, Depends

from app.auth import get_current_user
from app.database import get_db
from app.models.schemas import (
    ChatMessageRequest, ChatMessageResponse,
    CitationItem, EvidenceItem, RAGEvaluation
)
from app.indexing.vector_store import get_or_load_repo_index
from app.indexing.hybrid_retriever import hybrid_search
from app.gemini.client import gemini_client
from app.gemini.prompt_builder import SYSTEM_INSTRUCTION, build_rag_user_prompt
from app.evaluation.rag_eval import extract_citations_from_text, evaluate_rag_turn

router = APIRouter(prefix="/api/chat", tags=["AI Chat & Codebase Intelligence"])


def build_evidence_fallback(
    question: str,
    retrieved_chunks: List[dict],
    status: str
) -> tuple[str, List[CitationItem]]:
    citations = []
    evidence_notes = []
    evidence_sections = []

    for i, chunk in enumerate(retrieved_chunks[:4], start=1):
        file_path = chunk.get("file_path", "unknown")
        start_line = int(chunk.get("start_line", 1))
        lines = chunk.get("content", "").splitlines()
        end_line = int(chunk.get("end_line", start_line + max(len(lines) - 1, 0)))
        snippet = "\n".join(lines[:12])
        language = chunk.get("language") or "text"
        citation_text = f"[{file_path}:{start_line}-{end_line}]"
        citation = CitationItem(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            snippet=snippet,
            symbol=chunk.get("symbol_name"),
            relevance_score=round(float(chunk.get("score", 0.0)), 2)
        )
        citations.append(citation)
        documentation_summary = None
        if file_path.lower().endswith((".md", ".rst", ".txt")):
            documentation_summary = next(
                (
                    line.strip()
                    for line in lines[:12]
                    if line.strip() and not line.lstrip().startswith("#")
                ),
                None
            )
        if documentation_summary:
            evidence_notes.append(
                f"- Retrieved documentation states: {documentation_summary} {citation_text}"
            )
        elif chunk.get("symbol_name"):
            symbol_type = chunk.get("symbol_type") or "symbol"
            evidence_notes.append(
                f"- The retrieved source contains the {symbol_type} "
                f"`{chunk['symbol_name']}`; its indexed code excerpt follows. {citation_text}"
            )
        else:
            evidence_notes.append(
                f"- Retrieved source context from `{file_path}` is shown below. {citation_text}"
            )
        evidence_sections.append(
            f"#### Retrieved evidence {i} — {citation_text}\n"
            f"```{language}\n{snippet}\n```"
        )

    if not evidence_sections:
        content = f"""### Local evidence fallback — not AI-generated

Gemini could not produce an answer ({status}), and no code chunks were retrieved for this question. RepoMind cannot safely explain the project without source evidence. Try a more specific question or re-index the repository.

**Question:** {question}"""
    else:
        notes_text = "\n".join(evidence_notes)
        evidence_text = "\n".join(evidence_sections)
        content = f"""### Local evidence fallback — not AI-generated

Gemini could not produce an answer ({status}). This is not a model-generated explanation. These notes are limited to retrieved documentation and indexed symbol metadata; the exact source excerpts and citations follow.

**Question:** {question}

#### Evidence-based notes
{notes_text}

#### Retrieved code and documentation excerpts
{evidence_text}"""

    return content, citations


@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(
    payload: ChatMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    t0 = time.perf_counter()
    
    # 1. Verify repository
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM repositories WHERE id = ? AND user_id = ?", (payload.repo_id, current_user["id"]))
        repo_row = cursor.fetchone()
        if not repo_row:
            raise HTTPException(status_code=404, detail="Repository not found.")
            
    # 2. Get or create session
    session_id = payload.session_id
    if not session_id:
        session_id = "sess_" + secrets.token_hex(8)
        created_at = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO chat_sessions (id, repo_id, user_id, title, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, payload.repo_id, current_user["id"], payload.message[:40] or "Code Intelligence", created_at)
            )
            conn.commit()

    # 3. Retrieve conversation history
    history = []
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT 6""",
            (session_id,)
        )
        for r in cursor.fetchall():
            history.append({"role": r["role"], "content": r["content"]})

    # Record user message in DB
    user_msg_id = "msg_" + secrets.token_hex(8)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO chat_messages (id, session_id, role, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_msg_id, session_id, "user", payload.message, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()

    # 4. Perform Hybrid Search
    index = get_or_load_repo_index(payload.repo_id)
    retrieved_chunks = []
    evidence_items = []
    mode = (payload.search_mode or "hybrid").lower()
    top_k = min(payload.top_k or 6, 12)

    if index:
        if mode == "vector":
            raw = index.search_vector(payload.message, top_k=top_k)
            for c, s in raw:
                retrieved_chunks.append({**c, "score": s})
        elif mode == "bm25":
            raw = index.search_bm25(payload.message, top_k=top_k)
            for c, s in raw:
                retrieved_chunks.append({**c, "score": s})
        else:
            retrieved_chunks = hybrid_search(index, payload.message, top_k=top_k)
            
        for c in retrieved_chunks:
            lines = c.get("content", "").splitlines()
            evidence_items.append(EvidenceItem(
                chunk_id=c.get("chunk_id", c.get("id", "")),
                file_path=c.get("file_path", ""),
                start_line=c.get("start_line", 1),
                end_line=c.get("end_line", len(lines)),
                snippet="\n".join(lines[:12]),
                score=round(float(c.get("score", 0.0)), 4),
                retrieval_method=mode
            ))

    # 5. Build Grounded Prompt
    user_prompt = build_rag_user_prompt(
        question=payload.message,
        retrieved_chunks=retrieved_chunks,
        conversation_history=history
    )

    # 6. Generate an answer; retries and fallback reuse the retrieved evidence.
    configured_model = gemini_client.get_configured_model()
    cache_key = f"{payload.repo_id}:{payload.message.strip().lower()}:{mode}"
    
    gemini_resp = await gemini_client.generate_response(
        system_instruction=SYSTEM_INSTRUCTION,
        user_prompt=user_prompt,
        cache_key=cache_key
    )

    latency_ms = (time.perf_counter() - t0) * 1000.0
    citations = []
    eval_dict = {}

    if gemini_resp["success"]:
        content = gemini_resp["content"]
        status_state = "active"
        error_detail = None
        
        # Extract citations
        raw_citations = extract_citations_from_text(content, retrieved_chunks)
        citations = [
            CitationItem(
                file_path=c["file_path"],
                start_line=c["start_line"],
                end_line=c["end_line"],
                snippet=c["snippet"],
                symbol=c.get("symbol"),
                relevance_score=c["relevance_score"]
            )
            for c in raw_citations
        ]
        
        # Evaluate turn
        eval_dict = evaluate_rag_turn(
            question=payload.message,
            retrieved_chunks=retrieved_chunks,
            generated_answer=content,
            citations=[c.model_dump() for c in citations],
            latency_ms=latency_ms,
            tokens_used=gemini_resp.get("tokens_used", 0)
        )
    else:
        status_state = gemini_resp.get("status", "fallback_evidence_only")
        error_detail = gemini_resp.get("error", "Gemini service is unavailable.")
        content, citations = build_evidence_fallback(
            payload.message,
            retrieved_chunks,
            status_state
        )
        eval_dict = evaluate_rag_turn(
            question=payload.message,
            retrieved_chunks=retrieved_chunks,
            generated_answer=content,
            citations=[citation.model_dump() for citation in citations],
            latency_ms=latency_ms,
            tokens_used=0
        )

    # 7. Store assistant response
    assistant_msg_id = "msg_" + secrets.token_hex(8)
    created_at = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO chat_messages (id, session_id, role, content, citations_json, eval_json, evidence_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                assistant_msg_id, session_id, "assistant", content,
                json.dumps([c.model_dump() for c in citations]),
                json.dumps(eval_dict),
                json.dumps([e.model_dump() for e in evidence_items]),
                created_at
            )
        )
        conn.commit()

    return ChatMessageResponse(
        session_id=session_id,
        message_id=assistant_msg_id,
        role="assistant",
        content=content,
        model=gemini_resp.get("model", configured_model),
        citations=citations,
        evidence=evidence_items,
        evaluation=RAGEvaluation(**eval_dict),
        gemini_status=status_state,
        gemini_error_detail=error_detail
    )

@router.get("/sessions/{repo_id}")
async def get_repo_chat_sessions(repo_id: str, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM chat_sessions WHERE repo_id = ? AND user_id = ? ORDER BY created_at DESC""",
            (repo_id, current_user["id"])
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

@router.get("/history/{session_id}")
async def get_session_history(session_id: str, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        # Verify ownership
        cursor.execute("SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, current_user["id"]))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Chat session not found.")
            
        cursor.execute(
            """SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC""",
            (session_id,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            cites = json.loads(r["citations_json"] or "[]")
            eval_data = json.loads(r["eval_json"] or "{}")
            evidence = json.loads(r["evidence_json"] or "[]")
            result.append({
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "citations": cites,
                "evaluation": eval_data,
                "evidence": evidence,
                "created_at": r["created_at"]
            })
        return result
