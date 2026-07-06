import asyncio

from app.models.delivery import Delivery, Status

Payload = tuple[Status, str]


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[Payload]]] = {}

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


broadcaster = Broadcaster()
