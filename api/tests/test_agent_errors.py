from uuid import UUID

import httpx
import httpx2
import pytest
from agents import MaxTurnsExceeded, UserError
from fastapi import FastAPI
from openai import APITimeoutError, RateLimitError

from main import app

REQUEST_ID = "12345678-1234-4234-8234-123456789abc"
MODEL_REQUEST = httpx2.Request("POST", "https://example.test/v1/chat/completions")
PRIVATE_DETAIL = "private upstream failure details"
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        pytest.param(
            APITimeoutError(request=MODEL_REQUEST),
            504,
            "Model request timed out",
            id="model-timeout",
        ),
        pytest.param(
            RateLimitError(
                PRIVATE_DETAIL,
                response=httpx2.Response(429, request=MODEL_REQUEST),
                body={"error": PRIVATE_DETAIL},
            ),
            503,
            "Model service temporarily unavailable",
            id="upstream-rate-limit",
        ),
        pytest.param(
            MaxTurnsExceeded(PRIVATE_DETAIL),
            502,
            "Agent exceeded the maximum number of turns",
            id="max-turns",
        ),
        pytest.param(
            UserError(PRIVATE_DETAIL),
            500,
            "Internal server error",
            id="sdk-configuration-error",
        ),
    ],
)
@pytest.mark.parametrize(
    "headers", [{"X-Request-ID": REQUEST_ID}, {}], ids=["supplied-id", "generated-id"]
)
async def test_agent_errors_return_safe_responses_with_request_ids(
    error, status, detail, headers
):
    test_app = FastAPI(middleware=list(app.user_middleware))
    test_app.exception_handlers.update(app.exception_handlers)

    @test_app.get("/failure")
    async def failure():
        raise error

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/failure", headers=headers)

    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert PRIVATE_DETAIL not in response.text
    assert "example.test" not in response.text
    request_id = response.headers["X-Request-ID"]
    assert UUID(request_id).version == 4
    if headers:
        assert request_id == REQUEST_ID
