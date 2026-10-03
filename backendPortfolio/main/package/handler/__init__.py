"""
The HTTP layer: FastAPI routes over the services, with request and response
DTOs, one place that maps every exception to a status, rate limiting on
every route, and the gunicorn plus uvicorn runtime.

Exports:
    ApplicationFactory: builds the FastAPI app.
    ServiceContainer (with UpstreamTransports): the composition root that
    wires every service from AppConfig.
    GunicornSettings, FastUvicornWorker: the process runtime.
    Responder, PydanticJSONResponse: build every response.
    ErrorCatalog, ErrorRule, ExceptionHandler: map exceptions to responses.
    ClientIpResolver, RateLimitGuard, HandlerState: request context.
    The request and response DTOs, HandlerError and its subclasses.

Runtime and why it is fast:
    gunicorn -c gunicorn.conf.py starts one master and config.app.workers
    worker processes (default 1) of FastUvicornWorker, a
    uvicorn_worker.UvicornWorker pinned to uvloop (libuv event loop) and
    httptools (the llhttp C parser); both keep the GIL disabled on 3.14t.
    gunicorn.conf.py reads every value from GunicornSettings.from_config, and
    the app is built by the factory main.app:create_app() inside each worker,
    after the fork, so thread pools and SQLite belong to the worker.
    Every service is synchronous, so blocking routes are plain def functions:
    Starlette runs them on the AnyIO threadpool (thread_pool_size threads,
    default 64), truly in parallel on every core because the GIL is off. One
    worker is the default because the rate limiter, data cache and Groq key
    rotation are in memory; more workers would each keep their own.
    Routes that never block (health, profile, personality, photo, résumé)
    are async def and skip the threadpool hop.
    Responses are built by Responder as PydanticJSONResponse, whose render()
    is pydantic-core's Rust to_json, so FastAPI's re-validation,
    jsonable_encoder and stdlib json are skipped (orjson has no 3.14t
    wheel). response_model is declared only for the OpenAPI schema at /docs.
    Middleware is pure ASGI (no BaseHTTPMiddleware task overhead).

Envelopes:
    Success: ApiResponse {status, timestamp, data}, where status repeats the
    HTTP status and timestamp is UTC.
    Error: ErrorResponse {status, timestamp, error, message, details}, where
    error is a stable code and details lists {field, message} per invalid
    input. DELETE answers 204 with no body.
    Every status in code is an http.HTTPStatus member, never a bare int.

Routes (rate-limit api in brackets, see main.package.ratelimiter):
    GET    /health                           200 [none]
    POST   /sessions                         201 SessionResponse [create_session]
    POST   /chats            {title?}        201 ChatSummaryResponse [chat_write]
    GET    /chats                            200 ChatListResponse [chat_read]
    GET    /chats/{chat_id}                  200 ChatResponse [chat_read]
    PATCH  /chats/{chat_id}  {title}         200 ChatSummaryResponse [chat_write]
    DELETE /chats/{chat_id}                  204 [chat_write]
    POST   /chats/{chat_id}/messages {message}         200 ChatReplyResponse [chat_message]
        ChatReplyResponse is {chat, answer, scope, required_contexts}; the
        contexts are the knowledge domains the answer drew on, for source chips.
    POST   /chats/{chat_id}/messages/stream {message}  200 text/event-stream [chat_message]
    GET    /details/professional|leetcode|codeforces|github|profile|personality  200 [details]
        /details/profile also returns profile_image_url, the relative path
        "/details/profile/image?v=<etag>" (the etag changes with the photo).
        /details/professional returns ProfessionalResponse, whose
        resume_link is the relative path "/details/resume?v=<etag>" (the
        etag changes with the résumé).
    GET|HEAD /details/profile/image  200 image/jpeg, or 304 [not rate limited]
    GET|HEAD /details/resume         200 application/pdf, or 304 [not rate limited]
        Both serve a StaticAsset from memory with ETag and Cache-Control
        "public, max-age=31536000, immutable"; If-None-Match with the
        current ETag (weak or strong, or "*") answers 304. The résumé also
        sends Content-Disposition: inline; filename="<Name>_Resume.pdf",
        built from the profile name, so it opens in the browser and saves
        with a readable name. Deliberately outside every rate limit: they
        are static bytes that browsers and proxies cache for a year, so a
        busy visitor can never make the photo or the résumé fail.
    POST   /contact {email, subject, message}  200 ContactResponse {status: "SENT", reply_to, sent_at} [contact]
        Mails the message to the owner (main.package.service.contact); no
        session needed. The email is validated (syntax and a DNS mail
        check) and normalized (trimmed, lowercased); reply_to echoes the
        normalized address. The send is synchronous, so 200 means the SMTP
        server accepted it.
    Every /chats route needs the X-Session-Id header from POST /sessions.
    Request bodies are strict (no coercion) and reject unknown fields.
    Length and blank rules live in the services (MessageValidator and the
    repository's title rule) and still answer 400.

Headers:
    X-Session-Id: the session id, sent by the client.
    X-Forwarded-For: the first entry is the client IP when
    config.app.trust_forwarded_for is true (behind Caddy, which overwrites
    it); otherwise the socket peer is used.
    Retry-After: whole seconds, on 429.
    CORS allows config.app.cors.allow_origins, every method and header, and
    exposes Retry-After.

Rate limiting:
    RateLimitGuard(api) is a route dependency, so it runs before the body is
    validated and before any service call. It checks IP, then session (only
    a well-formed UUID header counts, so random headers cannot grow the
    store), then global, and a refusal answers 429.

Errors (ErrorCatalog.default(), first match along the exception's MRO):
    400 VALIDATION_ERROR: RequestValidationError (missing header, bad or
        extra body fields, wrong types, invalid JSON) with details,
        InvalidChatMessageError (empty or too long), InvalidRepositoryArgumentError
        (malformed id, bad title), InvalidContactSubmissionError (with
        details [{field: "body.<field>", message}]).
    401 SESSION_EXPIRED: SessionNotFoundError.
    404 CHAT_NOT_FOUND: ChatNotFoundError; NOT_FOUND for an unknown route.
    405 METHOD_NOT_ALLOWED, with Allow.
    409 CHAT_FULL: ChatFullError.
    413 CONTENT_TOO_LARGE: a body over config.app.max_body_bytes, declared by
        Content-Length or counted while a chunked body streams in.
    429 RATE_LIMITED: RateLimitExceededError, with Retry-After.
    502 UPSTREAM_ERROR: GroqClientError, DataSourceUnavailableError,
        DataSourceResponseError, OrchestratorResponseError, WorkerResponseError.
    503 UPSTREAM_BUSY: GroqRateLimitError.
    503 MAIL_UNAVAILABLE: MailDeliveryError (every SMTP account failed).
    500 INTERNAL_ERROR: RepositoryOperationError and anything else.
    4xx answers carry the exception's own (user-safe) message. 5xx answers
    carry a fixed message and the traceback is logged, so internals never
    leak. Starlette HTTPExceptions keep their status, with its name as the
    code. UnhandledErrorMiddleware turns anything left into a 500 envelope
    inside the CORS middleware, so even errors carry CORS headers. A new
    error is one new ErrorRule.

Streaming (POST /chats/{chat_id}/messages/stream, FastAPI EventSourceResponse):
    The stream is opened by the ChatStreamOpener dependency, which runs
    validation, the session and chat lookup, routing and the Groq request
    before any byte is sent, so those errors answer with their real status.
    Then:
        event: token  data: StreamTokenResponse {text}
        event: done   data: ApiResponse[ChatReplyResponse], once, after saving
        event: error  data: ErrorResponse, if the stream fails part way
    FastAPI adds keep-alive comments and the no-cache and X-Accel-Buffering
    headers. When the client disconnects, the dependency's teardown cancels
    the Groq stream, so nothing is saved and the visitor can retry.

ServiceContainer.from_config(config, transports=UpstreamTransports()):
    Builds the TTL store factory, the four clients, DataService, StaticLoader,
    ContextAggregator, SqliteChatRepository, ChatService, the Mailer,
    EmailNormalizer and ContactService, and RateLimiter. UpstreamTransports
    lets tests pass httpx transports, an SmtpConnector and a dnspython
    resolver. close() closes
    everything in reverse order; if building fails part way, what was built
    is closed before the error propagates.

ApplicationFactory(*, config, container_factory, responder=None, catalog=None):
    create() returns the app. Its lifespan sets the threadpool size, builds
    the container off the event loop, stores a HandlerState on app.state and
    closes the container on shutdown.

Running (from backendPortfolio/, GROQ_API_KEYS set):
    venv/bin/gunicorn -c gunicorn.conf.py
    venv/bin/uvicorn main.app:create_app --factory --loop uvloop --http httptools --reload

Thread safety:
    Routes keep no state; every service they call is thread-safe on the
    free-threaded build, and Responder, ExceptionHandler and the catalog are
    immutable.
"""

