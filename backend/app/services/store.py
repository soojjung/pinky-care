from app.models.delivery import Delivery


class DeliveryStore:
    def __init__(self) -> None:
        self._items: dict[str, Delivery] = {}

    def add(self, delivery: Delivery) -> None:
        self._items[delivery.id] = delivery

    def get(self, delivery_id: str) -> Delivery | None:
        return self._items.get(delivery_id)


store = DeliveryStore()
