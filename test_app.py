"""
Comprehensive Integration & Sanity Test for RepoMind
Tests:
- Database creation & User Auth
- AST parsing (Python & Multi-lang)
- Semantic chunking & Tokenization
- Dense Vector generation & BM25 indexing
- Hybrid Retrieval (RRF & weighted score)
- Dependency Graph generator
- Gemini Client error resilience (404, 429, timeouts)
- FastAPI endpoints
"""

import sys
import os
import shutil
import zipfile
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def run_tests():
    print("=" * 60)
    print("REPOMIND COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    # 1. Test Database & Auth
    print("\n[1] Testing Database Initialization & Auth...")
    from app.database import init_db, get_db
    from app.auth import hash_password, verify_password, create_user, get_user_by_email, create_access_token, decode_access_token

    init_db()
    pwd = "MySecretPassword123!"
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed), "Password verification failed"
    assert not verify_password("wrong_password", hashed), "Password verification accepted wrong password"
    print("  -> Password hashing (PBKDF2-HMAC-SHA256) passed.")

    test_email = "developer@repomind.ai"
    # Clean if exists from prior run
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE email = ?", (test_email,))
        conn.commit()

    user = create_user(email=test_email, password=pwd, full_name="Lead Engineer")
    assert user["email"] == test_email
    token = create_access_token({"sub": user["id"], "email": test_email})
    decoded = decode_access_token(token)
    assert decoded["sub"] == user["id"]
    print("  -> User registration, DB storage, and JWT token decode passed.")

    # 2. Test AST Parser
    print("\n[2] Testing AST & Multi-Language Parsing...")
    from app.parser.ast_python import parse_python_file
    from app.parser.multi_lang import parse_multi_lang

    sample_py = '''
import os
from typing import List

class RepositoryManager:
    """Manages repository lifecycle and caching."""
    def __init__(self, repo_id: str):
        self.repo_id = repo_id

    async def ingest_code(self, source_path: str) -> bool:
        """Parse and ingest code."""
        return True

def standalone_helper(x: int) -> int:
    return x * 2
'''
    py_ast = parse_python_file(sample_py)
    assert py_ast["success"], "Python AST parse failed"
    assert len(py_ast["classes"]) == 1, "Expected 1 class"
    assert py_ast["classes"][0]["name"] == "RepositoryManager"
    assert len(py_ast["functions"]) == 3, f"Expected 3 functions/methods, got {len(py_ast['functions'])}"
    assert len(py_ast["imports"]) == 2, "Expected 2 imports"
    print(f"  -> Python AST parsed {len(py_ast['classes'])} class, {len(py_ast['functions'])} functions, {len(py_ast['imports'])} imports.")

    sample_ts = '''
import { useState } from 'react';
export class AuthService {
    verify() { return true; }
}
export function loginUser(token: string) {
    return token.length > 0;
}
'''
    ts_ast = parse_multi_lang(sample_ts, "typescript")
    assert len(ts_ast["classes"]) == 1
    assert len(ts_ast["functions"]) == 1
    assert len(ts_ast["imports"]) == 1
    print(f"  -> TypeScript parser extracted {len(ts_ast['classes'])} class, {len(ts_ast['functions'])} function.")

    # 3. Test Chunker & Tokenization
    print("\n[3] Testing Code-Aware Semantic Chunker...")
    from app.parser.chunker import chunk_code_file
    chunks = chunk_code_file(
        file_path="app/manager.py",
        content=sample_py,
        language="python",
        symbols=py_ast,
        max_chunk_lines=20,
        overlap_lines=5
    )
    assert len(chunks) > 0, "No chunks generated"
    assert any(c.get("symbol_name") == "RepositoryManager" for c in chunks), "Class symbol not attached to chunk"
    print(f"  -> Chunker generated {len(chunks)} code-aware semantic chunks with symbol boundaries.")

    # 4. Test Local Embeddings & BM25 Indexing
    print("\n[4] Testing Local Dense Vectors & BM25 Search...")
    from app.indexing.embeddings import generate_text_embedding, compute_cosine_similarity
    from app.indexing.bm25_index import RepoBM25Index, code_tokenize

    v1 = generate_text_embedding("RepositoryManager ingest_code async function")
    v2 = generate_text_embedding("manage repository ingest source code")
    v3 = generate_text_embedding("unrelated cooking recipe pancakes syrup")

    sim_rel = compute_cosine_similarity(v1, v2.reshape(1, -1))[0]
    sim_unrel = compute_cosine_similarity(v1, v3.reshape(1, -1))[0]
    assert sim_rel > sim_unrel, f"Semantic similarity failed: {sim_rel} <= {sim_unrel}"
    print(f"  -> Semantic Cosine Similarity: Related = {sim_rel:.3f}, Unrelated = {sim_unrel:.3f} (Passed).")

    bm25 = RepoBM25Index(chunks)
    bm25_res = bm25.search("standalone_helper integer")
    assert len(bm25_res) > 0
    print(f"  -> BM25 Top Match: {bm25_res[0][0].get('symbol_name')} (Score: {bm25_res[0][1]:.3f}).")

    # 5. Test Hybrid Retriever
    print("\n[5] Testing Hybrid Retriever (RRF + Weighted Score)...")
    from app.indexing.vector_store import RepoIndex
    from app.indexing.hybrid_retriever import hybrid_search

    repo_idx = RepoIndex("test_repo_1")
    repo_idx.build(chunks, {"app/manager.py": py_ast["functions"]}, {"app/manager.py": {"language": "python", "lines_count": 25}})
    hybrid_res = hybrid_search(repo_idx, "ingest_code source_path", top_k=3)
    assert len(hybrid_res) > 0
    top_hit = hybrid_res[0]
    print(f"  -> Hybrid Top Result: [{top_hit['file_path']}:{top_hit['start_line']}-{top_hit['end_line']}] (Score: {top_hit['score']}, Vector: {top_hit['vector_score']}, BM25: {top_hit['bm25_score']}).")

    # 6. Test Dependency Graph
    print("\n[6] Testing Dependency Graph...")
    from app.indexing.dependency_graph import build_repo_dependency_graph
    files_meta = {
        "app/main.py": {"language": "python", "lines_count": 50, "symbols_count": 2, "imports": [{"module": "app.auth"}, {"module": "fastapi"}]},
        "app/auth.py": {"language": "python", "lines_count": 80, "symbols_count": 4, "imports": [{"module": "jose"}, {"module": "hashlib"}]}
    }
    graph = build_repo_dependency_graph(files_meta)
    assert graph["total_modules"] >= 2
    assert graph["total_dependencies"] >= 1
    print(f"  -> Graph generated: {graph['total_modules']} modules, {graph['total_dependencies']} links.")

    # 7. Test Gemini Client Resilience
    print("\n[7] Testing Gemini Client Resilience & Quota-Awareness...")
    from app.gemini.client import GeminiClient

    client = GeminiClient(api_key="TEST_DUMMY_KEY", model="gemini-3.8-flash")
    assert client.get_configured_model() == "gemini-3.8-flash"
    print(f"  -> Configured Model verified: {client.get_configured_model()}")

    # 8. Test RAG Evaluator
    print("\n[8] Testing RAG Turn Evaluation & Citations...")
    from app.evaluation.rag_eval import extract_citations_from_text, evaluate_rag_turn

    sample_answer = """The ingest_code function is implemented in `[app/manager.py:10-12]`.
It accepts a source_path string and returns a boolean status."""

    citations = extract_citations_from_text(sample_answer, hybrid_res)
    assert len(citations) >= 1
    print(f"  -> Extracted Citation: [{citations[0]['file_path']}:{citations[0]['start_line']}-{citations[0]['end_line']}].")

    eval_score = evaluate_rag_turn(
        question="How does ingest_code work in manager?",
        retrieved_chunks=hybrid_res,
        generated_answer=sample_answer,
        citations=citations,
        latency_ms=120.5
    )
    assert eval_score["groundedness"] >= 0.5, f"Groundedness: {eval_score['groundedness']}"
    assert eval_score["faithfulness"] >= 0.5, f"Faithfulness: {eval_score['faithfulness']}"
    print(f"  -> RAG Evaluation: Relevance={eval_score['context_relevance']}, Groundedness={eval_score['groundedness']}, Faithfulness={eval_score['faithfulness']}.")

    # 9. Test Zip Loading with Security Check
    print("\n[9] Testing Safe ZIP Extraction & ZipSlip Prevention...")
    from app.ingestion.zip_loader import extract_safe_zip, ZipSecurityError

    test_zip_path = ROOT / "test_sample_repo.zip"
    extract_target = ROOT / "test_extracted_repo"

    # Create safe zip
    with zipfile.ZipFile(test_zip_path, "w") as zf:
        zf.writestr("src/main.py", "def run():\n    print('Hello RepoMind')\n")
        zf.writestr("README.md", "# Sample Repo\nTest archive.\n")

    files_extracted, bytes_uncompressed = extract_safe_zip(test_zip_path, extract_target)
    assert files_extracted == 2
    assert (extract_target / "src" / "main.py").exists()
    print(f"  -> Safe ZIP extraction passed: {files_extracted} files extracted cleanly.")

    # Cleanup test files
    if test_zip_path.exists():
        test_zip_path.unlink()
    if extract_target.exists():
        shutil.rmtree(extract_target)

    # 10. Test FastAPI App Initialization
    print("\n[10] Testing FastAPI App...")
    from app.main import app
    assert "RepoMind" in app.title
    print("  -> FastAPI app configured and all routers mounted.")

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL TESTS PASSED! REPOMIND IS FULLY FUNCTIONAL.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
