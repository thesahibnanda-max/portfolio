from typing import Any

from uvicorn_worker import UvicornWorker


class FastUvicornWorker(UvicornWorker):
    CONFIG_KWARGS: dict[str, Any] = {
        "loop": "uvloop",
        "http": "httptools",
        "lifespan": "on",
        "proxy_headers": False,
        "server_header": False,
    }
