import os
from pathlib import Path
from typing import Optional, Set

IGNORED_DIRECTORIES: Set[str] = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", "venv", ".venv", "env", ".env", "dist", "build",
    "target", ".next", ".nuxt", ".turbo", "bin", "obj", ".idea", ".vscode"
}

IGNORED_EXTENSIONS: Set[str] = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".pyo", ".pyd",
    ".iso", ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf", ".png",
    ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".mp4", ".mp3",
    ".wav", ".ogg", ".woff", ".woff2", ".ttf", ".eot", ".lock", ".log"
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".md": "markdown",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".sh": "bash",
    ".bash": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".rb": "ruby",
    ".php": "php"
}

MAX_FILE_BYTES = 1_500_000  # 1.5 MB limit per source file

def is_text_file(filepath: Path) -> bool:
    """Check if file is text and decodable as utf-8 or ascii without null bytes."""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(4096)
            if b'\x00' in chunk:
                return False
            chunk.decode('utf-8')
            return True
    except Exception:
        return False

def should_index_file(filepath: Path, base_dir: Path) -> bool:
    """Filter files based on ignore list, extension, size, and binary check."""
    rel_path = filepath.relative_to(base_dir)
    
    # Check directory parts
    for part in rel_path.parts[:-1]:
        if part in IGNORED_DIRECTORIES or part.startswith("."):
            return False
            
    # Check file name and extension
    name = filepath.name
    if name.startswith(".") and name not in {".env.example", ".gitignore"}:
        return False
        
    ext = filepath.suffix.lower()
    if ext in IGNORED_EXTENSIONS:
        return False
        
    # Check size
    try:
        if filepath.stat().st_size > MAX_FILE_BYTES:
            return False
    except OSError:
        return False
        
    # Language or extension check
    if ext not in LANGUAGE_BY_EXTENSION and not is_text_file(filepath):
        return False
        
    return True

def detect_language(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    return LANGUAGE_BY_EXTENSION.get(ext, "text")
