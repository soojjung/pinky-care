from fastapi.testclient import TestClient


def test_create_returns_requested_with_camel_case(client: TestClient) -> None:
    r = client.post("/deliveries", json={"room": "102", "item": "약"})
    assert r.status_code == 201
    body = r.json()
    assert body["room"] == "102"
    assert body["item"] == "약"
    assert body["status"] == "REQUESTED"
    assert body["failReason"] is None
    assert body["createdAt"].endswith("Z")
    assert isinstance(body["id"], str) and len(body["id"]) == 36


def test_get_returns_same_snapshot(client: TestClient, created_id: str) -> None:
    r = client.get(f"/deliveries/{created_id}")
    assert r.status_code == 200
    assert r.json()["id"] == created_id


def test_get_missing_returns_not_found_envelope(client: TestClient) -> None:
    r = client.get("/deliveries/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {
        "error": {"code": "NOT_FOUND", "message": "Delivery does-not-exist not found"},
    }


def test_invalid_room_returns_validation_envelope(client: TestClient) -> None:
    r = client.post("/deliveries", json={"room": "999", "item": "약"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "room" in body["error"]["message"]


def test_happy_path_transitions_via_rest(client: TestClient, created_id: str) -> None:
    r = client.patch(f"/deliveries/{created_id}/robot-status", json={"status": "MOVING"})
    assert r.status_code == 200
    assert r.json()["status"] == "MOVING"

    r = client.patch(f"/deliveries/{created_id}/robot-status", json={"status": "ARRIVED"})
    assert r.json()["status"] == "ARRIVED"

    r = client.patch(f"/deliveries/{created_id}/verification", json={"result": "SUCCESS"})
    assert r.json()["status"] == "SUCCESS"
    assert r.json()["failReason"] is None


def test_invalid_robot_transition_returns_409(client: TestClient, created_id: str) -> None:
    r = client.patch(f"/deliveries/{created_id}/robot-status", json={"status": "ARRIVED"})
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "INVALID_TRANSITION"
    assert "REQUESTED" in body["error"]["message"]
    assert "ARRIVED" in body["error"]["message"]


def test_verification_before_arrived_returns_409(
    client: TestClient, created_id: str,
) -> None:
    r = client.patch(
        f"/deliveries/{created_id}/verification", json={"result": "SUCCESS"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"


def test_verification_failed_without_reason_returns_422(
    client: TestClient, arrived_id: str,
) -> None:
    r = client.patch(
        f"/deliveries/{arrived_id}/verification", json={"result": "FAILED"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_verification_failed_stores_reason(
    client: TestClient, arrived_id: str,
) -> None:
    r = client.patch(
        f"/deliveries/{arrived_id}/verification",
        json={"result": "FAILED", "reason": "물품 인식 실패"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED"
    assert body["failReason"] == "물품 인식 실패"


def test_robot_status_missing_delivery_returns_404(client: TestClient) -> None:
    r = client.patch(
        "/deliveries/unknown/robot-status", json={"status": "MOVING"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_robot_status_rejects_terminal_targets(
    client: TestClient, created_id: str,
) -> None:
    r = client.patch(
        f"/deliveries/{created_id}/robot-status", json={"status": "SUCCESS"},
    )
    assert r.status_code == 422


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
