import asyncio
import logging
import os
import subprocess

from fastapi import APIRouter, HTTPException, Response, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.models.delivery import (
    Delivery,
    DeliveryCreate,
    NurseReturnCommand,
    RobotStatusUpdate,
    Status,
    TERMINAL_STATUSES,
    VerificationResult,
    VerificationUpdate,
    new_delivery,
)
from app.services import yolo
from app.services.broadcaster import broadcaster
from app.services.frame_source import BoundFrameSource, frame_cache
from app.services.store import store
from app.services.transitions import (
    robot_status_required_current,
    robot_target_as_status,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

_VERIFYING_TO_RESULT_DELAY_S = 0.3
_SSE_PING_INTERVAL_S = 30
_RETURN_SCRIPT = os.path.expanduser(
    "~/pinky_pro/src/pinky_pro/pinky_navigation/scripts/junction_1.py"
)


def _not_found(delivery_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"Delivery {delivery_id} not found"},
    )


def _invalid_transition(current: Status, target: Status) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "INVALID_TRANSITION",
            "message": f"Cannot transition from {current.value} to {target.value}",
        },
    )


def _trigger_return_process(delivery_id: str) -> None:
    """복귀 스크립트를 백그라운드 subprocess로 띄운다.

    성공·실패 어느 쪽이든 로봇이 최종 결정된 뒤 호출한다.
    """
    subprocess.Popen(
        ["python3", _RETURN_SCRIPT, "--state", "복귀", "--delivery-id", delivery_id]
    )


async def _complete_verification_legacy(
    delivery: Delivery,
    result: VerificationResult,
    reason: str | None,
) -> None:
    """레거시 수동 PATCH /verification 로직.

    ARRIVED → VERIFYING(0.3초 UI 애니메이션) → SUCCESS 또는 FAILED (자동 복귀).
    YOLO 자동 파이프라인을 우회해서 즉시 결과를 확정할 때 사용.
    """
    if delivery.status != Status.VERIFYING:
        delivery.status = Status.VERIFYING
        broadcaster.publish(delivery)

    await asyncio.sleep(_VERIFYING_TO_RESULT_DELAY_S)

    if result == VerificationResult.SUCCESS:
        delivery.status = Status.SUCCESS
        delivery.fail_reason = None
    else:
        delivery.status = Status.FAILED
        delivery.fail_reason = reason
    broadcaster.publish(delivery)
    _trigger_return_process(delivery.id)


async def _run_yolo_pipeline(delivery_id: str) -> None:
    """ARRIVED 도달 시 자동 실행되는 백그라운드 30초 창 폴링 태스크.

    상태 흐름:
        ARRIVED → (즉시) VERIFYING → (30초 동안 폴링) → SUCCESS 또는 AWAITING_NURSE

    VERIFYING 을 창 시작 시점에 발행함으로써 프론트에서 "확인 중" 스텝이
    30초 내내 유지된다 (시나리오 v3 §3③).
    """
    try:
        delivery = store.get(delivery_id)
        if delivery is None or delivery.status != Status.ARRIVED:
            log.info(
                "YOLO 태스크: 시작 시점 상태가 ARRIVED 아님 (%s), 스킵",
                delivery_id,
            )
            return

        # 창 시작 시점에 VERIFYING 으로 전이
        delivery.status = Status.VERIFYING
        broadcaster.publish(delivery)

        source = BoundFrameSource(frame_cache, delivery_id)
        outcome = await yolo.wait_for_patient_response(source)

        delivery = store.get(delivery_id)
        if delivery is None:
            return
        if delivery.status != Status.VERIFYING:
            log.info(
                "YOLO 태스크: 창 종료 시점에 상태가 이미 %s 라 결과 전이 스킵 (%s)",
                delivery.status.value,
                delivery_id,
            )
            return

        reason_value = outcome.reason.value if outcome.reason else None
        if outcome.result == VerificationResult.SUCCESS:
            delivery.status = Status.SUCCESS
            delivery.fail_reason = None
            broadcaster.publish(delivery)
            _trigger_return_process(delivery.id)
        else:
            delivery.status = Status.AWAITING_NURSE
            delivery.fail_reason = reason_value
            broadcaster.publish(delivery)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        log.exception("YOLO 파이프라인 실행 중 예외 (%s)", delivery_id)
    finally:
        frame_cache.clear(delivery_id)


# ─────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=Delivery,
    response_model_by_alias=True,
    status_code=201,
)
def create_delivery(payload: DeliveryCreate) -> Delivery:
    delivery = new_delivery(payload.room, payload.item)
    store.add(delivery)
    # 로봇 미션 디스패처가 구독하는 전역 스트림으로 새 배송 알림
    n = broadcaster.publish_new(delivery)
    log.info("새 배송 %s (%s호) → 디스패처 %d명에게 전송", delivery.id, delivery.room.value, n)
    if n == 0:
        log.warning("연결된 디스패처가 없음 — 로봇이 이 배송을 못 받음 (디스패처 먼저 실행 필요)")
    return delivery


