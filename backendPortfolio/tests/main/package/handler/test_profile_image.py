from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main.package.static
from main.config import AppConfig
from main.package.ratelimiter import RateLimitScope
from tests.main.package.handler.fakes import Harness, rate_limited

PHOTO = (Path(main.package.static.__file__).parent / "pfp.jpg").read_bytes()
IMAGE_PATH = "/details/profile/image"


def _client(tmp_path: Path, config: AppConfig | None = None) -> TestClient:
    return Harness(tmp_path, config).client()


def test_profile_links_to_a_versioned_photo(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        profile = client.get("/details/profile").json()["data"]
        etag = client.get(IMAGE_PATH).headers["etag"].strip('"')

    assert profile["profile_image_url"] == f"{IMAGE_PATH}?v={etag}"
    assert "profile_image" not in profile


def test_photo_is_served_with_long_lived_caching(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(f"{IMAGE_PATH}?v=anything")

    assert response.status_code == HTTPStatus.OK
    assert response.content == PHOTO
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["etag"].startswith('"') and response.headers["etag"].endswith('"')


@pytest.mark.parametrize("header", ["{etag}", "W/{etag}", '"other", {etag}', "*"])
def test_matching_if_none_match_is_304(config_env: str, tmp_path: Path, header: str) -> None:
    with _client(tmp_path) as client:
        etag = client.get(IMAGE_PATH).headers["etag"]
        response = client.get(IMAGE_PATH, headers={"If-None-Match": header.format(etag=etag)})

    assert response.status_code == HTTPStatus.NOT_MODIFIED
    assert response.content == b""
    assert response.headers["etag"] == etag


def test_stale_if_none_match_gets_the_photo(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(IMAGE_PATH, headers={"If-None-Match": '"0000000000000000"'})

    assert (response.status_code, response.content) == (HTTPStatus.OK, PHOTO)


def test_head_returns_headers_only(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.head(IMAGE_PATH)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b""


def test_photo_is_never_rate_limited(config_env: str, tmp_path: Path) -> None:
    config = rate_limited(rate_limited(AppConfig.load(), "details", 2, RateLimitScope.IP), "details", 2, RateLimitScope.GLOBAL)
    with _client(tmp_path, config) as client:
        details = [client.get("/details/profile").status_code for _ in range(3)]
        photos = {client.get(IMAGE_PATH).status_code for _ in range(50)}

    assert details == [HTTPStatus.OK, HTTPStatus.OK, HTTPStatus.TOO_MANY_REQUESTS]
    assert photos == {HTTPStatus.OK}


def test_openapi_documents_the_photo_as_jpeg(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        operations = client.get("/openapi.json").json()["paths"][IMAGE_PATH]

    assert list(operations) == ["get"]
    assert "image/jpeg" in operations["get"]["responses"]["200"]["content"]
