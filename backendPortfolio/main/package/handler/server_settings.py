from dataclasses import dataclass
from typing import Self

from main.config import AppConfig

WORKER_CLASS = "main.package.handler.worker.FastUvicornWorker"
APP_FACTORY = "main.app:create_app()"


@dataclass(frozen=True)
class GunicornSettings:
    wsgi_app: str
    bind: str
    workers: int
    worker_class: str
    timeout: int
    graceful_timeout: int
    keepalive: int

    @classmethod
    def from_config(cls, config: AppConfig) -> Self:
        server = config.app
        return cls(
            wsgi_app=APP_FACTORY,
            bind=f"{server.host}:{server.port}",
            workers=server.workers,
            worker_class=WORKER_CLASS,
            timeout=int(server.timeout.total_seconds()),
            graceful_timeout=int(server.graceful_timeout.total_seconds()),
            keepalive=int(server.keepalive.total_seconds()),
        )
