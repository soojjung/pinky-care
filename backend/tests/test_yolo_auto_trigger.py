"""ARRIVED 도달 시 YOLO 파이프라인이 자동 실행되는지 검증.

실제 YOLO 모델 로드 없이 ``wait_for_patient_response``를 스텁으로 대체해
전이/브로드캐스트만 확인한다.
"""
import asyncio
from unittest.mock import patch

import httpx
import pytest

from app.main import app
from app.models.delivery import FailReason, Status, VerificationResult
from app.services import yolo
from app.services.store import store


async def _wait_for_status(delivery_id: str, target: Status, timeout: float = 3.0) -> None:
    """폴링으로 원하는 상태에 도달하기를 기다린다."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        d = store.get(delivery_id)
        if d is not None and d.status == target:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(
        f"Timeout waiting for {target}. Actual: {store.get(delivery_id).status if store.get(delivery_id) else 'None'}"
    )


async def _stub_success(*_a, **_kw):
    return yolo.YoloOutcome(VerificationResult.SUCCESS, None)


async def _stub_x_card(*_a, **_kw):
    return yolo.YoloOutcome(VerificationResult.FAILED, FailReason.X_CARD_DETECTED)


async def _stub_timeout(*_a, **_kw):
    return yolo.YoloOutcome(VerificationResult.FAILED, FailReason.TIMEOUT_NO_CARD)


@pytest.fixture
def _mock_return_process():
    with patch("app.api.deliveries.subprocess.Popen") as m:
        yield m


async def _make_arrived_delivery(client: httpx.AsyncClient) -> str:
    r = await client.post("/deliveries", json={"room": "102", "item": "약"})
    delivery_id = r.json()["id"]
    await client.patch(
        f"/deliveries/{delivery_id}/robot-status", json={"status": "MOVING"}
    )
    await client.patch(
        f"/deliveries/{delivery_id}/robot-status", json={"status": "ARRIVED"}
    )
    return delivery_id


async def test_arrived_triggers_yolo_and_success_completes(_mock_return_process):
    """YOLO가 SUCCESS 반환 → 상태 SUCCESS + 복귀 스크립트 트리거."""
    transport = httpx.ASGITransport(app=app)
    with patch("app.api.deliveries.yolo.wait_for_patient_response", _stub_success):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            delivery_id = await _make_arrived_delivery(client)
            await _wait_for_status(delivery_id, Status.SUCCESS)

    delivery = store.get(delivery_id)
    assert delivery.status == Status.SUCCESS
    assert delivery.fail_reason is None
    _mock_return_process.assert_called()


async def test_arrived_triggers_yolo_and_failure_awaits_nurse(_mock_return_process):
    """YOLO가 FAILED 반환 → 상태 AWAITING_NURSE, 복귀 스크립트 아직 안 뜸."""
    transport = httpx.ASGITransport(app=app)
    with patch("app.api.deliveries.yolo.wait_for_patient_response", _stub_x_card):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            delivery_id = await _make_arrived_delivery(client)
            await _wait_for_status(delivery_id, Status.AWAITING_NURSE)

    delivery = store.get(delivery_id)
    assert delivery.status == Status.AWAITING_NURSE
    assert delivery.fail_reason == FailReason.X_CARD_DETECTED.value
    _mock_return_process.assert_not_called()  # 실패는 간호사 결정을 기다림


async def test_awaiting_nurse_then_command_triggers_return(_mock_return_process):
    """AWAITING_NURSE → 간호사가 nurse-return-command → FAILED + 복귀."""
    transport = httpx.ASGITransport(app=app)
    with patch("app.api.deliveries.yolo.wait_for_patient_response", _stub_timeout):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            delivery_id = await _make_arrived_delivery(client)
            await _wait_for_status(delivery_id, Status.AWAITING_NURSE)

            r = await client.post(
                f"/deliveries/{delivery_id}/nurse-return-command",
                json={"choice": "AFTER_ARRIVAL", "reason": "환자 부재"},
            )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED"
    assert body["failReason"] == "환자 부재"
    _mock_return_process.assert_called()  # 이 시점에 복귀 트리거
