from http import HTTPStatus

from fastapi import APIRouter, Depends
from starlette.requests import Request

from main.package.handler.dto import ApiResponse, ContactRequest, ContactResponse
from main.package.handler.json_response import PydanticJSONResponse
from main.package.handler.request_context import RateLimitGuard, State
from main.package.service.contact import ContactSubmission

SENT = "SENT"

router = APIRouter(tags=["contact"])


@router.post(
    "/contact",
    status_code=HTTPStatus.OK,
    response_model=ApiResponse[ContactResponse],
    dependencies=[Depends(RateLimitGuard("contact"))],
)
def send_contact(body: ContactRequest, request: Request, state: State) -> PydanticJSONResponse:
    receipt = state.container.contact_service.submit(
        ContactSubmission(
            email=body.email,
            subject=body.subject,
            message=body.message,
            client_ip=state.client_ip_resolver.resolve(request),
        )
    )
    return state.responder.ok(ContactResponse(status=SENT, reply_to=receipt.reply_to, sent_at=receipt.sent_at))
