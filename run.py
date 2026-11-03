import sys
import os
from pathlib import Path
import uvicorn

# Ensure the root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.database import init_db

BANNER = r"""
  ____                      __  __ _           _ 
 |  _ \ ___ _ __   ___     |  \/  (_)_ __   __| |
 | |_) / _ \ '_ \ / _ \ ___| |\/| | | '_ \ / _` |
 |  _ <  __/ |_) | (_) |___| |  | | | | | | (_| |
 |_| \_\___| .__/ \___/    |_|  |_|_|_| |_|\__,_|
           |_|                                   
    RAG System - Gemini 3.8 Flash Codebase Intelligence
"""

def main():
    print(BANNER)
    print(f"[*] Environment: Python {sys.version.split()[0]}")
    print(f"[*] Configured Model: {settings.GEMINI_MODEL}")
    print(f"[*] Storage Directory: {settings.STORAGE_DIR}")
    
    if settings.GEMINI_API_KEY:
        masked_key = settings.GEMINI_API_KEY[:6] + "..." + settings.GEMINI_API_KEY[-4:] if len(settings.GEMINI_API_KEY) > 10 else "***"
        print(f"[*] Gemini API Key: Configured ({masked_key})")
    else:
        print("[!] Gemini API Key: Not set in .env (Add it to .env or in the Settings modal)")

    # Initialize local SQLite tables
    init_db()
    print("[*] Local database initialized.")

    port = settings.PORT
    # Check if port is already in use
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        is_in_use = (s.connect_ex((settings.HOST, port)) == 0)
    
    if is_in_use:
        print(f"[!] Warning: Port {port} is already in use by another process.")
        port = port + 1
        print(f"[*] Automatically selecting next available port: {port}")

    url = f"http://{settings.HOST}:{port}"
    print(f"\n[+] RepoMind is running at: {url}")
    print(f"[+] Open {url} in your browser to access the application.\n")

    try:
        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=port,
            reload=False,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[*] RepoMind server stopped by user.")

if __name__ == "__main__":
    main()
