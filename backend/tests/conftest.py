import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.broadcaster import broadcaster
from app.services.frame_source import frame_cache
from app.services.store import store


@pytest.fixture(autouse=True)
def _reset_state():
    store._items.clear()
    broadcaster._subscribers.clear()
    frame_cache._latest.clear()
    yield
    store._items.clear()
    broadcaster._subscribers.clear()
    frame_cache._latest.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def created_id(client: TestClient) -> str:
    r = client.post("/deliveries", json={"room": "101", "item": "약"})
    assert r.status_code == 201
    return r.json()["id"]


@pytest.fixture
def arrived_id(client: TestClient, created_id: str) -> str:
    client.patch(f"/deliveries/{created_id}/robot-status", json={"status": "MOVING"})
    client.patch(f"/deliveries/{created_id}/robot-status", json={"status": "ARRIVED"})
    return created_id
