import os
import shutil
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse

from app.config import settings
from app.auth import get_current_user
from app.database import get_db
from app.models.schemas import RepoResponse, GitHubIngestRequest, FileTreeItem
from app.ingestion.zip_loader import extract_safe_zip, ZipSecurityError
from app.ingestion.github_loader import download_github_repo, GitHubIngestError
from app.ingestion.file_filter import should_index_file, detect_language
from app.parser.ast_python import parse_python_file
from app.parser.multi_lang import parse_multi_lang
from app.parser.chunker import chunk_code_file
from app.indexing.vector_store import RepoIndex, cache_repo_index, get_or_load_repo_index

router = APIRouter(prefix="/api/repos", tags=["Repositories"])

def process_repository_pipeline(repo_id: str, repo_dir: Path) -> Dict[str, Any]:
    """
    Execute full multi-agent ingestion pipeline on repository files:
    1. Scan files
    2. Extract AST / symbols per file
    3. Generate code-aware chunks
    4. Build dense vectors and BM25 index
    5. Cache index and return statistics
    """
    files_meta: Dict[str, Dict[str, Any]] = {}
    symbols_map: Dict[str, List[Dict[str, Any]]] = {}
    all_chunks: List[Dict[str, Any]] = []
    language_counts: Dict[str, int] = {}
    
    total_lines = 0
    total_symbols = 0
    
    for root, _, files in os.walk(repo_dir):
        for f in files:
            file_path = Path(root) / f
            if not should_index_file(file_path, repo_dir):
                continue
                
            rel_path = str(file_path.relative_to(repo_dir)).replace("\\", "/")
            lang = detect_language(file_path)
            language_counts[lang] = language_counts.get(lang, 0) + 1
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as fp:
                    content = fp.read()
            except Exception:
                continue
                
            lines = content.splitlines()
            line_count = len(lines)
            total_lines += line_count
            
            # AST / Multi-lang parsing
            if lang == "python":
                parse_res = parse_python_file(content)
            else:
                parse_res = parse_multi_lang(content, lang)
                
            classes = parse_res.get("classes", [])
            functions = parse_res.get("functions", [])
            imports = parse_res.get("imports", [])
            calls = parse_res.get("calls", [])
            
            file_symbols = []
            for c in classes:
                file_symbols.append({"name": c["name"], "type": "class", "line": c["start_line"]})
            for fn in functions:
                parent = fn.get("parent_class")
                full_name = f"{parent}.{fn['name']}" if parent else fn['name']
                file_symbols.append({"name": full_name, "type": fn["type"], "line": fn["start_line"]})
                
            total_symbols += len(file_symbols)
            if file_symbols:
                symbols_map[rel_path] = file_symbols
                
            files_meta[rel_path] = {
                "file_path": rel_path,
                "language": lang,
                "lines_count": line_count,
                "symbols_count": len(file_symbols),
                "classes": classes,
                "functions": functions,
                "imports": imports,
                "calls": calls
            }
            
            # Chunking
            chunks = chunk_code_file(
                file_path=rel_path,
                content=content,
                language=lang,
                symbols=parse_res,
                max_chunk_lines=settings.CHUNK_SIZE_LINES,
                overlap_lines=settings.CHUNK_OVERLAP_LINES
            )
            all_chunks.extend(chunks)

    # Build and cache index
    repo_index = RepoIndex(repo_id)
    repo_index.build(all_chunks, symbols_map, files_meta)
    cache_repo_index(repo_id, repo_index)
    
    return {
        "total_files": len(files_meta),
        "total_lines": total_lines,
        "total_symbols": total_symbols,
        "total_chunks": len(all_chunks),
        "languages": language_counts,
        "files_meta": files_meta
    }

