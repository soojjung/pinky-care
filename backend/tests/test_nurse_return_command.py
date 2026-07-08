"""POST /deliveries/{id}/nurse-return-command — 실패 후 간호사 결정 API."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models.delivery import Status
from app.services.store import store


def _force_awaiting_nurse(delivery_id: str, reason: str = "X_CARD_DETECTED") -> None:
    """테스트용: YOLO 파이프라인 없이 AWAITING_NURSE 상태로 강제 전이."""
    delivery = store.get(delivery_id)
    assert delivery is not None
    delivery.status = Status.AWAITING_NURSE
    delivery.fail_reason = reason


def test_immediate_return_transitions_awaiting_to_failed(
    client: TestClient, arrived_id: str,
) -> None:
    _force_awaiting_nurse(arrived_id)

    with patch("app.api.deliveries.subprocess.Popen") as mock_popen:
        r = client.post(
            f"/deliveries/{arrived_id}/nurse-return-command",
            json={"choice": "IMMEDIATE"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED"
    assert body["failReason"] == "X_CARD_DETECTED"  # YOLO 사유 유지
    mock_popen.assert_called_once()  # 복귀 스크립트 트리거됨


def test_after_arrival_also_transitions_and_returns(
    client: TestClient, arrived_id: str,
) -> None:
    _force_awaiting_nurse(arrived_id)

    with patch("app.api.deliveries.subprocess.Popen"):
        r = client.post(
            f"/deliveries/{arrived_id}/nurse-return-command",
            json={"choice": "AFTER_ARRIVAL"},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "FAILED"


def test_reason_override_replaces_yolo_reason(
    client: TestClient, arrived_id: str,
) -> None:
    _force_awaiting_nurse(arrived_id, reason="X_CARD_DETECTED")

    with patch("app.api.deliveries.subprocess.Popen"):
        r = client.post(
            f"/deliveries/{arrived_id}/nurse-return-command",
            json={"choice": "AFTER_ARRIVAL", "reason": "환자 부재"},
        )
    assert r.status_code == 200
    assert r.json()["failReason"] == "환자 부재"


def test_default_choice_is_immediate(client: TestClient, arrived_id: str) -> None:
    _force_awaiting_nurse(arrived_id)

    with patch("app.api.deliveries.subprocess.Popen"):
        r = client.post(
            f"/deliveries/{arrived_id}/nurse-return-command",
            json={},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "FAILED"


def test_command_from_wrong_status_returns_409(
    client: TestClient, arrived_id: str,
) -> None:
    # ARRIVED에서 바로 호출하면 안 됨 (AWAITING_NURSE만 허용)
    r = client.post(
        f"/deliveries/{arrived_id}/nurse-return-command",
        json={"choice": "IMMEDIATE"},
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "INVALID_TRANSITION"


def test_command_missing_delivery_returns_404(client: TestClient) -> None:
    r = client.post(
        "/deliveries/unknown/nurse-return-command",
        json={"choice": "IMMEDIATE"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_invalid_choice_returns_422(client: TestClient, arrived_id: str) -> None:
    _force_awaiting_nurse(arrived_id)
    r = client.post(
        f"/deliveries/{arrived_id}/nurse-return-command",
        json={"choice": "BOGUS"},
    )
    assert r.status_code == 422
