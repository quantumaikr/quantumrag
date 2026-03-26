"""Tests for Request ID tracking middleware (E5.4)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from quantumrag.api.middleware import setup_request_id


@pytest.fixture()
def app() -> FastAPI:
    test_app = FastAPI()
    setup_request_id(test_app)

    @test_app.get("/echo")
    async def echo(request: Request) -> dict:
        return {"request_id": getattr(request.state, "request_id", None)}

    return test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestRequestID:
    def test_auto_generates_request_id(self, client: TestClient) -> None:
        resp = client.get("/echo")
        assert resp.status_code == 200
        rid = resp.headers.get("X-Request-ID")
        assert rid is not None
        assert len(rid) == 36  # UUID format

    def test_preserves_provided_request_id(self, client: TestClient) -> None:
        custom_id = "my-trace-12345"
        resp = client.get("/echo", headers={"X-Request-ID": custom_id})
        assert resp.status_code == 200
        assert resp.headers["X-Request-ID"] == custom_id
        assert resp.json()["request_id"] == custom_id

    def test_different_requests_get_different_ids(self, client: TestClient) -> None:
        r1 = client.get("/echo")
        r2 = client.get("/echo")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]
