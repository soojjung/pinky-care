import asyncio
import json

import httpx
from httpx import ASGITransport

from app.main import app


def _base_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _read_status_events(response: httpx.Response, until_terminal: bool = True) -> list[str]:
    statuses: list[str] = []
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = json.loads(line[len("data:"):].strip())
        statuses.append(payload["status"])
        if until_terminal and payload["status"] in ("SUCCESS", "FAILED"):
            break
    return statuses


async def test_sse_streams_full_lifecycle_including_verifying() -> None:
    async with _base_client() as client:
        created = await client.post("/deliveries", json={"room": "104", "item": "약"})
        delivery_id = created.json()["id"]

        async def consume() -> list[str]:
            async with client.stream("GET", f"/deliveries/{delivery_id}/events") as response:
                return await _read_status_events(response)

        async def drive() -> None:
            # give the subscriber a beat to register before we publish
            await asyncio.sleep(0.1)
            await client.patch(
                f"/deliveries/{delivery_id}/robot-status", json={"status": "MOVING"},
            )
            await client.patch(
                f"/deliveries/{delivery_id}/robot-status", json={"status": "ARRIVED"},
            )
            await client.patch(
                f"/deliveries/{delivery_id}/verification", json={"result": "SUCCESS"},
            )

        consumer_task = asyncio.create_task(consume())
        await drive()
        statuses = await asyncio.wait_for(consumer_task, timeout=5)

    assert statuses == ["REQUESTED", "MOVING", "ARRIVED", "VERIFYING", "SUCCESS"]


async def test_sse_failed_path_emits_verifying_then_failed() -> None:
    async with _base_client() as client:
        created = await client.post("/deliveries", json={"room": "102", "item": "기저귀"})
        delivery_id = created.json()["id"]

        async def consume() -> list[str]:
            async with client.stream("GET", f"/deliveries/{delivery_id}/events") as response:
                return await _read_status_events(response)

        async def drive() -> None:
            await asyncio.sleep(0.1)
            await client.patch(
                f"/deliveries/{delivery_id}/robot-status", json={"status": "MOVING"},
            )
            await client.patch(
                f"/deliveries/{delivery_id}/robot-status", json={"status": "ARRIVED"},
            )
            await client.patch(
                f"/deliveries/{delivery_id}/verification",
                json={"result": "FAILED", "reason": "물품 인식 실패"},
            )

        consumer_task = asyncio.create_task(consume())
        await drive()
        statuses = await asyncio.wait_for(consumer_task, timeout=5)

    assert statuses == ["REQUESTED", "MOVING", "ARRIVED", "VERIFYING", "FAILED"]


async def test_sse_reconnect_to_terminal_delivery_sends_snapshot_and_closes() -> None:
    async with _base_client() as client:
        created = await client.post("/deliveries", json={"room": "103", "item": "물티슈"})
        delivery_id = created.json()["id"]
        await client.patch(
            f"/deliveries/{delivery_id}/robot-status", json={"status": "MOVING"},
        )
        await client.patch(
            f"/deliveries/{delivery_id}/robot-status", json={"status": "ARRIVED"},
        )
        await client.patch(
            f"/deliveries/{delivery_id}/verification", json={"result": "SUCCESS"},
        )

        async with client.stream("GET", f"/deliveries/{delivery_id}/events") as response:
            statuses = await asyncio.wait_for(
                _read_status_events(response), timeout=3,
            )

    assert statuses == ["SUCCESS"]


async def test_sse_missing_delivery_returns_404() -> None:
    async with _base_client() as client:
        r = await client.get("/deliveries/unknown/events")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"
