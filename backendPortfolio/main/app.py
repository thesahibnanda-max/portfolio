from fastapi import FastAPI

from main.config import AppConfig, load_local_env
from main.package.handler import ApplicationFactory, ServiceContainer


def create_app() -> FastAPI:
    load_local_env()
    return ApplicationFactory(config=AppConfig.load(), container_factory=ServiceContainer.from_config).create()
