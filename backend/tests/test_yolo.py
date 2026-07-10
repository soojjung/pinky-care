"""backend/app/services/yolo.py 판정 로직 단위 테스트.

실제 모델 로드 없이 결정 로직만 검증한다. ``detect_labels``는 monkeypatch로 대체.
"""
import asyncio

import pytest

from app.models.delivery import FailReason, VerificationResult
from app.services import yolo


# ── decide_window_verdict — 순수 규칙 ────────────────────

def test_success_only_yields_success():
    outcome = yolo.decide_window_verdict({"success": 5})
    assert outcome == yolo.YoloOutcome(VerificationResult.SUCCESS, None)


def test_failure_only_yields_x_card_detected():
    outcome = yolo.decide_window_verdict({"failure": 5})
    assert outcome.result == VerificationResult.FAILED
    assert outcome.reason == FailReason.X_CARD_DETECTED


def test_both_labels_yield_ambiguous():
    outcome = yolo.decide_window_verdict({"success": 4, "failure": 4})
    assert outcome.result == VerificationResult.FAILED
    assert outcome.reason == FailReason.AMBIGUOUS_BOTH_CARDS


def test_empty_counts_yield_timeout():
    outcome = yolo.decide_window_verdict({})
    assert outcome.result == VerificationResult.FAILED
    assert outcome.reason == FailReason.TIMEOUT_NO_CARD


def test_below_threshold_labels_not_confirmed():
    # MIN_CONFIRMATIONS(3) 미만이면 확정 취급 안 함 → TIMEOUT
    outcome = yolo.decide_window_verdict({"success": 2})
    assert outcome.reason == FailReason.TIMEOUT_NO_CARD


def test_one_below_one_above_only_confirmed_counts():
    # failure만 확정 → X_CARD_DETECTED (success는 미확정)
    outcome = yolo.decide_window_verdict({"success": 1, "failure": 5})
    assert outcome.reason == FailReason.X_CARD_DETECTED


# ── wait_for_patient_response — 폴링 루프 ───────────────

class _FakeSource:
    """지정한 순서대로 프레임을 뱉는 fake FrameSource."""

    def __init__(self, frames: list[bytes | None]) -> None:
        self._frames = list(frames)

    async def grab(self) -> bytes | None:
        if not self._frames:
            return None
        return self._frames.pop(0)


def _make_detector(seq: list[set[str]]):
    """호출될 때마다 미리 지정된 라벨 집합을 순서대로 돌려주는 fake 추론기."""
    iterator = iter(seq)

    def _detect(_frame: bytes) -> set[str]:
        return next(iterator, set())

    return _detect


async def test_polling_success_when_success_confirmed_within_window():
    # 짧은 창 안에서 success 라벨 3회 확정
    frames = [b"f1", b"f2", b"f3", b"f4", b"f5"]
    labels_seq = [{"success"}, {"success"}, {"success"}, set(), set()]
    outcome = await yolo.wait_for_patient_response(
        _FakeSource(frames),
        timeout_sec=0.5,
        poll_interval_sec=0.05,
        detector=_make_detector(labels_seq),
    )
    assert outcome.result == VerificationResult.SUCCESS
    assert outcome.reason is None


async def test_polling_failure_when_only_failure_confirmed():
    frames = [b"f1", b"f2", b"f3", b"f4"]
    labels_seq = [{"failure"}, {"failure"}, {"failure"}, set()]
    outcome = await yolo.wait_for_patient_response(
        _FakeSource(frames),
        timeout_sec=0.5,
        poll_interval_sec=0.05,
        detector=_make_detector(labels_seq),
    )
    assert outcome.result == VerificationResult.FAILED
    assert outcome.reason == FailReason.X_CARD_DETECTED


async def test_polling_ambiguous_when_both_confirmed():
    """X 가 먼저 한 번이라도 보이면 조기 종료하지 않고 끝까지 관찰 → AMBIGUOUS.

    라벨을 번갈아 준다: success 가 확정(3회)되기 전에 failure 가 등장하므로
    조기 판정 조건(failure 0회)이 깨져 창을 끝까지 돌린다.
    """
    frames = [b"f"] * 8
    labels_seq = [
        {"success"}, {"failure"}, {"success"},
        {"failure"}, {"success"}, {"failure"},
        set(), set(),
    ]
    outcome = await yolo.wait_for_patient_response(
        _FakeSource(frames),
        timeout_sec=0.8,
        poll_interval_sec=0.05,
        detector=_make_detector(labels_seq),
    )
    assert outcome.result == VerificationResult.FAILED
    assert outcome.reason == FailReason.AMBIGUOUS_BOTH_CARDS


async def test_polling_early_success_exits_before_window_ends():
    """success 확정 + failure 0회 → 창이 끝나기 전에 즉시 SUCCESS 로 반환."""
    frames = [b"f"] * 50
    labels_seq = [{"success"}] * 50
    started = asyncio.get_running_loop().time()
    outcome = await yolo.wait_for_patient_response(
        _FakeSource(frames),
        timeout_sec=5.0,          # 창은 5초지만
        poll_interval_sec=0.05,   # 3프레임(≈0.15s)만에 확정되어야 한다
        detector=_make_detector(labels_seq),
    )
    elapsed = asyncio.get_running_loop().time() - started
    assert outcome == yolo.YoloOutcome(VerificationResult.SUCCESS, None)
    assert elapsed < 5.0, "조기 판정이 안 되고 창을 끝까지 기다렸다"


async def test_polling_early_success_wins_over_later_failure():
    """조기 판정 계약: 먼저 확정된 success 가 이기고, 그 뒤 X 카드는 보지 않는다.

    성공을 즉시 확정해 로봇을 빨리 복귀시키기 위한 의도적 트레이드오프.
    (X 를 먼저 보여주면 위 AMBIGUOUS 테스트처럼 끝까지 관찰한다)
    """
    frames = [b"f"] * 8
    labels_seq = [
        {"success"}, {"success"}, {"success"},   # 여기서 조기 확정
        {"failure"}, {"failure"}, {"failure"},   # 이후는 관찰되지 않음
        set(), set(),
    ]
    outcome = await yolo.wait_for_patient_response(
        _FakeSource(frames),
        timeout_sec=0.8,
        poll_interval_sec=0.05,
        detector=_make_detector(labels_seq),
    )
    assert outcome == yolo.YoloOutcome(VerificationResult.SUCCESS, None)


async def test_polling_timeout_when_no_frames():
    outcome = await yolo.wait_for_patient_response(
        _FakeSource([]),
        timeout_sec=0.15,
        poll_interval_sec=0.05,
        detector=_make_detector([]),
    )
    assert outcome.result == VerificationResult.FAILED
    assert outcome.reason == FailReason.TIMEOUT_NO_CARD


async def test_polling_detector_error_does_not_abort_loop():
    frames = [b"bad", b"ok", b"ok", b"ok"]

    def _detector(frame: bytes) -> set[str]:
        if frame == b"bad":
            raise RuntimeError("simulated inference error")
        return {"success"}

    outcome = await yolo.wait_for_patient_response(
        _FakeSource(frames),
        timeout_sec=0.5,
        poll_interval_sec=0.05,
        detector=_detector,
    )
    assert outcome.result == VerificationResult.SUCCESS