from .application import ApplicationFactory
from .container import ServiceContainer, UpstreamTransports
from .dto import (
    AccountsResponse,
    ProfessionalResponse,
    ProfileResponse,
    ContactRequest,
    ContactResponse,
    ApiResponse,
    ChatListResponse,
    ChatReplyResponse,
    ChatResponse,
    ChatSummaryResponse,
    CreateChatRequest,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    MessageResponse,
    RenameChatRequest,
    SendMessageRequest,
    SessionResponse,
    StreamTokenResponse,
)
from .error_catalog import ErrorCatalog, ErrorRule
from .exception_handler import ExceptionHandler
from .exceptions import HandlerError, InvalidHandlerSettingError, RequestBodyTooLargeError
from .json_response import PydanticJSONResponse
from .request_context import ClientIpResolver, HandlerState, RateLimitGuard
from .responder import Responder
from .server_settings import GunicornSettings
from .worker import FastUvicornWorker

__all__ = [
    "ApplicationFactory",
    "ServiceContainer",
    "UpstreamTransports",
    "GunicornSettings",
    "FastUvicornWorker",
    "Responder",
    "PydanticJSONResponse",
    "ErrorCatalog",
    "ErrorRule",
    "ExceptionHandler",
    "ClientIpResolver",
    "RateLimitGuard",
    "HandlerState",
    "CreateChatRequest",
    "RenameChatRequest",
    "SendMessageRequest",
    "ProfessionalResponse",
    "ProfileResponse",
    "ContactRequest",
    "ContactResponse",
    "ApiResponse",
    "ErrorResponse",
    "ErrorDetail",
    "HealthResponse",
    "SessionResponse",
    "ChatSummaryResponse",
    "ChatResponse",
    "ChatListResponse",
    "MessageResponse",
    "ChatReplyResponse",
    "StreamTokenResponse",
    "AccountsResponse",
    "HandlerError",
    "InvalidHandlerSettingError",
    "RequestBodyTooLargeError",
]
