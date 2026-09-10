"""Phase 0 smoke test: GET /health returns 200 and the expected body.

Mocked test — no Docker, no databases, no API calls. Safe to run repeatedly.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
