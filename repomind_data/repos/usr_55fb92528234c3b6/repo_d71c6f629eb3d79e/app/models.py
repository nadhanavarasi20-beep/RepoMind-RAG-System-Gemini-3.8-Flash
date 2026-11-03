from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ------------------------------------------------------------------ auth ---
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserInDB(BaseModel):
    username: str
    email: str
    hashed_password: str
    created_at: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


# -------------------------------------------------------------- planners ---
class HomePlannerInput(BaseModel):
    budget: float
    room_types: str          # e.g. "Living Room, Kitchen, Bedroom"
    items: str                # e.g. "2 ceiling fans, 1 dining table, 4 lights"
    style_preference: Optional[str] = "Modern"


class PartyPlannerInput(BaseModel):
    budget: float
    guest_count: int
    event_type: str          # birthday / wedding / corporate ...
    venue_preference: Optional[str] = "Any"
    location: Optional[str] = ""


class JewelryPlannerInput(BaseModel):
    budget: float
    occasion: str
    style_preference: Optional[str] = "Traditional"
