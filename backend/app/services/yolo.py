"""배송 완료 시점 YOLO 자동 판정 서비스.

- ``detect_labels(bytes)`` — 프레임 1장에서 conf ≥ 임계치인 라벨 집합을 뽑는다.
- ``decide_window_verdict(counts)`` — 30초 창 동안 누적된 라벨 통계로 최종 판정.
- ``wait_for_patient_response(source)`` — 창을 굴리며 프레임을 폴링해 최종 outcome을 반환.

판정 로직은 ``yolo/detect_ox.py``의 window-based 규칙과 동일해야 한다
(`delivery-scenario.md §4` 실패 사유 3가지). 프레임 1장의 순간 판정이 아니라,
30초 창 안에 여러 번 확인된 라벨 집합으로 결정한다.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from pathlib import Path
from typing import NamedTuple, Protocol

from app.models.delivery import FailReason, VerificationResult

log = logging.getLogger(__name__)

# ── 판정 파라미터 ─────────────────────────────────────────
CONF_THRESHOLD = 0.5       # 프레임 판정에 필요한 최소 신뢰도
POLL_INTERVAL_SEC = 1.0    # 프레임 폴링 간격
WINDOW_SECONDS = 30.0      # 판정 창 길이
MIN_CONFIRMATIONS = 3      # 창 안에서 라벨을 '확정' 처리하기 위한 최소 감지 프레임 수

# ── 라벨 상수 ────────────────────────────────────────────
LABEL_SUCCESS = "success"
LABEL_FAILURE = "failure"

# ── 가중치 경로 ───────────────────────────────────────────
_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "pinky_yolo_v1.pt"
_model_instance = None  # lazy loader


class YoloOutcome(NamedTuple):
    result: VerificationResult
    reason: FailReason | None  # SUCCESS일 때 None


class FrameSource(Protocol):
    """폴링 루프가 프레임을 꺼내오는 얇은 인터페이스."""

    async def grab(self) -> bytes | None:
        """최신 JPEG 바이트. 아직 없으면 ``None``."""


# ─────────────────────────────────────────────────────────
# 프레임 판정 — 순수 로직 (테스트 대상)
# ─────────────────────────────────────────────────────────

def decide_window_verdict(label_counts: dict[str, int]) -> YoloOutcome:
    """30초 창 동안 누적된 라벨 통계로 최종 판정.

    ``label_counts``는 라벨명 → 감지된 프레임 수. ``MIN_CONFIRMATIONS`` 이상
    감지된 라벨만 "확정"으로 취급.
    """
    confirmed = {label for label, n in label_counts.items() if n >= MIN_CONFIRMATIONS}
    has_success = LABEL_SUCCESS in confirmed
    has_failure = LABEL_FAILURE in confirmed

    if has_success and has_failure:
        return YoloOutcome(VerificationResult.FAILED, FailReason.AMBIGUOUS_BOTH_CARDS)
    if has_success:
        return YoloOutcome(VerificationResult.SUCCESS, None)
    if has_failure:
        return YoloOutcome(VerificationResult.FAILED, FailReason.X_CARD_DETECTED)
    return YoloOutcome(VerificationResult.FAILED, FailReason.TIMEOUT_NO_CARD)


# ─────────────────────────────────────────────────────────
# YOLO 추론 — 실제 모델 로드
# ─────────────────────────────────────────────────────────

def _load_model():
    """가중치를 lazy load. 실제 배포/시연 시에만 한 번 호출."""
    global _model_instance
    if _model_instance is None:
        from ultralytics import YOLO  # 로컬 임포트 (테스트에서 모델 없어도 임포트 가능)

        log.info("Loading YOLO model from %s", _MODEL_PATH)
        _model_instance = YOLO(str(_MODEL_PATH))
    return _model_instance


def detect_labels(image_bytes: bytes) -> set[str]:
    """JPEG 바이트에서 conf ≥ 임계치인 라벨 집합을 뽑는다.

    실제 YOLO 추론을 수행하므로 pytest에서는 ``monkeypatch``로 대체하는 게 정석.
    """
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    results = _load_model().predict(image, conf=CONF_THRESHOLD, verbose=False)

    labels: set[str] = set()
    for r in results:
        names = r.names  # 예: {0: "failure", 1: "success"}
        if r.boxes is None:
            continue
        for i in range(len(r.boxes)):
            conf = float(r.boxes.conf[i].item())
            if conf < CONF_THRESHOLD:
                continue
            cls_idx = int(r.boxes.cls[i].item())
            labels.add(names[cls_idx])
    return labels


# ─────────────────────────────────────────────────────────
# 폴링 루프 — ARRIVED 이후 30초 창
# ─────────────────────────────────────────────────────────

async def wait_for_patient_response(
    frame_source: FrameSource,
    *,
    timeout_sec: float = WINDOW_SECONDS,
    poll_interval_sec: float = POLL_INTERVAL_SEC,
    detector=detect_labels,
) -> YoloOutcome:
    """ARRIVED 이후 30초 창을 굴리며 프레임을 폴링한다.

    창이 끝나면 누적된 라벨 통계로 ``decide_window_verdict()`` 호출.
    ``detector``는 테스트에서 주입 가능 (기본은 실제 YOLO 추론).
    """
    deadline = time.monotonic() + timeout_sec
    counts: dict[str, int] = {}

    while time.monotonic() < deadline:
        frame = await frame_source.grab()
        if frame is not None:
            try:
                labels = detector(frame)
            except Exception:  # noqa: BLE001 — 추론 오류는 로그만 남기고 폴링 지속
                log.exception("YOLO 추론 실패, 이번 프레임 건너뜀")
                labels = set()
            for label in labels:
                counts[label] = counts.get(label, 0) + 1
        await asyncio.sleep(poll_interval_sec)

    return decide_window_verdict(counts)
