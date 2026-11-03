from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates

from app import auth, database
from app.models import Token, UserInDB

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------- register ---
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = await auth.get_current_user_optional(request)
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@router.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Passwords do not match."},
            status_code=400,
        )
    if database.get_user(username):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "That username is already taken."},
            status_code=400,
        )
    hashed = auth.hash_password(password)
    database.create_user(username, email, hashed)
    return RedirectResponse("/login?registered=1", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------- login ---
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, registered: str = None):
    user = await auth.get_current_user_optional(request)
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "just_registered": bool(registered)},
    )


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    user = auth.authenticate_user(username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password.", "just_registered": False},
            status_code=401,
        )
    access_token = auth.create_access_token(data={"sub": user["username"]})
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=auth.COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


# --------------------------------------------------------------- logout ---
@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(auth.COOKIE_NAME)
    return response


# ------------------------------------------------------- OAuth2 /token ----
@router.post("/token", response_model=Token)
async def issue_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Standard OAuth2 password-flow token endpoint (useful for API clients,
    Swagger UI's 'Authorize' button, and Postman)."""
    user = auth.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = auth.create_access_token(data={"sub": user["username"]})
    return Token(access_token=access_token)


# --------------------------------------------------------- session info --
@router.get("/session-info")
async def session_info(current_user: UserInDB = Depends(auth.get_current_active_user)):
    return JSONResponse({
        "logged_in": True,
        "username": current_user.username,
        "email": current_user.email,
    })


@router.get("/session-data")
async def session_data(current_user: UserInDB = Depends(auth.get_current_active_user)):
    history = database.get_history_for_user(current_user.username)
    return JSONResponse({
        "username": current_user.username,
        "total_queries": len(history),
        "recent_categories": [h["category"] for h in history[:5]],
    })
