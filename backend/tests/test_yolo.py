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
    frames = [b"f"] * 8
    labels_seq = [
        {"success"}, {"success"}, {"success"},
        {"failure"}, {"failure"}, {"failure"},
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
