import asyncio

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.models.delivery import (
    Delivery,
    DeliveryCreate,
    RobotStatusUpdate,
    Status,
    TERMINAL_STATUSES,
    VerificationResult,
    VerificationUpdate,
    new_delivery,
)
from app.services.broadcaster import broadcaster
from app.services.store import store
from app.services.transitions import (
    robot_status_required_current,
    robot_target_as_status,
)

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

_VERIFYING_TO_RESULT_DELAY_S = 0.3
_SSE_PING_INTERVAL_S = 30


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
def update_robot_status(delivery_id: str, payload: RobotStatusUpdate) -> Delivery:
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)

    target = robot_target_as_status(payload.status)
    required_current = robot_status_required_current(payload.status)
    if delivery.status != required_current:
        raise _invalid_transition(delivery.status, target)

    delivery.status = target
    broadcaster.publish(delivery)
    return delivery


@router.patch(
    "/{delivery_id}/verification",
    response_model=Delivery,
    response_model_by_alias=True,
)
async def submit_verification(delivery_id: str, payload: VerificationUpdate) -> Delivery:
    delivery = store.get(delivery_id)
    if delivery is None:
        raise _not_found(delivery_id)

    if delivery.status != Status.ARRIVED:
        raise _invalid_transition(delivery.status, Status.VERIFYING)

    delivery.status = Status.VERIFYING
    broadcaster.publish(delivery)

    await asyncio.sleep(_VERIFYING_TO_RESULT_DELAY_S)

    if payload.result == VerificationResult.SUCCESS:
        delivery.status = Status.SUCCESS
        delivery.fail_reason = None
    else:
        delivery.status = Status.FAILED
        delivery.fail_reason = payload.reason

    broadcaster.publish(delivery)
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
