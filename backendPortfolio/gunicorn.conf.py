from main.config import AppConfig, load_local_env
from main.package.handler import GunicornSettings

load_local_env()
_settings = GunicornSettings.from_config(AppConfig.load())

wsgi_app = _settings.wsgi_app
bind = _settings.bind
workers = _settings.workers
worker_class = _settings.worker_class
timeout = _settings.timeout
graceful_timeout = _settings.graceful_timeout
keepalive = _settings.keepalive
