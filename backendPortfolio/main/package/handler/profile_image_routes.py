from http import HTTPStatus

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

from main.package.handler.request_context import State
from main.package.static.dto import ProfileImage

PROFILE_IMAGE_PATH = "/details/profile/image"
CACHE_CONTROL = "public, max-age=31536000, immutable"
_WEAK_PREFIX = "W/"

router = APIRouter(tags=["details"])


def profile_image_url(image: ProfileImage) -> str:
    return f"{PROFILE_IMAGE_PATH}?v={image.etag}"


def _quoted(etag: str) -> str:
    return f'"{etag}"'


def _matches(if_none_match: str | None, etag: str) -> bool:
    if if_none_match is None:
        return False
    candidates = [candidate.strip().removeprefix(_WEAK_PREFIX) for candidate in if_none_match.split(",")]
    return "*" in candidates or etag in candidates


@router.get(
    PROFILE_IMAGE_PATH,
    response_class=Response,
    responses={
        HTTPStatus.OK: {"content": {"image/jpeg": {}}, "description": "The profile photo"},
        HTTPStatus.NOT_MODIFIED: {"description": "The cached photo is still current"},
    },
)
async def profile_image(request: Request, state: State) -> Response:
    image = state.container.static_loader.get_profile_image()
    etag = _quoted(image.etag)
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if _matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=HTTPStatus.NOT_MODIFIED, headers=headers)
    return Response(content=image.content, media_type=image.media_type, headers=headers)


router.add_api_route(
    PROFILE_IMAGE_PATH,
    profile_image,
    methods=["HEAD"],
    response_class=Response,
    include_in_schema=False,
)
