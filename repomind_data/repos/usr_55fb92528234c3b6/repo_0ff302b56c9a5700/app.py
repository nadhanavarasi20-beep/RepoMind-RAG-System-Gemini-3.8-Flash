from pathlib import Path
from typing import Optional
import json, uuid, logging
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from engine import build_product_pack, safe_filename

BASE = Path(__file__).resolve().parent
OUT = BASE / "outputs"
OUT.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studio")

app = FastAPI(title="Multimodal Product Intelligence & Content Studio", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Multimodal Product Intelligence & Content Studio"}

@app.post("/api/generate")
async def generate(
    product_name: str = Form(""),
    category: str = Form(""),
    audience: str = Form(""),
    tone: str = Form("Confident & clear"),
    image: Optional[UploadFile] = File(None),
    spec_pdf: Optional[UploadFile] = File(None),
    reviews_file: Optional[UploadFile] = File(None),
    reviews_text: str = Form("")
):
    rid = uuid.uuid4().hex[:10]
    try:
        image_data = await image.read() if image and image.filename else None
        pdf_data = await spec_pdf.read() if spec_pdf and spec_pdf.filename else None
        review_data = await reviews_file.read() if reviews_file and reviews_file.filename else b""
        if image_data and len(image_data) > 12 * 1024 * 1024:
            raise HTTPException(413, "Image exceeds 12 MB.")
        if pdf_data and len(pdf_data) > 15 * 1024 * 1024:
            raise HTTPException(413, "PDF exceeds 15 MB.")
        if len(review_data) > 5 * 1024 * 1024:
            raise HTTPException(413, "Reviews file exceeds 5 MB.")
        if not any([product_name.strip(), image_data, pdf_data, reviews_text.strip(), review_data.strip()]):
            raise HTTPException(400, "Add at least one product detail or input file.")
        all_reviews = (reviews_text + "\n" + review_data.decode("utf-8-sig", errors="replace")).strip()
        result = build_product_pack(
            product_name=product_name.strip(), category=category.strip(), audience=audience.strip(),
            tone=tone, image_data=image_data, image_name=image.filename if image else "",
            pdf_data=pdf_data, reviews=all_reviews
        )
        result["request_id"] = rid
        filename = f"content_pack_{rid}.json"
        (OUT / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["download_url"] = f"/api/download/{filename}"
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected failure [%s]", rid)
        raise HTTPException(500, f"Unexpected processing error. Reference: {rid}. Check the terminal for details.")

@app.get("/api/download/{filename}")
async def download(filename: str):
    path = OUT / safe_filename(filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Report not found.")
    return FileResponse(path, media_type="application/json", filename=path.name)
