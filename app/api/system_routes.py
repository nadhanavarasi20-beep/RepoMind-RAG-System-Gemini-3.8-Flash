from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from app.auth import get_current_user
from app.models.schemas import GeminiStatusResponse, SettingsUpdateRequest
from app.gemini.client import gemini_client
from app.config import settings

router = APIRouter(prefix="/api/system", tags=["System & Settings"])

@router.get("/gemini-status", response_model=GeminiStatusResponse)
async def get_gemini_status(force: bool = False, current_user: dict = Depends(get_current_user)):
    is_avail, code, msg = await gemini_client.verify_model_availability(force_check=force)
    return GeminiStatusResponse(
        configured_model=gemini_client.get_configured_model(),
        api_key_configured=bool(gemini_client.api_key),
        verified_available=is_avail,
        status_code=code,
        status_message=msg,
        last_checked=datetime.now(timezone.utc).isoformat(),
        quota_limited=gemini_client.is_quota_limited()
    )

@router.post("/settings")
async def update_system_settings(payload: SettingsUpdateRequest, current_user: dict = Depends(get_current_user)):
    gemini_client.update_credentials(
        api_key=payload.gemini_api_key,
        model=payload.gemini_model
    )
    is_avail, code, msg = await gemini_client.verify_model_availability(force_check=True)
    return {
        "message": "Settings updated successfully.",
        "configured_model": gemini_client.get_configured_model(),
        "api_key_configured": bool(gemini_client.api_key),
        "verified_available": is_avail,
        "status_code": code,
        "status_message": msg
    }

@router.get("/models")
async def get_available_models(current_user: dict = Depends(get_current_user)):
    models = await gemini_client.list_available_models()
    return {"models": models}
