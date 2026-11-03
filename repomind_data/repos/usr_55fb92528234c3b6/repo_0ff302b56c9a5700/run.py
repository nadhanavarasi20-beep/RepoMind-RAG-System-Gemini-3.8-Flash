from pathlib import Path
import os
from dotenv import load_dotenv
import uvicorn

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
host = os.getenv("HOST", "127.0.0.1")
port = int(os.getenv("PORT", "8000"))
if __name__ == "__main__":
    uvicorn.run("app:app", host=host, port=port, reload=False)
