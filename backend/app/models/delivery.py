from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel


class CamelBase(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Room(str, Enum):
    R101 = "101"
    R102 = "102"
    R103 = "103"


class Item(str, Enum):
    MED = "약"
    DIAPER = "기저귀"
    GLUCOSE = "혈당측정키트"
    WIPE = "물티슈"


class Status(str, Enum):
    REQUESTED = "REQUESTED"
    MOVING = "MOVING"
    ARRIVED = "ARRIVED"
    VERIFYING = "VERIFYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RobotStatus(str, Enum):
    MOVING = "MOVING"
    ARRIVED = "ARRIVED"


class VerificationResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


TERMINAL_STATUSES: frozenset[Status] = frozenset({Status.SUCCESS, Status.FAILED})


class DeliveryCreate(BaseModel):
    room: Room
    item: Item


class RobotStatusUpdate(BaseModel):
    status: RobotStatus


class VerificationUpdate(BaseModel):
    result: VerificationResult
    reason: str | None = None

    @model_validator(mode="after")
    def _require_reason_on_failure(self) -> "VerificationUpdate":
        if self.result == VerificationResult.FAILED and not self.reason:
            raise ValueError("reason is required when result is FAILED")
        return self


class Delivery(CamelBase):
    id: str
    room: Room
    item: Item
    status: Status
    created_at: str
    fail_reason: str | None = None


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def new_delivery(room: Room, item: Item) -> Delivery:
    return Delivery(
        id=str(uuid4()),
        room=room,
        item=item,
        status=Status.REQUESTED,
        created_at=_now_iso(),
        fail_reason=None,
    )
