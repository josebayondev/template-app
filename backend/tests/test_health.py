import pytest
from fastapi.testclient import TestClient


@pytest.mark.db
def test_health_returns_ok(running_client: TestClient) -> None:
    """running_client starts the lifespan, so check_db_connection() runs for real."""
    response = running_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_answers_head_requests(client: TestClient) -> None:
    """Uptime probes default to HEAD, and FastAPI does not add it implicitly."""
    response = client.head("/health")

    assert response.status_code == 200
