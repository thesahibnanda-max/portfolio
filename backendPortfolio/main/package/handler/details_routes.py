from http import HTTPStatus

from fastapi import APIRouter, Depends

from main.package.handler.dto import AccountsResponse, ApiResponse, ProfileResponse
from main.package.handler.json_response import PydanticJSONResponse
from main.package.handler.profile_image_routes import profile_image_url
from main.package.handler.request_context import RateLimitGuard, State
from main.package.service.data import CodeforcesDetails, GitHubDetails, LeetcodeDetails, ProfessionalDetails
from main.package.static.dto import Personality

router = APIRouter(prefix="/details", tags=["details"], dependencies=[Depends(RateLimitGuard("details"))])


@router.get("/professional", status_code=HTTPStatus.OK, response_model=ApiResponse[ProfessionalDetails])
def professional_details(state: State) -> PydanticJSONResponse:
    return state.responder.ok(state.container.data_service.get_professional_details())


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
    profile = ProfileResponse(**dict(loader.get_profile()), profile_image_url=profile_image_url(loader.get_profile_image()))
    return state.responder.ok(profile)


@router.get("/personality", status_code=HTTPStatus.OK, response_model=ApiResponse[Personality])
async def personality_details(state: State) -> PydanticJSONResponse:
    return state.responder.ok(state.container.static_loader.get_personality())
