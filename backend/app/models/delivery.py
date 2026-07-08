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
    AWAITING_NURSE = "AWAITING_NURSE"  # YOLO가 FAILED 판정 후, 간호사 결정 대기
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class NurseChoice(str, Enum):
    # 간호사가 실패 알림 후 어떻게 대응했는지 기록 (감사·통계 용도)
    IMMEDIATE = "IMMEDIATE"          # "바로 복귀"
    AFTER_ARRIVAL = "AFTER_ARRIVAL"  # "대기해, 내가 갈게" → 도착 후 "복귀 보내기"


class RobotStatus(str, Enum):
    MOVING = "MOVING"
    ARRIVED = "ARRIVED"


class VerificationResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class FailReason(str, Enum):
    # YOLO가 자동 판정한 실패 사유. 간호사 자유 텍스트 사유는 별도로 허용.
    X_CARD_DETECTED = "X_CARD_DETECTED"           # 실패(X) 카드가 확정됨
    TIMEOUT_NO_CARD = "TIMEOUT_NO_CARD"           # 30초 창 안에 어떤 카드도 확정되지 않음
    AMBIGUOUS_BOTH_CARDS = "AMBIGUOUS_BOTH_CARDS" # O·X 둘 다 확정됨(모호)


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


class NurseReturnCommand(BaseModel):
    """간호사가 실패 알림에 응답할 때 보내는 페이로드.

    - choice: 어떤 버튼을 눌렀는지 (감사 기록). 없으면 IMMEDIATE로 간주.
    - reason: YOLO가 붙인 사유 위에 간호사가 덧붙이는 자유 텍스트 (선택).
    """
    choice: NurseChoice = NurseChoice.IMMEDIATE
    reason: str | None = None


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
