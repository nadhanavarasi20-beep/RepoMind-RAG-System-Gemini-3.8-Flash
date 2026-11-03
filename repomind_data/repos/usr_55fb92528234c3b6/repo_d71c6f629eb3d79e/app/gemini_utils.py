"""
gemini_utils.py
----------------
Central AI service layer for PocketSmart AI.

Responsibilities:
  - Configure the Gemini client from the GEMINI_API_KEY env var
  - Build category-specific prompts (home / party / jewelry)
  - Call Gemini (text-only, or text + image for the jewelry planner)
  - Parse the model's JSON response into a predictable structure
  - Fall back to a safe, deterministic mock response if the API key is
    missing, the call fails, or Gemini returns something unparsable, so the
    rest of the app (and a demo/interview) never breaks on a flaky network
    or quota error.
"""
import json
import os
import re
from io import BytesIO
from typing import Optional

import google.generativeai as genai
from PIL import Image

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

_model = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL_NAME)


PLATFORMS_BY_CATEGORY = {
    "home": ["Amazon", "Flipkart", "IKEA"],
    "party": ["Swiggy", "Zomato", "OYO", "Amazon"],
    "jewelry": ["Amazon", "Flipkart"],
}


def _extract_json(text: str) -> Optional[dict]:
    """Gemini sometimes wraps JSON in ```json fences or adds stray text -
    strip that and parse the first {...} block we can find."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _call_gemini(prompt: str, image: Optional[Image.Image] = None) -> Optional[dict]:
    if _model is None:
        return None
    try:
        if image is not None:
            response = _model.generate_content([prompt, image])
        else:
            response = _model.generate_content(prompt)
        return _extract_json(response.text)
    except Exception as exc:  # noqa: BLE001 - we deliberately want a soft fallback
        print(f"[gemini_utils] Gemini call failed, using fallback data: {exc}")
        return None


def _budget_split(total: float, weights: dict) -> dict:
    return {k: round(total * w, 2) for k, w in weights.items()}


# --------------------------------------------------------------- HOME -----
def get_home_recommendations(budget: float, room_types: str, items: str,
                              style_preference: str = "Modern") -> dict:
    prompt = f"""
You are PocketSmart AI's home interior budgeting assistant.

User budget: ₹{budget}
Rooms: {room_types}
Items needed: {items}
Style preference: {style_preference}

Split the budget sensibly across the requested items and suggest realistic,
budget-appropriate product ideas for each item, referencing plausible
platforms from this list: {PLATFORMS_BY_CATEGORY['home']}.

Respond with ONLY valid JSON in exactly this shape, no commentary:
{{
  "total_budget": {budget},
  "summary": "<one paragraph summary of the plan>",
  "items": [
    {{
      "name": "<item name>",
      "allocated_budget": <number>,
      "platform": "<one of Amazon/Flipkart/IKEA>",
      "suggestion": "<short product suggestion with style notes>",
      "estimated_price_range": "<e.g. ₹2,000 - ₹3,500>"
    }}
  ],
  "tips": ["<budgeting or style tip 1>", "<tip 2>"]
}}
"""
    result = _call_gemini(prompt)
    if result:
        return result
    return _fallback_home(budget, room_types, items)


def _fallback_home(budget: float, room_types: str, items: str) -> dict:
    item_list = [i.strip() for i in re.split(r",|\n", items) if i.strip()] or ["Furniture", "Lighting", "Decor"]
    n = len(item_list)
    per_item = round(budget / max(n, 1), 2)
    return {
        "total_budget": budget,
        "summary": (
            f"A balanced plan for {room_types} split across {n} item group(s). "
            "This is a fallback estimate generated locally because the Gemini "
            "API was unavailable - connect a valid GEMINI_API_KEY for live, "
            "personalized recommendations."
        ),
        "items": [
            {
                "name": item,
                "allocated_budget": per_item,
                "platform": PLATFORMS_BY_CATEGORY["home"][idx % 3],
                "suggestion": f"Look for mid-range {item.lower()} options that balance durability and style.",
                "estimated_price_range": f"₹{int(per_item*0.8)} - ₹{int(per_item*1.2)}",
            }
            for idx, item in enumerate(item_list)
        ],
        "tips": [
            "Prioritize functional pieces (seating, lighting) before purely decorative ones.",
            "Compare the same product across platforms before purchasing.",
        ],
        "fallback": True,
    }


# -------------------------------------------------------------- PARTY -----
def get_party_recommendations(budget: float, guest_count: int, event_type: str,
                               venue_preference: str = "Any", location: str = "") -> dict:
    prompt = f"""
You are PocketSmart AI's party & event budgeting assistant.

User budget: ₹{budget}
Guest count: {guest_count}
Event type: {event_type}
Venue preference: {venue_preference}
Location: {location or "Not specified"}

Allocate the budget proportionally across catering, decoration, venue/
accommodation, and entertainment. Reference plausible platforms from this
list: {PLATFORMS_BY_CATEGORY['party']}.