@router.get("/events")
async def stream_new_deliveries() -> EventSourceResponse:
    """새로 생성되는 배송을 실시간으로 흘려보내는 전역 스트림.

    로봇 쪽 미션 디스패처가 이 스트림을 구독해서, 배송이 생기면
    ``junction_1.py`` 를 room·delivery-id 로 자동 실행한다.

    NOTE: 이 라우트는 ``/{delivery_id}`` 보다 먼저 선언되어야 한다.
    안 그러면 ``/deliveries/events`` 가 delivery_id="events" 로 잡힌다.
    """

    async def event_generator():
        queue = broadcaster.subscribe_new()
        log.info("디스패처 연결됨 (현재 %d명 구독 중)", broadcaster.new_subscriber_count())
        try:
            while True:
                snapshot = await queue.get()
                yield {"event": "delivery", "data": snapshot}
        finally:
            broadcaster.unsubscribe_new(queue)
            log.info("디스패처 연결 종료 (남은 구독자 %d명)", broadcaster.new_subscriber_count())

    return EventSourceResponse(event_generator(), ping=_SSE_PING_INTERVAL_S)


@router.get(
    "/{delivery_id}",
    response_model=Delivery,
    response_model_by_alias=True,
)
def get_delivery(delivery_id: str) -> Delivery:
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)
    return delivery


@router.patch(
    "/{delivery_id}/robot-status",
    response_model=Delivery,
    response_model_by_alias=True,
)
async def update_robot_status(delivery_id: str, payload: RobotStatusUpdate) -> Delivery:
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)

    target = robot_target_as_status(payload.status)
    required_current = robot_status_required_current(payload.status)
    if delivery.status != required_current:
        raise _invalid_transition(delivery.status, target)

    delivery.status = target
    broadcaster.publish(delivery)

    # ARRIVED 도달 시 30초 YOLO 창 자동 시작
    if target == Status.ARRIVED:
        asyncio.create_task(_run_yolo_pipeline(delivery_id))

    return delivery


@router.post(
    "/{delivery_id}/image",
    status_code=204,
)
async def upload_image(delivery_id: str, image: UploadFile) -> Response:
    """ROS2 노드가 초당 1회 카메라 프레임을 올리는 엔드포인트.

    최신 1장만 캐시에 덮어씀. YOLO 폴링 루프가 이 캐시에서 꺼내 판정한다.
    """
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)

    data = await image.read()
    if not data:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "empty image body"},
        )
    frame_cache.put(delivery_id, data)
    return Response(status_code=204)


@router.patch(
    "/{delivery_id}/verification",
    response_model=Delivery,
    response_model_by_alias=True,
)
async def submit_verification(delivery_id: str, payload: VerificationUpdate) -> Delivery:
    """(레거시) 외부에서 수동으로 verification 결과를 넣을 때 쓰는 경로.

    YOLO 자동 판정이 붙은 뒤로는 데모에서 직접 호출할 일은 거의 없다.
    ARRIVED 상태에서만 허용해서 기존 동작 유지.
    """
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)

    # ARRIVED 는 사람이 자동 파이프라인 시작 전에 override, VERIFYING 은 진행 중 override
    if delivery.status not in (Status.ARRIVED, Status.VERIFYING):
        raise _invalid_transition(delivery.status, Status.VERIFYING)

    await _complete_verification_legacy(delivery, payload.result, payload.reason)
    return delivery


@router.post(
    "/{delivery_id}/nurse-return-command",
    response_model=Delivery,
    response_model_by_alias=True,
)
def nurse_return_command(
    delivery_id: str, payload: NurseReturnCommand
) -> Delivery:
    """간호사가 실패 알림에 응답해서 로봇을 복귀시키는 명령.

    - "바로 복귀" 버튼        → choice=IMMEDIATE (기본), 즉시 복귀
    - "대기해, 내가 갈게" 후    → choice=AFTER_ARRIVAL, 병실에서 처리 후 호출
    - reason으로 자유 텍스트 사유를 덧붙이면 fail_reason 을 덮어씀
    """
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)

    if delivery.status != Status.AWAITING_NURSE:
        raise _invalid_transition(delivery.status, Status.FAILED)

    delivery.status = Status.FAILED
    if payload.reason:
        delivery.fail_reason = payload.reason
    broadcaster.publish(delivery)

    _trigger_return_process(delivery_id)
    return delivery


@router.get("/{delivery_id}/events")
async def stream_events(delivery_id: str) -> EventSourceResponse:
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)

    initial_snapshot = delivery.model_dump_json(by_alias=True)
    initial_status = delivery.status

    async def event_generator():
        yield {"event": "status", "data": initial_snapshot}
        if initial_status in TERMINAL_STATUSES:
            return

        queue = broadcaster.subscribe(delivery_id)
        try:
            while True:
                status, snapshot = await queue.get()
                yield {"event": "status", "data": snapshot}
                if status in TERMINAL_STATUSES:
                    return
        finally:
            broadcaster.unsubscribe(delivery_id, queue)

    return EventSourceResponse(event_generator(), ping=_SSE_PING_INTERVAL_S)
