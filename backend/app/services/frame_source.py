"""ROS2가 업로드한 카메라 프레임을 배송별로 캐시하는 저장소.

각 배송에 대해 **가장 최신 프레임 1장만** 유지한다. YOLO 폴링 루프
(``yolo.wait_for_patient_response``)가 ``grab()``으로 꺼내 씀.
"""
from __future__ import annotations

import threading


class CachedImageSource:
    """delivery_id → 최신 JPEG 바이트 1장을 담는 인메모리 캐시.

    - ``put(id, bytes)``     — 새 프레임으로 덮어씀
    - ``grab(id)`` (async)   — 최신 프레임 반환. 없으면 ``None``
    - ``clear(id)``          — terminal 상태 도달 시 캐시 해제

    ROS2 노드가 초당 1회 ``POST /deliveries/{id}/image``로 프레임을 올리는
    사이, 백엔드 폴링 루프도 초당 1회 ``grab()``. 두 스레드/이벤트 루프가
    같은 dict을 만지므로 ``lock``으로 보호한다.
    """

    def __init__(self) -> None:
        self._latest: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put(self, delivery_id: str, image_bytes: bytes) -> None:
        with self._lock:
            self._latest[delivery_id] = image_bytes

    async def grab(self, delivery_id: str) -> bytes | None:
        # 락은 짧게 잡고 빠져나온다. async 인터페이스는 향후 원격 저장소
        # 교체 여지를 남기려는 것 — 지금은 순수 in-memory.
        with self._lock:
            return self._latest.get(delivery_id)

    def clear(self, delivery_id: str) -> None:
        with self._lock:
            self._latest.pop(delivery_id, None)


class BoundFrameSource:
    """특정 delivery_id 하나에 묶인 ``FrameSource`` 어댑터.

    ``yolo.wait_for_patient_response()`` 는 ``FrameSource`` 프로토콜
    (``grab() -> bytes | None``, delivery_id 인자 없음)을 기대한다.
    ``CachedImageSource``는 여러 배송을 관리하므로, 이 어댑터로 감싸서 준다.
    """

    def __init__(self, cache: CachedImageSource, delivery_id: str) -> None:
        self._cache = cache
        self._delivery_id = delivery_id

    async def grab(self) -> bytes | None:
        return await self._cache.grab(self._delivery_id)


# 전역 싱글턴 — API 핸들러와 폴링 루프가 공유
frame_cache = CachedImageSource()
