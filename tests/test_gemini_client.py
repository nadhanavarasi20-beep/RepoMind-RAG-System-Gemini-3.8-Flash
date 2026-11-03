import httpx
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.gemini.client import GeminiClient


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    def json(self):
        return self.body


class FakeAsyncClient:
    def __init__(self, responses, requests):
        self.responses = responses
        self.requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def post(self, url, json, headers):
        self.requests.append({"url": url, "json": json, "headers": headers})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def get(self, url, headers):
        self.requests.append({"url": url, "headers": headers})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class GeminiClientTests(IsolatedAsyncioTestCase):
    async def call_client(self, responses, retries=2):
        requests = []
        client = GeminiClient(
            api_key="test-key",
            model="gemini-3.8-flash",
            fallback_model="gemini-3.6-flash"
        )
        fake_async_client = lambda **kwargs: FakeAsyncClient(responses, requests)
        with (
            patch("app.gemini.client.httpx.AsyncClient", side_effect=fake_async_client),
            patch("app.gemini.client.settings.GEMINI_MAX_RETRIES", retries),
            patch("app.gemini.client.asyncio.sleep", new_callable=AsyncMock) as sleep
        ):
            result = await client.generate_response("system", "question")
        return result, requests, sleep

    async def test_retries_primary_503_then_uses_fallback_model(self):
        responses = [
            FakeResponse(503, {"error": {"message": "overloaded"}}),
            FakeResponse(503, {"error": {"message": "overloaded"}}),
            FakeResponse(503, {"error": {"message": "overloaded"}}),
            FakeResponse(200, {
                "candidates": [{"content": {"parts": [{"text": "Fallback answer"}]}}],
                "usageMetadata": {"totalTokenCount": 17}
            })
        ]

        result, requests, sleep = await self.call_client(responses)

        self.assertTrue(result["success"])
        self.assertEqual(result["content"], "Fallback answer")
        self.assertEqual(result["model"], "gemini-3.6-flash")
        self.assertEqual(len(requests), 4)
        self.assertEqual(
            [request["url"].split("/models/")[1].split(":")[0] for request in requests],
            ["gemini-3.8-flash"] * 3 + ["gemini-3.6-flash"]
        )
        self.assertNotIn("test-key", requests[0]["url"])
        self.assertEqual(requests[0]["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(sleep.await_count, 2)

    async def test_429_is_not_retried_and_fallback_is_bounded(self):
        responses = [
            FakeResponse(429, {"error": {"message": "quota exhausted"}}),
            FakeResponse(429, {"error": {"message": "quota exhausted"}})
        ]

        result, requests, _ = await self.call_client(responses)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "quota_exceeded")
        self.assertEqual(len(requests), 2)

    async def test_timeout_uses_secondary_once(self):
        responses = [
            httpx.TimeoutException("request timed out"),
            FakeResponse(200, {
                "candidates": [{"content": {"parts": [{"text": "Recovered"}]}}]
            })
        ]

        result, requests, _ = await self.call_client(responses)

        self.assertTrue(result["success"])
        self.assertEqual(result["model"], "gemini-3.6-flash")
        self.assertEqual(len(requests), 2)

    async def test_invalid_api_key_does_not_retry_or_try_fallback(self):
        responses = [
            FakeResponse(400, {
                "error": {"message": "API key not valid. Please pass a valid API key."}
            })
        ]

        result, requests, _ = await self.call_client(responses)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "authentication_error")
        self.assertEqual(len(requests), 1)

    async def test_missing_api_key_returns_without_network_request(self):
        client = GeminiClient(
            api_key="",
            model="gemini-3.8-flash",
            fallback_model="gemini-3.6-flash"
        )
        with patch("app.gemini.client.httpx.AsyncClient") as async_client:
            result = await client.generate_response("system", "question")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "missing_api_key")
        async_client.assert_not_called()

    async def test_verification_does_not_report_overloaded_model_as_available(self):
        responses = [FakeResponse(503, {"error": {"message": "overloaded"}})]
        requests = []
        client = GeminiClient(
            api_key="test-key",
            model="gemini-3.8-flash",
            fallback_model="gemini-3.6-flash"
        )
        fake_async_client = lambda **kwargs: FakeAsyncClient(responses, requests)
        with patch("app.gemini.client.httpx.AsyncClient", side_effect=fake_async_client):
            available, status_code, _ = await client.verify_model_availability(force_check=True)

        self.assertFalse(available)
        self.assertEqual(status_code, 503)
        self.assertEqual(len(requests), 1)

    async def test_fallback_overload_stops_after_one_call(self):
        responses = [
            FakeResponse(503, {"error": {"message": "overloaded"}}),
            FakeResponse(503, {"error": {"message": "overloaded"}}),
            FakeResponse(503, {"error": {"message": "overloaded"}}),
            FakeResponse(503, {"error": {"message": "overloaded"}})
        ]

        result, requests, _ = await self.call_client(responses)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "server_overload")
        self.assertEqual(len(requests), 4)

    async def test_evidence_fallback_contains_snippet_and_exact_citation(self):
        from app.api.chat_routes import build_evidence_fallback

        content, citations = build_evidence_fallback(
            "Explain the architecture",
            [{
                "file_path": "app/main.py",
                "start_line": 10,
                "end_line": 12,
                "content": "app = FastAPI()\napp.include_router(router)\n@app.get('/health')",
                "language": "python",
                "score": 0.9
            }, {
                "file_path": "README.md",
                "start_line": 1,
                "end_line": 4,
                "content": "# Product\n\nA FastAPI project that processes reviews.",
                "language": "markdown",
                "score": 0.8
            }],
            "server_overload"
        )

        self.assertIn("not AI-generated", content)
        self.assertIn("[app/main.py:10-12]", content)
        self.assertIn("app.include_router(router)", content)
        self.assertIn("A FastAPI project that processes reviews.", content)
        self.assertEqual(citations[0].file_path, "app/main.py")
        self.assertEqual(citations[0].start_line, 10)
        self.assertEqual(citations[0].end_line, 12)

        empty_content, empty_citations = build_evidence_fallback(
            "Explain the architecture",
            [],
            "missing_api_key"
        )
        self.assertIn("Local evidence fallback", empty_content)
        self.assertIn("no code chunks were retrieved", empty_content)
        self.assertEqual(empty_citations, [])
