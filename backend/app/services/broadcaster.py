import asyncio

from app.models.delivery import Delivery, Status

Payload = tuple[Status, str]


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[Payload]]] = {}
        # 전역 "새 배송 생성" 스트림 구독자 (로봇 미션 디스패처가 구독)
        self._new_subscribers: list[asyncio.Queue[str]] = []

    def subscribe(self, delivery_id: str) -> asyncio.Queue[Payload]:
        queue: asyncio.Queue[Payload] = asyncio.Queue()
        self._subscribers.setdefault(delivery_id, []).append(queue)
        return queue

    def unsubscribe(self, delivery_id: str, queue: asyncio.Queue[Payload]) -> None:
        subs = self._subscribers.get(delivery_id)
        if subs is None:
            return
        try:
            subs.remove(queue)
        except ValueError:
            pass
        if not subs:
            self._subscribers.pop(delivery_id, None)

    def publish(self, delivery: Delivery) -> None:
        subs = self._subscribers.get(delivery.id)
        if not subs:
            return
        snapshot = delivery.model_dump_json(by_alias=True)
        payload: Payload = (delivery.status, snapshot)
        for queue in list(subs):
            queue.put_nowait(payload)

    # ── 전역 새 배송 스트림 (로봇 미션 디스패처용) ──

    def subscribe_new(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._new_subscribers.append(queue)
        return queue

    def unsubscribe_new(self, queue: asyncio.Queue[str]) -> None:
        try:
            self._new_subscribers.remove(queue)
        except ValueError:
            pass

    def publish_new(self, delivery: Delivery) -> int:
        """새로 생성된 배송 스냅샷을 전역 구독자에게 push. 전송된 구독자 수 반환."""
        snapshot = delivery.model_dump_json(by_alias=True)
        subs = list(self._new_subscribers)
        for queue in subs:
            queue.put_nowait(snapshot)
        return len(subs)

    def new_subscriber_count(self) -> int:
        return len(self._new_subscribers)


broadcaster = Broadcaster()
