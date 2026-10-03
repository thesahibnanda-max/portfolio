from http import HTTPStatus

from fastapi import APIRouter, Depends

from main.package.handler.dto import AccountsResponse, ApiResponse, ProfessionalResponse, ProfileResponse
from main.package.handler.json_response import PydanticJSONResponse
from main.package.handler.static_asset_routes import PROFILE_IMAGE_PATH, RESUME_PATH, versioned_url
from main.package.handler.request_context import RateLimitGuard, State
from main.package.service.data import CodeforcesDetails, GitHubDetails, LeetcodeDetails
from main.package.static.dto import Personality

router = APIRouter(prefix="/details", tags=["details"], dependencies=[Depends(RateLimitGuard("details"))])


@router.get("/professional", status_code=HTTPStatus.OK, response_model=ApiResponse[ProfessionalResponse])
def professional_details(state: State) -> PydanticJSONResponse:
    details = state.container.data_service.get_professional_details()
    resume_link = versioned_url(RESUME_PATH, state.container.static_loader.get_resume())
    return state.responder.ok(ProfessionalResponse(**dict(details), resume_link=resume_link))


@router.get("/leetcode", status_code=HTTPStatus.OK, response_model=ApiResponse[AccountsResponse[LeetcodeDetails]])
def leetcode_details(state: State) -> PydanticJSONResponse:
    accounts = state.container.data_service.get_leetcode_details()
    return state.responder.ok(AccountsResponse[LeetcodeDetails](accounts=accounts))


@router.get("/codeforces", status_code=HTTPStatus.OK, response_model=ApiResponse[AccountsResponse[CodeforcesDetails]])
def codeforces_details(state: State) -> PydanticJSONResponse:
    accounts = state.container.data_service.get_codeforces_details()
    return state.responder.ok(AccountsResponse[CodeforcesDetails](accounts=accounts))


@router.get("/github", status_code=HTTPStatus.OK, response_model=ApiResponse[AccountsResponse[GitHubDetails]])
def github_details(state: State) -> PydanticJSONResponse:
    accounts = state.container.data_service.get_github_details()
    return state.responder.ok(AccountsResponse[GitHubDetails](accounts=accounts))


@router.get("/profile", status_code=HTTPStatus.OK, response_model=ApiResponse[ProfileResponse])
async def profile_details(state: State) -> PydanticJSONResponse:
    loader = state.container.static_loader
    profile = ProfileResponse(**dict(loader.get_profile()), profile_image_url=versioned_url(PROFILE_IMAGE_PATH, loader.get_profile_image()))
    return state.responder.ok(profile)


@router.get("/personality", status_code=HTTPStatus.OK, response_model=ApiResponse[Personality])
async def personality_details(state: State) -> PydanticJSONResponse:
    return state.responder.ok(state.container.static_loader.get_personality())
