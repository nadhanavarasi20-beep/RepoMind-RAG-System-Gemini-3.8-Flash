# RepoMind – RAG System – Gemini 3.8 Flash

**RepoMind** is an enterprise-grade AI codebase intelligence and Modular RAG (Retrieval-Augmented Generation) application designed for developers to analyze, search, and understand software repositories.

Powered by **Gemini 3.8 Flash**, Python AST / multi-language syntax parsing, local dense vector embeddings, Rank-BM25 lexical search, and reciprocal rank fusion (RRF), RepoMind provides deeply grounded explanations with verifiable source citations, dependency graphs, and automated RAG evaluation metrics.

---

## 🌟 Key Features

### 1. Multi-Agent Workflow Engine
- **Ingestion Agent**: Validates ZIP uploads, enforces strict ZipSlip / Zip Bomb protection, and checks public GitHub URLs against SSRF vulnerabilities.
- **AST Parser Agent**: Extracts classes, methods, docstrings, imports, decorators, and function calls using Python native `ast` and multi-language syntax matchers (JS/TS, Go, Rust, Java, C++).
- **Chunker & Index Agent**: Code-aware semantic chunking respecting function and class boundaries; builds 384-dimensional dense semantic vectors and Rank-BM25 lexical indexes locally.
- **Hybrid Search Agent**: Combines dense semantic vector search with Okapi BM25 using Reciprocal Rank Fusion (RRF) and normalized weighted scoring ($\alpha \cdot \text{Vector} + (1 - \alpha) \cdot \text{BM25}$).
- **Synthesis & Citation Agent**: Injects retrieved code chunks into Gemini 3.8 Flash with instructions to cite exact file paths and line ranges (`[path/to/file.ext:start_line-end_line]`).
- **RAG Evaluator Agent**: Computes automated real-time quality scores: Context Relevance, Answer Groundedness, Faithfulness, and Inference Latency.

### 2. Full-Page Authentication & Registration
- Complete full-page login and registration experience.
- Uses real user credentials with secure PBKDF2-HMAC-SHA256 password hashing (100,000 rounds) and JWT authentication tokens.
- No demo credentials; each user's repositories and conversation sessions are isolated in the local SQLite database (`repomind.db`).

### 3. Critical Reliability & Zero-Hallucination Policy
- **Configured Model**: `gemini-3.8-flash` is the default and configured model.
- **Zero Silent Fallback**: The system **never silently switches models** or fabricates AI answers.
- **Quota & Error Resilience**: Catches HTTP 404 (model endpoint not found), HTTP 429 (quota exceeded), HTTP 529 / 503 (server overloaded), and network timeouts without crashing.
- **Quota-Aware Handling**: Does not repeatedly hammer the API when rate-limited.
- **Preserved Evidence Mode**: If Gemini is quota-limited or unavailable, RepoMind preserves repository indexing and displays the exact retrieved code evidence, match scores, and citations so developers still get codebase intelligence.

### 4. Futuristic Neon UI Design
- Styled with electric neon accents: **Electric Lime** (`#10b981`), **Neon Violet** (`#8b5cf6`), and **Cyber Teal** (`#06b6d4`) on a slightly dark graphite canvas (`#0c0f17`).
- Smooth glassmorphism, glowing status pills, agent telemetry displays, and responsive layouts.
- **Interactive Code Explorer**: Hierarchical directory tree, numbered code viewer, and direct "Ask AI About This File" action.
- **Interactive Dependency Graph**: Force-directed module architecture visualization showing internal imports and third-party packages.
- **Retrieved Evidence Drawer**: Side-by-side inspection of all candidate code chunks, similarity scores, and syntax snippets.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Backend Framework** | Python 3.11, FastAPI, Uvicorn |
| **AI / LLM** | Google Gemini API (`gemini-3.8-flash`) |
| **Parsing & AST** | Python `ast`, Multi-Language Tokenizer (JS/TS, Go, Rust, Java, C++) |
| **Lexical Search** | `rank-bm25` (Okapi BM25 with code-aware camelCase/snake_case tokenization) |
| **Vector Search** | Local 384-dimensional dense semantic projection & cosine matrix similarity |
| **Fusion Algorithm** | Reciprocal Rank Fusion (RRF) + Normalized Weighted Blending |
| **Security & Auth** | PBKDF2-HMAC-SHA256, JWT (`python-jose`), SSRF and ZipSlip validation |
| **Database** | SQLite3 (`repomind.db`) |
| **Frontend** | Vanilla ES6 JavaScript, HTML5, CSS3 with Electric Neon Graphite styling |

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.11+
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/)

### 2. Configure Environment
A template file `.env.example` is provided. Copy or edit `.env`:

```bash
# In the project directory:
cp .env.example .env
```

Open `.env` and insert your Gemini API Key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash
```

*(Note: You can also enter or test your Gemini API Key directly inside the application UI via the Settings modal).*

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
Start RepoMind with:

```bash
python run.py
```

### 5. Access the Web Application
Open your browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 📖 Usage Walkthrough

1. **Create an Account**:
   - On first launch, the full-page Auth screen appears.
   - Click **Create Account**, enter your name, email, and password, and click **Create My Account**.
2. **Ingest a Repository**:
   - In the **Dashboard**, click **Ingest Repository**.
   - Choose either:
     - **ZIP Archive Upload**: Select any `.zip` archive containing source code (up to 50MB).
     - **Public GitHub URL**: Enter any public repository URL (e.g. `https://github.com/psf/requests`).
   - Watch the **Agent Workflow Visualizer** transition through Ingest, AST Parsing, and Indexing in real time.
3. **Explore Code & Dependencies**:
   - Switch to **Code Explorer** to browse files, view lines of code, and click **Ask AI About This File**.
   - Switch to **Dependency Graph** to interactively visualize module imports and relationships.
4. **Chat with AI Intelligence**:
   - Switch to **AI Intelligence** tab.
   - Ask complex architectural questions:
     - *"How does request authentication and token verification work?"*
     - *"Trace the end-to-end data flow from API endpoint to the database."*
     - *"Where is error handling implemented for network timeouts?"*
   - Review the verified source citations (`[auth.py:45-78]`), click them to view the exact code snippet, inspect the **RAG Scorecard** (Relevance, Groundedness, Faithfulness), and explore the **Code Evidence Drawer**.

---

## 🔒 Security Architecture

- **Path Traversal / ZipSlip Prevention**: Archive extraction explicitly verifies that every destination path resolves strictly within the target sandbox directory.
- **SSRF Prevention**: GitHub ingestion validates that URLs strictly belong to `github.com` with HTTPS, disallowing internal IP addresses and loopbacks.
- **Zero Remote Code Execution**: Repository files are only parsed statically as text and AST syntax trees; no repository code or scripts are ever executed.
- **Password Security**: Passwords are never stored in plaintext; they are salted and hashed using PBKDF2 with 100,000 iterations.
