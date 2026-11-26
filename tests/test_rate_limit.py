"""Offline tests for the rate limiter."""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import rate_limit
from app.rate_limit import SlidingWindowLimiter


def test_allows_requests_up_to_the_limit_then_blocks():
    limiter = SlidingWindowLimiter(max_requests=3, window_seconds=60)

    assert limiter.check("user-a") is None
    assert limiter.check("user-a") is None
    assert limiter.check("user-a") is None

    retry_after = limiter.check("user-a")

    assert retry_after is not None
    assert 1 <= retry_after <= 61


def test_each_key_has_its_own_budget():
    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=60)

    assert limiter.check("user-a") is None
    assert limiter.check("user-a") is not None
    assert limiter.check("user-b") is None


def test_requests_are_allowed_again_after_the_window(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock["now"])

    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=10)

    assert limiter.check("k") is None
    assert limiter.check("k") is not None

    clock["now"] += 11

    assert limiter.check("k") is None


def test_endpoint_returns_429_with_retry_after_header():
    limiter = SlidingWindowLimiter(max_requests=2, window_seconds=60)
    api = FastAPI()

    @api.get(
        "/ping",
        dependencies=[
            Depends(rate_limit.make_limit_dependency(limiter, "requests"))
        ],
    )
    def ping():
        return {"ok": True}

    client = TestClient(api)

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200

    blocked = client.get("/ping")

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert "wait" in blocked.json()["detail"].lower()


def test_client_ip_prefers_forwarded_header():
    api = FastAPI()

    @api.get("/ip")
    def ip(request: rate_limit.Request):
        return {"ip": rate_limit.client_ip(request)}

    client = TestClient(api)
    response = client.get(
        "/ip", headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}
    )

    assert response.json() == {"ip": "203.0.113.9"}
