from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main.package.static
from main.config import AppConfig
from main.package.handler.static_asset_routes import resume_filename
from main.package.ratelimiter import RateLimitScope
from main.package.static import Profile, StaticLoader
from tests.main.package.handler.fakes import Harness, rate_limited

STATIC_DIR = Path(main.package.static.__file__).parent
PHOTO = (STATIC_DIR / "pfp.jpg").read_bytes()
RESUME = (STATIC_DIR / "resume.pdf").read_bytes()
IMAGE_PATH = "/details/profile/image"
RESUME_PATH = "/details/resume"
ASSETS = [(IMAGE_PATH, PHOTO, "image/jpeg"), (RESUME_PATH, RESUME, "application/pdf")]
ASSET_PATHS = [IMAGE_PATH, RESUME_PATH]


def _client(tmp_path: Path, config: AppConfig | None = None) -> TestClient:
    return Harness(tmp_path, config).client()


def _profile_named(name: str) -> Profile:
    profile = StaticLoader().get_profile()
    details = profile.profile_details.model_copy(update={"name": name})
    return profile.model_copy(update={"profile_details": details})


def test_profile_links_to_a_versioned_photo(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        profile = client.get("/details/profile").json()["data"]
        etag = client.get(IMAGE_PATH).headers["etag"].strip('"')

    assert profile["profile_image_url"] == f"{IMAGE_PATH}?v={etag}"
    assert "profile_image" not in profile


def test_professional_details_link_to_the_versioned_resume(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        professional = client.get("/details/professional").json()["data"]
        etag = client.get(RESUME_PATH).headers["etag"].strip('"')

    assert professional["resume_link"] == f"{RESUME_PATH}?v={etag}"
    assert "supabase" not in str(professional["resume_link"])


@pytest.mark.parametrize(("path", "content", "media_type"), ASSETS, ids=["photo", "resume"])
def test_versioned_asset_is_cached_for_a_year(config_env: str, tmp_path: Path, path: str, content: bytes, media_type: str) -> None:
    with _client(tmp_path) as client:
        etag = client.get(path).headers["etag"].strip('"')
        response = client.get(f"{path}?v={etag}")

    assert response.status_code == HTTPStatus.OK
    assert response.content == content
    assert response.headers["content-type"] == media_type
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["etag"] == f'"{etag}"'


@pytest.mark.parametrize("query", ["", "?v=stale0000000000", "?other=1"], ids=["none", "stale", "other"])
@pytest.mark.parametrize("path", ASSET_PATHS, ids=["photo", "resume"])
def test_unversioned_asset_must_revalidate(config_env: str, tmp_path: Path, path: str, query: str) -> None:
    with _client(tmp_path) as client:
        response = client.get(f"{path}{query}")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"].startswith('"')


def test_resume_opens_inline_with_a_readable_filename(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(RESUME_PATH)

    assert response.content.startswith(b"%PDF-")
    assert response.headers["content-disposition"] == 'inline; filename="Sahib_Nanda_Resume.pdf"'


def test_photo_has_no_content_disposition(config_env: str, tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert "content-disposition" not in client.get(IMAGE_PATH).headers


@pytest.mark.parametrize(
    ("name", "filename"),
    [
        ("Sahib Nanda", "Sahib_Nanda_Resume.pdf"),
        ('  Évil "Name"\r\nX-Header: 1 ', "vil_Name_X-Header_1_Resume.pdf"),
    ],
)
def test_resume_filename_is_header_safe(name: str, filename: str) -> None:
    assert resume_filename(_profile_named(name)) == filename


@pytest.mark.parametrize("path", ASSET_PATHS, ids=["photo", "resume"])
@pytest.mark.parametrize("header", ["{etag}", "W/{etag}", '"other", {etag}', "*"])
def test_matching_if_none_match_is_304(config_env: str, tmp_path: Path, path: str, header: str) -> None:
    with _client(tmp_path) as client:
        etag = client.get(path).headers["etag"]
        response = client.get(path, headers={"If-None-Match": header.format(etag=etag)})

    assert response.status_code == HTTPStatus.NOT_MODIFIED
    assert response.content == b""
    assert response.headers["etag"] == etag


@pytest.mark.parametrize(("path", "content", "media_type"), ASSETS, ids=["photo", "resume"])
def test_stale_if_none_match_gets_the_asset(config_env: str, tmp_path: Path, path: str, content: bytes, media_type: str) -> None:
    with _client(tmp_path) as client:
        response = client.get(path, headers={"If-None-Match": '"0000000000000000"'})

    assert (response.status_code, response.content) == (HTTPStatus.OK, content)


@pytest.mark.parametrize(("path", "content", "media_type"), ASSETS, ids=["photo", "resume"])
def test_head_returns_headers_only(config_env: str, tmp_path: Path, path: str, content: bytes, media_type: str) -> None:
    with _client(tmp_path) as client:
        response = client.head(path)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == media_type
    assert response.content == b""


@pytest.mark.parametrize("path", ASSET_PATHS, ids=["photo", "resume"])
def test_assets_are_never_rate_limited(config_env: str, tmp_path: Path, path: str) -> None:
    config = rate_limited(rate_limited(AppConfig.load(), "details", 2, RateLimitScope.IP), "details", 2, RateLimitScope.GLOBAL)
    with _client(tmp_path, config) as client:
        details = [client.get("/details/profile").status_code for _ in range(3)]
        assets = {client.get(path).status_code for _ in range(50)}

    assert details == [HTTPStatus.OK, HTTPStatus.OK, HTTPStatus.TOO_MANY_REQUESTS]
    assert assets == {HTTPStatus.OK}


@pytest.mark.parametrize(("path", "content", "media_type"), ASSETS, ids=["photo", "resume"])
def test_openapi_documents_the_media_type(config_env: str, tmp_path: Path, path: str, content: bytes, media_type: str) -> None:
    with _client(tmp_path) as client:
        operations = client.get("/openapi.json").json()["paths"][path]

    assert list(operations) == ["get"]
    assert media_type in operations["get"]["responses"]["200"]["content"]
