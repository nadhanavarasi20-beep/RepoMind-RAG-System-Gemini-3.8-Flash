import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.config import settings

DB_PATH = settings.STORAGE_DIR / "repomind.db"

def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables with indexes."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)
        
        # Repositories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repositories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT,
                disk_path TEXT NOT NULL,
                total_files INTEGER DEFAULT 0,
                total_lines INTEGER DEFAULT 0,
                total_symbols INTEGER DEFAULT 0,
                languages_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                status_message TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Indexed Files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                language TEXT,
                lines_count INTEGER DEFAULT 0,
                symbols_count INTEGER DEFAULT 0,
                indexed_at TEXT NOT NULL,
                FOREIGN KEY (repo_id) REFERENCES repositories (id) ON DELETE CASCADE
            )
        """)
        
        # Chat Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (repo_id) REFERENCES repositories (id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        
        # Chat Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                citations_json TEXT DEFAULT '[]',
                eval_json TEXT DEFAULT '{}',
                evidence_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_user ON repositories (user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_repo ON indexed_files (repo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_repo ON chat_sessions (repo_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_msgs_session ON chat_messages (session_id)")
        
        conn.commit()
