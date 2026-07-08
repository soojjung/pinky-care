"""POST /deliveries/{id}/image — ROS2 카메라 프레임 업로드."""
from fastapi.testclient import TestClient

from app.services.frame_source import frame_cache


_JPEG_STUB = b"\xff\xd8\xff\xe0\x00\x10JFIFdummy"


def test_upload_returns_204_and_caches_bytes(client: TestClient, arrived_id: str) -> None:
    r = client.post(
        f"/deliveries/{arrived_id}/image",
        files={"image": ("frame.jpg", _JPEG_STUB, "image/jpeg")},
    )
    assert r.status_code == 204
    assert not r.content

    # 캐시가 최신 프레임 1장을 보관 중
    cached = frame_cache._latest[arrived_id]
    assert cached == _JPEG_STUB


def test_upload_overwrites_previous_frame(client: TestClient, arrived_id: str) -> None:
    client.post(
        f"/deliveries/{arrived_id}/image",
        files={"image": ("f1.jpg", b"first", "image/jpeg")},
    )
    client.post(
        f"/deliveries/{arrived_id}/image",
        files={"image": ("f2.jpg", b"second", "image/jpeg")},
    )
    assert frame_cache._latest[arrived_id] == b"second"


def test_upload_missing_delivery_returns_404(client: TestClient) -> None:
    r = client.post(
        "/deliveries/unknown/image",
        files={"image": ("frame.jpg", _JPEG_STUB, "image/jpeg")},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_upload_empty_body_returns_422(client: TestClient, arrived_id: str) -> None:
    r = client.post(
        f"/deliveries/{arrived_id}/image",
        files={"image": ("empty.jpg", b"", "image/jpeg")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
