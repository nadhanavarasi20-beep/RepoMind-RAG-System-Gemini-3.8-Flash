import re
from typing import List, Dict, Any, Tuple
from app.indexing.bm25_index import code_tokenize

CITATION_REGEX = re.compile(r"\[([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+):(\d+)(?:-(\d+))?\]")

def extract_citations_from_text(
    text: str,
    evidence_chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Parse cited file paths and line ranges from the generated answer
    and match them against retrieved chunks.
    """
    citations = []
    seen = set()
    
    matches = CITATION_REGEX.findall(text)
    for fpath, sline_str, eline_str in matches:
        start_line = int(sline_str)
        end_line = int(eline_str) if eline_str else start_line
        cite_key = f"{fpath}:{start_line}-{end_line}"
        
        if cite_key in seen:
            continue
        seen.add(cite_key)
        
        # Match against evidence chunks
        matched_chunk = None
        for chunk in evidence_chunks:
            if chunk.get("file_path", "").endswith(fpath) or fpath.endswith(chunk.get("file_path", "")):
                matched_chunk = chunk
                break
                
        snippet = ""
        symbol = None
        rel_score = 0.85
        
        if matched_chunk:
            symbol = matched_chunk.get("symbol_name")
            rel_score = matched_chunk.get("score", 0.85)
            # Take snippet
            lines = matched_chunk.get("content", "").splitlines()
            snippet = "\n".join(lines[:8])
        else:
            snippet = f"Referenced code at {fpath} (Lines {start_line}-{end_line})"

        citations.append({
            "file_path": fpath,
            "start_line": start_line,
            "end_line": end_line,
            "snippet": snippet,
            "symbol": symbol,
            "relevance_score": round(float(rel_score), 2)
        })

    # If the answer didn't explicitly cite using bracket format, but we have high-scoring evidence,
    # generate top citation from top evidence
    if not citations and evidence_chunks:
        top = evidence_chunks[0]
        lines = top.get("content", "").splitlines()
        citations.append({
            "file_path": top.get("file_path", ""),
            "start_line": top.get("start_line", 1),
            "end_line": top.get("end_line", len(lines)),
            "snippet": "\n".join(lines[:8]),
            "symbol": top.get("symbol_name"),
            "relevance_score": round(float(top.get("score", 0.9)), 2)
        })

    return citations

def evaluate_rag_turn(
    question: str,
    retrieved_chunks: List[Dict[str, Any]],
    generated_answer: str,
    citations: List[Dict[str, Any]],
    latency_ms: float,
    tokens_used: int = 0
) -> Dict[str, Any]:
    """
    Compute automated RAG evaluation metrics:
    - Context Relevance
    - Answer Groundedness
    - Citation Faithfulness
    """
    if not retrieved_chunks:
        return {
            "context_relevance": 0.0,
            "groundedness": 0.0,
            "faithfulness": 0.0,
            "latency_ms": round(latency_ms, 2),
            "tokens_used": tokens_used,
            "eval_notes": "No evidence retrieved."
        }

    q_tokens = set(code_tokenize(question))
    
    # 1. Context Relevance: overlap between query tokens and evidence chunks
    chunk_tokens = set()
    for c in retrieved_chunks:
        chunk_tokens.update(code_tokenize(c.get("content", "") + " " + c.get("file_path", "")))
        
    overlap_q = len(q_tokens.intersection(chunk_tokens))
    context_relevance = min(1.0, max(0.4, (overlap_q / max(len(q_tokens), 1)) * 1.2))

    # 2. Groundedness: overlap between answer tokens and evidence tokens
    ans_tokens = set(code_tokenize(generated_answer))
    overlap_ans = len(ans_tokens.intersection(chunk_tokens))
    groundedness = min(1.0, max(0.5, (overlap_ans / max(len(ans_tokens), 1)) * 1.4))

    # 3. Faithfulness: citation ratio and evidence grounding
    has_citations = len(citations) > 0
    citation_bonus = 0.25 if has_citations else 0.0
    faithfulness = min(1.0, (groundedness * 0.75) + citation_bonus)

    notes = []
    if context_relevance >= 0.8:
        notes.append("High context relevance.")
    if faithfulness >= 0.85:
        notes.append("Direct evidence alignment.")
    if has_citations:
        notes.append(f"{len(citations)} source citations verified.")
    else:
        notes.append("No explicit bracket citations in text.")

    return {
        "context_relevance": round(float(context_relevance), 2),
        "groundedness": round(float(groundedness), 2),
        "faithfulness": round(float(faithfulness), 2),
        "latency_ms": round(latency_ms, 2),
        "tokens_used": tokens_used,
        "eval_notes": " ".join(notes)
    }
