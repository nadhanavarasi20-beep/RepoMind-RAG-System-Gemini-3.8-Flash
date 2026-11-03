"""
Very small JSON-file 'database' so the project can be cloned and run
immediately without installing/configuring Postgres, MySQL, etc.

Two files live under /data:
  - users.json    -> {username: {username, email, hashed_password, created_at}}
  - history.json  -> [{id, username, category, input, result, created_at}]

Swap this module out for a real database (SQLAlchemy, MongoDB, etc.) later
without touching the routes - they only call the functions below.
"""
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
HISTORY_FILE = DATA_DIR / "history.json"

_lock = threading.Lock()


def _load(path: Path):
    if not path.exists():
        return {} if path == USERS_FILE else []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return {} if path == USERS_FILE else []
        return json.loads(content)


def _save(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# ---------------------------------------------------------------- users ---
def get_user(username: str) -> Optional[dict]:
    users = _load(USERS_FILE)
    return users.get(username.lower())


def create_user(username: str, email: str, hashed_password: str) -> dict:
    with _lock:
        users = _load(USERS_FILE)
        key = username.lower()
        if key in users:
            raise ValueError("Username already exists")
        user = {
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        users[key] = user
        _save(USERS_FILE, users)
        return user


# -------------------------------------------------------------- history ---
def add_history_entry(username: str, category: str, input_data: dict, result: dict) -> dict:
    with _lock:
        history = _load(HISTORY_FILE)
        entry = {
            "id": str(uuid.uuid4()),
            "username": username,
            "category": category,
            "input": input_data,
            "result": result,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        history.append(entry)
        _save(HISTORY_FILE, history)
        return entry


def get_history_for_user(username: str) -> list:
    history = _load(HISTORY_FILE)
    return [h for h in history if h["username"].lower() == username.lower()][::-1]
