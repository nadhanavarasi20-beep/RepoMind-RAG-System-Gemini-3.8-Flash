# Multimodal Product Intelligence & Content Studio

A single-folder FastAPI application that accepts a product image, PDF specification sheet, and customer reviews, then produces a structured product content pack.

## What it generates
- Product description
- Key features
- FAQs
- Advertisement headline, body and CTA
- Instagram, LinkedIn and short social captions
- Consistency and claims checklist
- Downloadable JSON report
- Visible multi-agent workflow status

## Important reliability design
The application has a **local-first workflow**. PDF text extraction, basic review analysis, structured content generation, validation and report export work without an external AI API. Gemini is an optional enhancement. If Gemini returns quota, 503/504, timeout, invalid JSON or another API error, the app keeps the locally generated content and does not crash.

**Honest capability note:** without a working multimodal model, local image handling reads image format/dimensions only; it does not identify objects or interpret visual details. Scanned PDFs may not contain extractable text and require OCR. For true visual understanding, configure a valid Gemini API key with available quota.

## Requirements
- Python 3.10 or newer
- Internet only for installing dependencies and optional Gemini API use

## Windows setup (VS Code / PowerShell)
Open this project folder in VS Code. In the terminal:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

If `py -3.11` is unavailable, use `python -m venv .venv` with an installed Python 3.10+ version.

Open:
- App: http://127.0.0.1:8000
- Health check: http://127.0.0.1:8000/api/health
- API docs: http://127.0.0.1:8000/docs

## Optional Gemini enhancement
1. Create an API key in Google AI Studio.
2. Put it in `.env`:
   `GEMINI_API_KEY=your_key_here`
3. Keep `GEMINI_MODEL=gemini-2.5-flash` or set a model currently available to your API key.
4. Restart the server after changing `.env`.

The app loads `.env` automatically through `python-dotenv`? For this version, environment variables are read from the process. To load `.env` automatically, run with the included launcher `run.py` (recommended), which loads dotenv before starting Uvicorn.

## Run using launcher (recommended)
```powershell
python run.py
```

## Inputs
- Image: PNG, JPG, WEBP (12 MB max)
- Specification: text-based PDF (15 MB max)
- Reviews: TXT or CSV (5 MB max), or paste text

At least one product detail or source is required. Best results come from adding product name, category, audience, and the source files.

## Output
JSON reports are saved in `outputs/`. The browser also provides a download link after generation.

## Troubleshooting
- Port already in use: change port in `run.py` or stop the process using port 8000.
- PDF says no text extracted: the PDF may be scanned; run OCR separately or provide a text-based PDF.
- Gemini quota/API failure: local content generation still completes; check Google AI Studio usage if you need Gemini enhancement.
- Missing package: activate `.venv`, then run `pip install -r requirements.txt`.

## Privacy
Do not commit `.env`, API keys, private customer data or confidential product documents. The app stores generated JSON reports locally in `outputs/`.
