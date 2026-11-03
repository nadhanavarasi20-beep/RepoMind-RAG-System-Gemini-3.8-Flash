import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import database, gemini_utils
from app.auth import get_current_active_user
from app.models import UserInDB

router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------ dashboard ---
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    history = database.get_history_for_user(current_user.username)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": current_user, "history": history[:5], "total": len(history)},
    )


# ---------------------------------------------------------- home planner --
@router.get("/planner/home", response_class=HTMLResponse)
async def home_planner_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    return templates.TemplateResponse("home_planner.html", {"request": request, "user": current_user})


@router.post("/generate-home", response_class=HTMLResponse)
async def generate_home(
    request: Request,
    budget: float = Form(...),
    room_types: str = Form(...),
    items: str = Form(...),
    style_preference: str = Form("Modern"),
    current_user: UserInDB = Depends(get_current_active_user),
):
    result = gemini_utils.get_home_recommendations(budget, room_types, items, style_preference)
    input_data = {
        "budget": budget, "room_types": room_types, "items": items, "style_preference": style_preference,
    }
    database.add_history_entry(current_user.username, "Home", input_data, result)
    return templates.TemplateResponse(
        "recommendations.html",
        {
            "request": request, "user": current_user, "category": "Home Interior",
            "input_data": input_data, "result": result,
        },
    )


# --------------------------------------------------------- party planner --
@router.get("/planner/party", response_class=HTMLResponse)
async def party_planner_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    return templates.TemplateResponse("party_planner.html", {"request": request, "user": current_user})


@router.post("/generate-party", response_class=HTMLResponse)
async def generate_party(
    request: Request,
    budget: float = Form(...),
    guest_count: int = Form(...),
    event_type: str = Form(...),
    venue_preference: str = Form("Any"),
    location: str = Form(""),
    current_user: UserInDB = Depends(get_current_active_user),
):
    result = gemini_utils.get_party_recommendations(budget, guest_count, event_type, venue_preference, location)
    input_data = {
        "budget": budget, "guest_count": guest_count, "event_type": event_type,
        "venue_preference": venue_preference, "location": location,
    }
    database.add_history_entry(current_user.username, "Party", input_data, result)
    return templates.TemplateResponse(
        "recommendations.html",
        {
            "request": request, "user": current_user, "category": "Party Planning",
            "input_data": input_data, "result": result,
        },
    )


# ------------------------------------------------------- jewelry planner --
@router.get("/planner/jewelry", response_class=HTMLResponse)
async def jewelry_planner_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Jewelry budget planner page"""
    return templates.TemplateResponse("jewelry_planner.html", {"request": request, "user": current_user})


@router.post("/generate-jewelry", response_class=HTMLResponse)
async def generate_jewelry(
    request: Request,
    budget: float = Form(...),
    occasion: str = Form(...),
    style_preference: str = Form("Traditional"),
    outfit_image: Optional[UploadFile] = File(None),
    current_user: UserInDB = Depends(get_current_active_user),
):
    image_bytes = None
    saved_image_url = None
    if outfit_image is not None and outfit_image.filename:
        image_bytes = await outfit_image.read()
        if image_bytes:
            ext = Path(outfit_image.filename).suffix or ".jpg"
            fname = f"{uuid.uuid4().hex}{ext}"
            with open(UPLOAD_DIR / fname, "wb") as f:
                f.write(image_bytes)
            saved_image_url = f"/static/uploads/{fname}"

    result = gemini_utils.get_jewelry_recommendations(budget, occasion, style_preference, image_bytes)
    input_data = {
        "budget": budget, "occasion": occasion, "style_preference": style_preference,
        "outfit_image_url": saved_image_url,
    }
    database.add_history_entry(current_user.username, "Jewelry", input_data, result)
    return templates.TemplateResponse(
        "recommendations.html",
        {
            "request": request, "user": current_user, "category": "Jewelry",
            "input_data": input_data, "result": result,
        },
    )


# ---------------------------------------------------- recommendation api --
@router.get("/recommendations-details/{entry_id}")
async def recommendation_details(entry_id: str, current_user: UserInDB = Depends(get_current_active_user)):
    history = database.get_history_for_user(current_user.username)
    for entry in history:
        if entry["id"] == entry_id:
            return JSONResponse(entry)
    return JSONResponse({"error": "Not found"}, status_code=404)


# --------------------------------------------------------------- history --
@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    history = database.get_history_for_user(current_user.username)
    return templates.TemplateResponse(
        "history.html", {"request": request, "user": current_user, "history": history}
    )
