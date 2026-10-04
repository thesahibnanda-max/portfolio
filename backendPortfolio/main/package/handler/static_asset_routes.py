import re
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

from main.package.handler.request_context import State
from main.package.static.dto import Profile, StaticAsset

PROFILE_IMAGE_PATH = "/details/profile/image"
RESUME_PATH = "/details/resume"
CACHE_CONTROL = "public, max-age=31536000, immutable"
REVALIDATE_CACHE_CONTROL = "no-cache"
VERSION_PARAMETER = "v"
_WEAK_PREFIX = "W/"
_UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^A-Za-z0-9_-]+")

router = APIRouter(tags=["details"])


def versioned_url(path: str, asset: StaticAsset) -> str:
    return f"{path}?{VERSION_PARAMETER}={asset.etag}"


def resume_filename(profile: Profile) -> str:
    name = _UNSAFE_FILENAME_CHARACTERS.sub("_", profile.profile_details.name).strip("_")
    return f"{name}_Resume.pdf"


def _quoted(etag: str) -> str:
    return f'"{etag}"'


def _matches(if_none_match: str | None, etag: str) -> bool:
    if if_none_match is None:
        return False
    candidates = [candidate.strip().removeprefix(_WEAK_PREFIX) for candidate in if_none_match.split(",")]
    return "*" in candidates or etag in candidates


def _asset_response(request: Request, asset: StaticAsset, extra_headers: Mapping[str, str]) -> Response:
    etag = _quoted(asset.etag)
    versioned = request.query_params.get(VERSION_PARAMETER) == asset.etag
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL if versioned else REVALIDATE_CACHE_CONTROL, **extra_headers}
    if _matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)
    return Response(content=asset.content, media_type=asset.media_type, headers=headers)


@router.get(
    PROFILE_IMAGE_PATH,
    response_class=Response,
    responses={
        HTTPStatus.OK: {"content": {"image/jpeg": {}}, "description": "The profile photo"},
        HTTPStatus.NOT_MODIFIED: {"description": "The cached photo is still current"},
    },
)
async def profile_image(request: Request, state: State) -> Response:
    return _asset_response(request, state.container.static_loader.get_profile_image(), {})


@router.get(
    RESUME_PATH,
    response_class=Response,
    responses={
        HTTPStatus.OK: {"content": {"application/pdf": {}}, "description": "The résumé"},
        HTTPStatus.NOT_MODIFIED: {"description": "The cached résumé is still current"},
    },
)
async def resume(request: Request, state: State) -> Response:
    loader = state.container.static_loader
    disposition = f'inline; filename="{resume_filename(loader.get_profile())}"'
    return _asset_response(request, loader.get_resume(), {"Content-Disposition": disposition})


router.add_api_route(PROFILE_IMAGE_PATH, profile_image, methods=["HEAD"], response_class=Response, include_in_schema=False)
router.add_api_route(RESUME_PATH, resume, methods=["HEAD"], response_class=Response, include_in_schema=False)