Respond with ONLY valid JSON in exactly this shape, no commentary:
{{
  "total_budget": {budget},
  "summary": "<one paragraph plan summary tailored to the event type>",
  "categories": [
    {{
      "name": "Catering",
      "allocated_budget": <number>,
      "platform": "<Swiggy/Zomato>",
      "suggestion": "<menu / catering suggestion>"
    }},
    {{
      "name": "Venue/Accommodation",
      "allocated_budget": <number>,
      "platform": "OYO",
      "suggestion": "<venue suggestion>"
    }},
    {{
      "name": "Decoration",
      "allocated_budget": <number>,
      "platform": "Amazon",
      "suggestion": "<decoration suggestion>"
    }},
    {{
      "name": "Entertainment",
      "allocated_budget": <number>,
      "platform": "Amazon",
      "suggestion": "<entertainment suggestion>"
    }}
  ],
  "tips": ["<planning tip 1>", "<tip 2>"]
}}
"""
    result = _call_gemini(prompt)
    if result:
        return result
    return _fallback_party(budget, guest_count, event_type)


def _fallback_party(budget: float, guest_count: int, event_type: str) -> dict:
    split = _budget_split(budget, {
        "Catering": 0.45, "Venue/Accommodation": 0.25, "Decoration": 0.20, "Entertainment": 0.10
    })
    platforms = {"Catering": "Swiggy", "Venue/Accommodation": "OYO",
                 "Decoration": "Amazon", "Entertainment": "Amazon"}
    return {
        "total_budget": budget,
        "summary": (
            f"A proportional budget split for a {event_type} with {guest_count} guests. "
            "This is a fallback estimate generated locally because the Gemini "
            "API was unavailable - connect a valid GEMINI_API_KEY for live, "
            "personalized recommendations."
        ),
        "categories": [
            {
                "name": name,
                "allocated_budget": amount,
                "platform": platforms[name],
                "suggestion": f"Reasonable {name.lower()} options for a {guest_count}-guest {event_type}.",
            }
            for name, amount in split.items()
        ],
        "tips": [
            "Book venues and catering early for better rates.",
            "Keep a 5-10% contingency buffer for last-minute costs.",
        ],
        "fallback": True,
    }


# ------------------------------------------------------------ JEWELRY -----
def get_jewelry_recommendations(budget: float, occasion: str, style_preference: str = "Traditional",
                                 image_bytes: Optional[bytes] = None) -> dict:
    image = None
    image_note = "No outfit image provided."
    if image_bytes:
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image_note = "An outfit image was provided - consider its color palette."
        except Exception as exc:  # noqa: BLE001
            print(f"[gemini_utils] Could not open uploaded image: {exc}")

    prompt = f"""
You are PocketSmart AI's jewelry budgeting and styling assistant.

User budget: ₹{budget}
Occasion: {occasion}
Style preference: {style_preference}
{image_note}

Suggest jewelry pieces (e.g. necklace, earrings, bangles, ring) that fit the
budget and, if an outfit image is described, coordinate with its likely
color palette. Reference plausible platforms from this list:
{PLATFORMS_BY_CATEGORY['jewelry']}.

Respond with ONLY valid JSON in exactly this shape, no commentary:
{{
  "total_budget": {budget},
  "summary": "<one paragraph styling summary>",
  "items": [
    {{
      "name": "<piece name, e.g. Kundan Necklace Set>",
      "allocated_budget": <number>,
      "platform": "<Amazon/Flipkart>",
      "suggestion": "<short styling note>",
      "estimated_price_range": "<e.g. ₹3,000 - ₹5,000>"
    }}
  ],
  "color_notes": "<how the suggestions coordinate with the outfit, or general styling advice if no image>",
  "tips": ["<tip 1>", "<tip 2>"]
}}
"""
    result = _call_gemini(prompt, image=image)
    if result:
        return result
    return _fallback_jewelry(budget, occasion, style_preference, has_image=image is not None)


def _fallback_jewelry(budget: float, occasion: str, style_preference: str, has_image: bool) -> dict:
    pieces = ["Necklace Set", "Earrings", "Bangles"]
    split = _budget_split(budget, {"Necklace Set": 0.5, "Earrings": 0.3, "Bangles": 0.2})
    return {
        "total_budget": budget,
        "summary": (
            f"A {style_preference.lower()} jewelry set suited for {occasion}. "
            "This is a fallback estimate generated locally because the Gemini "
            "API was unavailable - connect a valid GEMINI_API_KEY for live, "
            "personalized recommendations."
        ),
        "items": [
            {
                "name": piece,
                "allocated_budget": amount,
                "platform": PLATFORMS_BY_CATEGORY["jewelry"][idx % 2],
                "suggestion": f"{style_preference} style {piece.lower()} appropriate for {occasion}.",
                "estimated_price_range": f"₹{int(amount*0.8)} - ₹{int(amount*1.2)}",
            }
            for idx, (piece, amount) in enumerate(split.items())
        ],
        "color_notes": (
            "Outfit image was received but could not be analyzed in fallback mode."
            if has_image else
            "No outfit image provided - gold and white-stone tones are safe defaults for most occasions."
        ),
        "tips": [
            "Match metal tone (gold/silver/rose-gold) to your outfit's dominant color.",
            "Save 10% of the budget for a statement piece if the occasion calls for it.",
        ],
        "fallback": True,
    }
