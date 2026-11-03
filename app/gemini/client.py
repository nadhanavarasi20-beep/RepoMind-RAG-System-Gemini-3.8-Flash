import asyncio
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import httpx

from app.config import settings

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

class GeminiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        fallback_model: Optional[str] = None
    ):
        self.api_key = settings.GEMINI_API_KEY if api_key is None else api_key
        self.model = settings.GEMINI_MODEL if model is None else model
        self.fallback_model = (
            settings.GEMINI_FALLBACK_MODEL if fallback_model is None else fallback_model
        )
        self._quota_limited_until: float = 0.0
        self._last_checked: str = ""
        self._last_verified: bool = False
        self._last_status_code: int = 200
        self._last_status_message: str = "Ready"
        self._cached_verify_time: float = 0.0
        self._response_cache: Dict[str, Dict[str, Any]] = {}

    def get_configured_model(self) -> str:
        return self.model

    def is_quota_limited(self) -> bool:
        return time.time() < self._quota_limited_until

    def update_credentials(self, api_key: Optional[str] = None, model: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key.strip()
        if model is not None:
            self.model = model.strip()
        self._quota_limited_until = 0.0
        self._cached_verify_time = 0.0
        self._response_cache.clear()

    @staticmethod
    def _clean_model_name(model: str) -> str:
        return model[7:] if model.startswith("models/") else model

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return f"HTTP {response.status_code}"
        error = data.get("error", {}) if isinstance(data, dict) else {}
        if isinstance(error, dict):
            return str(error.get("message") or f"HTTP {response.status_code}")[:500]
        return f"HTTP {response.status_code}"

    async def verify_model_availability(self, force_check: bool = False) -> Tuple[bool, int, str]:
        """
        Verify if the configured model is available.
        Uses a 5-minute memory cache to avoid burning Gemini API quota on every page refresh.
        """
        now = time.time()
        # Return cached verification if within 300 seconds and not forced
        if not force_check and (now - self._cached_verify_time < 300.0) and self._cached_verify_time > 0:
            return self._last_verified, self._last_status_code, self._last_status_message

        if not self.api_key:
            self._last_verified = False
            self._last_status_code = 401
            self._last_status_message = "Gemini API key is not configured in .env or settings."
            return False, 401, self._last_status_message
            
        clean_model = self._clean_model_name(self.model)
        url = f"{GEMINI_BASE_URL}/models/{clean_model}"
        
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers={"x-goog-api-key": self.api_key})
                self._last_checked = datetime.now(timezone.utc).isoformat()
                self._cached_verify_time = now
                self._last_status_code = resp.status_code
                
                if resp.status_code == 200:
                    self._last_verified = True
                    self._quota_limited_until = 0.0
                    self._last_status_message = f"Model '{self.model}' is verified and available on Gemini API."
                    return True, 200, self._last_status_message
                elif resp.status_code == 404:
                    self._last_verified = False
                    self._last_status_message = f"Configured model '{self.model}' was not found (HTTP 404)."
                    return False, 404, self._last_status_message
                elif resp.status_code == 429:
                    self._last_verified = False
                    self._quota_limited_until = now + 30.0  # Cool off for 30 seconds
                    self._last_status_message = "Gemini API quota or rate-limit exceeded (HTTP 429). Retries paused."
                    return False, 429, self._last_status_message
                elif resp.status_code in (400, 401, 403):
                    self._last_verified = False
                    msg = self._error_message(resp)
                    self._last_status_message = f"Authentication error: {msg}"
                    return False, resp.status_code, self._last_status_message
                elif resp.status_code in (503, 529):
                    self._last_verified = False
                    self._last_status_message = f"Model '{self.model}' is temporarily unavailable (HTTP {resp.status_code})."
                    return False, resp.status_code, self._last_status_message
                else:
                    self._last_status_message = f"API returned status HTTP {resp.status_code}."
                    return False, resp.status_code, self._last_status_message
        except httpx.TimeoutException:
            self._last_status_message = "Connection to Gemini API timed out."
            return False, 408, self._last_status_message
        except Exception as e:
            self._last_status_message = f"Network or connection error ({type(e).__name__})."
            return False, 500, self._last_status_message

    async def _generate_with_model(
        self,
        model: str,
        payload: Dict[str, Any],
        max_retries: int
    ) -> Dict[str, Any]:
        clean_model = self._clean_model_name(model)
        url = f"{GEMINI_BASE_URL}/models/{clean_model}:generateContent"

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": self.api_key
                        }
                    )
            except httpx.TimeoutException:
                return {
                    "success": False,
                    "status": "timeout",
                    "status_code": 408,
                    "error": f"Gemini request timed out after {settings.GEMINI_TIMEOUT_SECONDS}s.",
                    "content": "",
                    "model": model
                }
            except httpx.RequestError as exc:
                return {
                    "success": False,
                    "status": "network_error",
                    "status_code": 500,
                    "error": f"Gemini network request failed ({type(exc).__name__}).",
                    "content": "",
                    "model": model
                }

            try:
                data = response.json()
            except ValueError:
                data = {}

            if response.status_code == 200:
                candidates = data.get("candidates", []) if isinstance(data, dict) else []
                candidate = candidates[0] if candidates else {}
                candidate_content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
                parts = candidate_content.get("parts", []) if isinstance(candidate_content, dict) else []
                text = "".join(
                    part.get("text", "")
                    for part in parts
                    if isinstance(part, dict) and isinstance(part.get("text", ""), str)
                )
                if text.strip():
                    usage = data.get("usageMetadata", {})
                    if not isinstance(usage, dict):
                        usage = {}
                    return {
                        "success": True,
                        "status": "active",
                        "status_code": 200,
                        "content": text,
                        "model": model,
                        "tokens_used": usage.get("totalTokenCount", 0),
                        "error": None
                    }
                return {
                    "success": False,
                    "status": "empty_response",
                    "status_code": 200,
                    "error": "Gemini returned no text candidate.",
                    "content": "",
                    "model": model
                }

            detail = self._error_message(response)
            if response.status_code in (503, 529):
                if attempt < max_retries:
                    await asyncio.sleep(min(2.0, 0.5 * (2 ** attempt)))
                    continue
                return {
                    "success": False,
                    "status": "server_overload",
                    "status_code": response.status_code,
                    "error": f"Gemini server unavailable (HTTP {response.status_code}): {detail}",
                    "content": "",
                    "model": model
                }

            if response.status_code == 429:
                self._quota_limited_until = time.time() + 30.0
                return {
                    "success": False,
                    "status": "quota_exceeded",
                    "status_code": 429,
                    "error": f"Gemini quota or rate limit reached (HTTP 429): {detail}",
                    "content": "",
                    "model": model
                }

            if response.status_code in (400, 401, 403):
                invalid_key = response.status_code in (401, 403) or any(
                    marker in detail.lower()
                    for marker in ("api key not valid", "invalid api key", "api_key_invalid")
                )
                status = "authentication_error" if invalid_key else "api_error"
                return {
                    "success": False,
                    "status": status,
                    "status_code": response.status_code,
                    "error": f"Gemini authentication/API error (HTTP {response.status_code}): {detail}",
                    "content": "",
                    "model": model
                }

            if response.status_code == 404:
                return {
                    "success": False,
                    "status": "model_error",
                    "status_code": 404,
                    "error": f"Gemini model '{model}' was not found (HTTP 404).",
                    "content": "",
                    "model": model
                }

            status = "server_error" if response.status_code >= 500 else "api_error"
            return {
                "success": False,
                "status": status,
                "status_code": response.status_code,
                "error": f"Gemini API error (HTTP {response.status_code}): {detail}",
                "content": "",
                "model": model
            }

        return {
            "success": False,
            "status": "failed",
            "status_code": 500,
            "error": "Gemini failed to return a response.",
            "content": "",
            "model": model
        }

    async def generate_response(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
        cache_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if cache_key and cache_key in self._response_cache:
            cached = self._response_cache[cache_key]
            return {**cached, "cached": True}

        if not self.api_key:
            return {
                "success": False,
                "status": "missing_api_key",
                "status_code": 401,
                "error": "Gemini API key is not configured. Add your GEMINI_API_KEY to .env or in Settings.",
                "content": "",
                "model": self.model
            }

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "topP": 0.95
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        configured_retries = max(0, min(int(settings.GEMINI_MAX_RETRIES), 2))
        primary_model = self._clean_model_name(self.model)
        fallback_model = self._clean_model_name(self.fallback_model)
        primary_available = not self.is_quota_limited()
        if primary_available:
            primary_result = await self._generate_with_model(
                self.model,
                payload,
                configured_retries
            )
        else:
            wait_sec = max(1, int(self._quota_limited_until - time.time()))
            primary_result = {
                "success": False,
                "status": "quota_exceeded",
                "status_code": 429,
                "error": f"Gemini API rate limit active. Retry after {wait_sec}s.",
                "content": "",
                "model": self.model
            }

        fallback_eligible_statuses = {
            "server_overload",
            "server_error",
            "quota_exceeded",
            "timeout",
            "network_error",
            "model_error",
            "empty_response",
            "invalid_response"
        }
        can_try_fallback = (
            primary_result["status"] in fallback_eligible_statuses
            and fallback_model
            and fallback_model != primary_model
        )
        result = primary_result
        if can_try_fallback:
            result = await self._generate_with_model(self.fallback_model, payload, 0)

        if result["success"] and cache_key:
            if len(self._response_cache) >= 100:
                self._response_cache.pop(next(iter(self._response_cache)))
            self._response_cache[cache_key] = result
        return result

# Global Gemini client singleton
gemini_client = GeminiClient()