@router.post("/upload-zip", response_model=RepoResponse)
async def upload_repo_zip(
    file: UploadFile = File(...),
    repo_name: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip archive files are supported.")
        
    repo_id = "repo_" + secrets.token_hex(8)
    display_name = (repo_name.strip() if repo_name else Path(file.filename).stem) or "Repository"
    
    user_repos_dir = settings.STORAGE_DIR / "repos" / current_user["id"]
    repo_target_dir = user_repos_dir / repo_id
    repo_target_dir.mkdir(parents=True, exist_ok=True)
    
    temp_zip = user_repos_dir / f"upload_{repo_id}.zip"
    try:
        with open(temp_zip, "wb") as f:
            while chunk := await file.read(1024 * 64):
                f.write(chunk)
                
        # Extract safe zip
        extract_safe_zip(temp_zip, repo_target_dir)
        
        # Check if single root folder
        subdirs = [p for p in repo_target_dir.iterdir() if p.is_dir()]
        files_at_root = [p for p in repo_target_dir.iterdir() if p.is_file()]
        if len(subdirs) == 1 and len(files_at_root) == 0:
            nested = subdirs[0]
            for item in nested.iterdir():
                shutil.move(str(item), str(repo_target_dir))
            shutil.rmtree(nested, ignore_errors=True)
            
        # Run indexing pipeline
        pipeline_res = process_repository_pipeline(repo_id, repo_target_dir)
        
        # Save to DB
        created_at = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO repositories (
                    id, user_id, name, source_type, source_url, disk_path,
                    total_files, total_lines, total_symbols, languages_json,
                    status, status_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    repo_id, current_user["id"], display_name, "zip", file.filename,
                    str(repo_target_dir), pipeline_res["total_files"], pipeline_res["total_lines"],
                    pipeline_res["total_symbols"], json.dumps(pipeline_res["languages"]),
                    "ready", f"Indexed {pipeline_res['total_files']} files and {pipeline_res['total_chunks']} chunks.",
                    created_at
                )
            )
            # Record indexed files
            for fpath, fmeta in pipeline_res["files_meta"].items():
                file_id = "f_" + secrets.token_hex(8)
                cursor.execute(
                    """INSERT INTO indexed_files (id, repo_id, relative_path, language, lines_count, symbols_count, indexed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (file_id, repo_id, fpath, fmeta["language"], fmeta["lines_count"], fmeta["symbols_count"], created_at)
                )
            conn.commit()

        return {
            "id": repo_id,
            "name": display_name,
            "source_type": "zip",
            "source_url": file.filename,
            "total_files": pipeline_res["total_files"],
            "total_lines": pipeline_res["total_lines"],
            "total_symbols": pipeline_res["total_symbols"],
            "languages": pipeline_res["languages"],
            "status": "ready",
            "status_message": f"Successfully indexed {pipeline_res['total_files']} files.",
            "created_at": created_at
        }
        
    except ZipSecurityError as ze:
        raise HTTPException(status_code=400, detail=f"Archive Security Violation: {str(ze)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process archive: {str(e)}")
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except OSError:
                pass

@router.post("/ingest-github", response_model=RepoResponse)
async def ingest_github_repo(
    payload: GitHubIngestRequest,
    current_user: dict = Depends(get_current_user)
):
    repo_id = "repo_" + secrets.token_hex(8)
    user_repos_dir = settings.STORAGE_DIR / "repos" / current_user["id"]
    user_repos_dir.mkdir(parents=True, exist_ok=True)
    repo_target_dir = user_repos_dir / repo_id
    repo_target_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        repo_name, _ = await download_github_repo(
            repo_url=payload.repo_url,
            target_dir=repo_target_dir,
            branch=payload.branch or "main"
        )
        
        pipeline_res = process_repository_pipeline(repo_id, repo_target_dir)
        
        created_at = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO repositories (
                    id, user_id, name, source_type, source_url, disk_path,
                    total_files, total_lines, total_symbols, languages_json,
                    status, status_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    repo_id, current_user["id"], repo_name, "github", payload.repo_url,
                    str(repo_target_dir), pipeline_res["total_files"], pipeline_res["total_lines"],
                    pipeline_res["total_symbols"], json.dumps(pipeline_res["languages"]),
                    "ready", f"Indexed {pipeline_res['total_files']} files from GitHub.",
                    created_at
                )
            )
            for fpath, fmeta in pipeline_res["files_meta"].items():
                file_id = "f_" + secrets.token_hex(8)
                cursor.execute(
                    """INSERT INTO indexed_files (id, repo_id, relative_path, language, lines_count, symbols_count, indexed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (file_id, repo_id, fpath, fmeta["language"], fmeta["lines_count"], fmeta["symbols_count"], created_at)
                )
            conn.commit()

        return {
            "id": repo_id,
            "name": repo_name,
            "source_type": "github",
            "source_url": payload.repo_url,
            "total_files": pipeline_res["total_files"],
            "total_lines": pipeline_res["total_lines"],
            "total_symbols": pipeline_res["total_symbols"],
            "languages": pipeline_res["languages"],
            "status": "ready",
            "status_message": f"Successfully ingested {pipeline_res['total_files']} files from GitHub.",
            "created_at": created_at
        }
    except GitHubIngestError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest GitHub repository: {str(e)}")

@router.get("", response_model=List[RepoResponse])
async def list_repositories(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM repositories WHERE user_id = ? ORDER BY created_at DESC""",
            (current_user["id"],)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            langs = {}
            try:
                langs = json.loads(r["languages_json"] or "{}")
            except Exception:
                pass
            result.append({
                "id": r["id"],
                "name": r["name"],
                "source_type": r["source_type"],
                "source_url": r["source_url"],
                "total_files": r["total_files"],
                "total_lines": r["total_lines"],
                "total_symbols": r["total_symbols"],
                "languages": langs,
                "status": r["status"],
                "status_message": r["status_message"],
                "created_at": r["created_at"]
            })
        return result

@router.get("/{repo_id}", response_model=RepoResponse)
async def get_repository_details(repo_id: str, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM repositories WHERE id = ? AND user_id = ?", (repo_id, current_user["id"]))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Repository not found.")
        langs = json.loads(r["languages_json"] or "{}")
        return {
            "id": r["id"],
            "name": r["name"],
            "source_type": r["source_type"],
            "source_url": r["source_url"],
            "total_files": r["total_files"],
            "total_lines": r["total_lines"],
            "total_symbols": r["total_symbols"],
            "languages": langs,
            "status": r["status"],
            "status_message": r["status_message"],
            "created_at": r["created_at"]
        }

@router.get("/{repo_id}/tree")
async def get_repository_tree(repo_id: str, current_user: dict = Depends(get_current_user)):
    idx = get_or_load_repo_index(repo_id)
    if not idx:
        raise HTTPException(status_code=404, detail="Repository index not found.")
        
    # Construct tree from indexed files
    tree_root = {"name": "root", "path": "", "type": "directory", "children": []}
    
    for fpath, meta in sorted(idx.files_meta.items()):
        parts = fpath.split("/")
        curr = tree_root
        curr_path = ""
        
        for i, part in enumerate(parts):
            curr_path = f"{curr_path}/{part}" if curr_path else part
            if i == len(parts) - 1:
                # File node
                curr["children"].append({
                    "name": part,
                    "path": fpath,
                    "type": "file",
                    "language": meta.get("language", "text"),
                    "lines": meta.get("lines_count", 0),
                    "symbols": meta.get("symbols_count", 0)
                })
            else:
                # Directory node
                found_dir = None
                for c in curr["children"]:
                    if c["type"] == "directory" and c["name"] == part:
                        found_dir = c
                        break
                if not found_dir:
                    found_dir = {
                        "name": part,
                        "path": curr_path,
                        "type": "directory",
                        "children": []
                    }
                    curr["children"].append(found_dir)
                curr = found_dir
                
    return tree_root.get("children", [])

@router.get("/{repo_id}/file")
async def get_file_content(
    repo_id: str,
    path: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT disk_path FROM repositories WHERE id = ? AND user_id = ?", (repo_id, current_user["id"]))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Repository not found.")
        repo_dir = Path(r["disk_path"]).resolve()

    target_file = (repo_dir / path).resolve()
    try:
        target_file.relative_to(repo_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path.")
        
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="File does not exist.")
        
    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read file: {e}")
        
    idx = get_or_load_repo_index(repo_id)
    symbols = idx.symbols_map.get(path, []) if idx else []
    
    return {
        "path": path,
        "language": detect_language(target_file),
        "lines": len(content.splitlines()),
        "symbols": symbols,
        "content": content
    }

@router.delete("/{repo_id}")
async def delete_repository(repo_id: str, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT disk_path FROM repositories WHERE id = ? AND user_id = ?", (repo_id, current_user["id"]))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Repository not found.")
        disk_path = r["disk_path"]
        
        cursor.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        conn.commit()

    # Clean disk files and indices
    if disk_path and os.path.exists(disk_path):
        shutil.rmtree(disk_path, ignore_errors=True)
        
    index_meta = settings.STORAGE_DIR / "indices" / f"{repo_id}_meta.json"
    index_vec = settings.STORAGE_DIR / "indices" / f"{repo_id}_vec.npy"
    if index_meta.exists():
        index_meta.unlink(missing_ok=True)
    if index_vec.exists():
        index_vec.unlink(missing_ok=True)
        
    return {"message": "Repository and indices successfully removed."}
