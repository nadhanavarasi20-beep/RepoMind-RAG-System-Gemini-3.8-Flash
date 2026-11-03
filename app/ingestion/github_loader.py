import re
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import httpx
from app.ingestion.zip_loader import extract_safe_zip, ZipSecurityError

class GitHubIngestError(Exception):
    pass

def validate_github_url(repo_url: str) -> tuple[str, str, str | None]:
    """
    Validate public GitHub repository URL against SSRF and parse owner, repo, and optional branch.
    Supports:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - https://github.com/owner/repo/tree/branch_name
      - https://github.com/owner/repo/tree/branch_name/subfolder
    """
    cleaned_url = repo_url.strip()
    parsed = urlparse(cleaned_url)
    
    if parsed.scheme != "https":
        raise GitHubIngestError("Only secure HTTPS URLs are permitted (e.g., https://github.com/owner/repo).")
        
    hostname = (parsed.hostname or "").lower()
    if hostname not in {"github.com", "www.github.com"}:
        raise GitHubIngestError("Only public repositories from github.com are permitted.")
        
    if parsed.port and parsed.port not in {443, 80}:
        raise GitHubIngestError("Invalid port specified in GitHub repository URL.")
        
    # Split path: /owner/repo/...
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(path_parts) < 2:
        raise GitHubIngestError("Invalid GitHub repository URL format. Expected: https://github.com/owner/repository")
        
    owner = path_parts[0]
    repo = path_parts[1]
    
    if repo.endswith(".git"):
        repo = repo[:-4]
        
    # Validation of owner and repo characters
    if not re.match(r"^[a-zA-Z0-9_.-]+$", owner) or not re.match(r"^[a-zA-Z0-9_.-]+$", repo):
        raise GitHubIngestError("Invalid repository owner or name format.")
        
    extracted_branch = None
    # If URL includes /tree/<branch>
    if len(path_parts) >= 4 and path_parts[2] == "tree":
        extracted_branch = path_parts[3]
        
    return owner, repo, extracted_branch

async def fetch_github_repo_metadata(owner: str, repo: str) -> dict:
    """Attempt to fetch public repository metadata from GitHub REST API."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "User-Agent": "RepoMind-RAG-System/1.0",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            resp = await client.get(api_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "default_branch": data.get("default_branch", "main"),
                    "description": data.get("description", ""),
                    "stars": data.get("stargazers_count", 0),
                    "full_name": data.get("full_name", f"{owner}/{repo}")
                }
    except Exception:
        pass
    return {"default_branch": "main", "description": "", "stars": 0, "full_name": f"{owner}/{repo}"}

async def download_github_repo(repo_url: str, target_dir: Path, branch: str = "main") -> tuple[str, int]:
    """
    Safely download a public GitHub repository zipball and extract it.
    Returns (repo_name, total_files).
    """
    owner, repo, url_branch = validate_github_url(repo_url)
    target_dir = Path(target_dir).resolve()
    
    # Ensure parent directories exist
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine branch priority
    candidate_branches = []
    if url_branch:
        candidate_branches.append(url_branch)
    if branch and branch not in candidate_branches:
        candidate_branches.append(branch)
        
    # Fetch metadata for default branch if needed
    meta = await fetch_github_repo_metadata(owner, repo)
    default_branch = meta.get("default_branch", "main")
    if default_branch not in candidate_branches:
        candidate_branches.append(default_branch)
        
    for fallback_b in ["main", "master", "HEAD"]:
        if fallback_b not in candidate_branches:
            candidate_branches.append(fallback_b)
            
    zip_bytes = None
    successful_branch = None
    last_error_code = None
    
    client_limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    headers = {"User-Agent": "RepoMind-RAG-System/1.0"}
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=35.0, limits=client_limits) as client:
        for b in candidate_branches:
            # 1. Try codeload zip URL
            urls_to_try = [
                f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{b}",
                f"https://github.com/{owner}/{repo}/archive/refs/heads/{b}.zip",
                f"https://api.github.com/repos/{owner}/{repo}/zipball/{b}"
            ]
            for zip_url in urls_to_try:
                try:
                    resp = await client.get(zip_url, headers=headers)
                    if resp.status_code == 200 and len(resp.content) > 100:
                        # Verify zip magic bytes (PK\x03\x04)
                        if resp.content[:2] == b"PK":
                            zip_bytes = resp.content
                            successful_branch = b
                            break
                    elif resp.status_code in (404, 403):
                        last_error_code = resp.status_code
                except Exception:
                    continue
            if zip_bytes:
                break
                
    if not zip_bytes:
        if last_error_code == 404:
            raise GitHubIngestError(
                f"Repository '{owner}/{repo}' not found on GitHub. Verify the URL is public and spelled correctly."
            )
        elif last_error_code == 403:
            raise GitHubIngestError(
                f"GitHub API rate limit or access denied for '{owner}/{repo}'. Please try again in a few minutes."
            )
        else:
            raise GitHubIngestError(
                f"Could not download repository '{owner}/{repo}'. Please check repository visibility, URL, and network connection."
            )
            
    # Write to temporary file in target_dir.parent
    temp_zip = target_dir.parent / f"temp_{owner}_{repo}_{os.getpid()}.zip"
    temp_extract = target_dir.parent / f"extract_{owner}_{repo}_{os.getpid()}"
    
    try:
        with open(temp_zip, "wb") as f:
            f.write(zip_bytes)
            
        temp_extract.mkdir(parents=True, exist_ok=True)
        file_count, _ = extract_safe_zip(temp_zip, temp_extract)
        
        # Check if archive extracted into a single top-level folder (standard GitHub zipball structure)
        subdirs = [p for p in temp_extract.iterdir() if p.is_dir()]
        files_at_root = [p for p in temp_extract.iterdir() if p.is_file()]
        
        # Clear target_dir if anything exists
        for item in target_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                try:
                    item.unlink()
                except OSError:
                    pass
                    
        if len(subdirs) == 1 and len(files_at_root) == 0:
            source_folder = subdirs[0]
            for item in source_folder.iterdir():
                dest = target_dir / item.name
                shutil.move(str(item), str(target_dir))
        else:
            for item in temp_extract.iterdir():
                dest = target_dir / item.name
                shutil.move(str(item), str(target_dir))
                
        return repo, file_count
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except OSError:
                pass
        if temp_extract.exists():
            shutil.rmtree(temp_extract, ignore_errors=True)
