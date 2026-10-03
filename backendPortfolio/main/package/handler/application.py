from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from main.config import AppConfig
from main.package.handler import (
    chat_routes,
    contact_routes,
    details_routes,
    health_routes,
    profile_image_routes,
    session_routes,
)
from main.package.handler.container import ServiceContainer
from main.package.handler.error_catalog import ErrorCatalog
from main.package.handler.exception_handler import ExceptionHandler
from main.package.handler.json_response import PydanticJSONResponse
from main.package.handler.middleware import BodySizeLimitMiddleware, UnhandledErrorMiddleware
from main.package.handler.request_context import (
    FORWARDED_FOR_HEADER,
    SESSION_HEADER,
    ClientIpResolver,
    HandlerState,
)
from main.package.handler.responder import Responder

TITLE = "Backend Portfolio"
EXPOSED_HEADERS = ("Retry-After",)


class ApplicationFactory:
    def __init__(
        self,
        *,
        config: AppConfig,
        container_factory: Callable[[AppConfig], ServiceContainer],
        responder: Responder | None = None,
        catalog: ErrorCatalog | None = None,
    ) -> None:
        self._config = config
        self._container_factory = container_factory
        self._responder = responder or Responder()
        self._exception_handler = ExceptionHandler(catalog=catalog or ErrorCatalog.default(), responder=self._responder)
        self._client_ip_resolver = ClientIpResolver(trust_forwarded_for=config.app.trust_forwarded_for)

    def create(self) -> FastAPI:
        app = FastAPI(title=TITLE, default_response_class=PydanticJSONResponse, lifespan=self._lifespan)

        for router in (
            health_routes.router,
            session_routes.router,
            chat_routes.router,
            details_routes.router,
            profile_image_routes.router,
            contact_routes.router,
        ):
            app.include_router(router)

        for error_type in self._exception_handler.handled_types:
            app.add_exception_handler(error_type, self._exception_handler)

        server = self._config.app
        app.add_middleware(UnhandledErrorMiddleware, exception_handler=self._exception_handler)
        app.add_middleware(
            BodySizeLimitMiddleware,
            max_body_bytes=server.max_body_bytes,
            exception_handler=self._exception_handler,
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(server.cors.allow_origins),
            allow_methods=["*"],
            allow_headers=["*", SESSION_HEADER, FORWARDED_FOR_HEADER],
            expose_headers=list(EXPOSED_HEADERS),
            max_age=int(server.cors.max_age.total_seconds()),
        )
        return app

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        anyio.to_thread.current_default_thread_limiter().total_tokens = self._config.app.thread_pool_size
        container = await anyio.to_thread.run_sync(self._container_factory, self._config)
        app.state.handler = HandlerState(
            container=container,
            responder=self._responder,
            exception_handler=self._exception_handler,
            client_ip_resolver=self._client_ip_resolver,
        )
        try:
            yield
        finally:
            await anyio.to_thread.run_sync(container.close)
