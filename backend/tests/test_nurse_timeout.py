"""AWAITING_NURSE 5분 대기 상한 — 간호사 무응답 시 자동 복귀."""
import asyncio
from unittest.mock import patch

import pytest

from app.api import deliveries
from app.models.delivery import Delivery, Item, Room, Status, new_delivery
from app.services.store import store


@pytest.fixture
def awaiting_delivery() -> Delivery:
    delivery = new_delivery(Room.R102, Item.MED)
    delivery.status = Status.AWAITING_NURSE
    delivery.fail_reason = "X_CARD_DETECTED"
    store.add(delivery)
    return delivery


@pytest.fixture(autouse=True)
def _fast_timeout():
    """5분을 그대로 기다리지 않도록 상한을 짧게 줄인다."""
    with patch.object(deliveries, "_AWAITING_NURSE_TIMEOUT_S", 0.05):
        yield


async def test_timeout_transitions_awaiting_to_failed(awaiting_delivery: Delivery) -> None:
    with patch("app.api.deliveries.subprocess.Popen") as mock_popen:
        await deliveries._expire_nurse_wait(awaiting_delivery.id)

    assert awaiting_delivery.status == Status.FAILED
    assert awaiting_delivery.fail_reason == "X_CARD_DETECTED"  # YOLO 사유 유지
    mock_popen.assert_called_once()  # 로봇 자동 복귀


async def test_timeout_is_noop_when_nurse_already_responded(
    awaiting_delivery: Delivery,
) -> None:
    # 취소를 놓친 태스크가 뒤늦게 깨어나도 이미 확정된 결과를 덮어쓰면 안 된다
    awaiting_delivery.status = Status.FAILED
    awaiting_delivery.fail_reason = "환자 부재"

    with patch("app.api.deliveries.subprocess.Popen") as mock_popen:
        await deliveries._expire_nurse_wait(awaiting_delivery.id)

    assert awaiting_delivery.fail_reason == "환자 부재"
    mock_popen.assert_not_called()


async def test_timeout_is_noop_when_delivery_gone() -> None:
    with patch("app.api.deliveries.subprocess.Popen") as mock_popen:
        await deliveries._expire_nurse_wait("unknown")
    mock_popen.assert_not_called()


async def test_nurse_response_cancels_pending_timeout(
    awaiting_delivery: Delivery,
) -> None:
    deliveries._start_nurse_timeout(awaiting_delivery.id)
    task = deliveries._nurse_timeouts[awaiting_delivery.id]

    deliveries._cancel_nurse_timeout(awaiting_delivery.id)

    assert awaiting_delivery.id not in deliveries._nurse_timeouts
    with pytest.raises(asyncio.CancelledError):
        await task
    assert awaiting_delivery.status == Status.AWAITING_NURSE  # 타임아웃이 확정하지 않음


async def test_timeout_task_deregisters_itself_after_firing(
    awaiting_delivery: Delivery,
) -> None:
    with patch("app.api.deliveries.subprocess.Popen"):
        deliveries._start_nurse_timeout(awaiting_delivery.id)
        await deliveries._nurse_timeouts[awaiting_delivery.id]

    assert awaiting_delivery.id not in deliveries._nurse_timeouts
    assert awaiting_delivery.status == Status.FAILED
