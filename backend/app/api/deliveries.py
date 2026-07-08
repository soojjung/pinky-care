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


async def _complete_verification(
    delivery: Delivery,
    result: VerificationResult,
    reason: str | None,
    *,
    wait_for_nurse_on_failure: bool,
) -> None:
    """검증 결과 확정 공통 로직 (YOLO 자동 판정 · 간호사 수동 입력 모두 재사용).

    - 성공: ARRIVED → VERIFYING → SUCCESS 전이 + 자동 복귀 트리거
    - 실패:
        * ``wait_for_nurse_on_failure=True`` (YOLO 자동 경로) → VERIFYING → AWAITING_NURSE.
          실제 복귀는 나중에 ``/nurse-return-command`` 에서 발동.
        * ``wait_for_nurse_on_failure=False`` (레거시 수동 PATCH) → VERIFYING → FAILED
          + 즉시 복귀 트리거 (v2 이전 동작 유지).
    """
    delivery.status = Status.VERIFYING
    broadcaster.publish(delivery)

    await asyncio.sleep(_VERIFYING_TO_RESULT_DELAY_S)

    if result == VerificationResult.SUCCESS:
        delivery.status = Status.SUCCESS
        delivery.fail_reason = None
        broadcaster.publish(delivery)
        _trigger_return_process(delivery.id)
        return

    delivery.fail_reason = reason
    if wait_for_nurse_on_failure:
        delivery.status = Status.AWAITING_NURSE
        broadcaster.publish(delivery)
    else:
        delivery.status = Status.FAILED
        broadcaster.publish(delivery)
        _trigger_return_process(delivery.id)


async def _run_yolo_pipeline(delivery_id: str) -> None:
    """ARRIVED 도달 시 자동 실행되는 백그라운드 30초 창 폴링 태스크.

    창이 끝나면 YOLO 결과에 따라 SUCCESS 또는 AWAITING_NURSE로 전이한다.
    중간에 외부 PATCH /verification 등으로 상태가 이미 넘어갔다면 조용히 종료.
    """
    try:
        source = BoundFrameSource(frame_cache, delivery_id)
        outcome = await yolo.wait_for_patient_response(source)

        delivery = store.get(delivery_id)
        if delivery is None:
            return
        if delivery.status != Status.ARRIVED:
            log.info(
                "YOLO 태스크: 상태가 이미 %s 라 자동 전이 스킵 (%s)",
                delivery.status.value,
                delivery_id,
            )
            return

        reason_value = outcome.reason.value if outcome.reason else None
        await _complete_verification(
            delivery, outcome.result, reason_value,
            wait_for_nurse_on_failure=True,
        )
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
    return delivery


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

    if delivery.status != Status.ARRIVED:
        raise _invalid_transition(delivery.status, Status.VERIFYING)

    await _complete_verification(
        delivery, payload.result, payload.reason,
        wait_for_nurse_on_failure=False,
    )
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
