import os
from pathlib import Path

import pytest
from fastapi import FastAPI

import main
import main.app
from main.config import LOCAL_ENV_FILE, AppConfig, load_local_env
from tests.conftest import FAKE_GROQ_API_KEYS

VARIABLE = "PORTFOLIO_TEST_DOTENV_VALUE"


@pytest.fixture
def clean_variable(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv(VARIABLE, "placeholder")
    monkeypatch.delenv(VARIABLE)
    return VARIABLE


def _env_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_local_env_file_is_next_to_the_main_package() -> None:
    assert LOCAL_ENV_FILE == Path(main.__file__).resolve().parent.parent / ".env"


def test_loads_variables_that_are_not_set(tmp_path: Path, clean_variable: str) -> None:
    loaded = load_local_env(_env_file(tmp_path, f"{clean_variable}=from-file\n"))

    assert loaded is True
    assert os.environ[clean_variable] == "from-file"


def test_never_overrides_a_variable_that_is_already_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VARIABLE, "from-environment")

    load_local_env(_env_file(tmp_path, f"{VARIABLE}=from-file\n"))

    assert os.environ[VARIABLE] == "from-environment"


def test_missing_file_is_a_no_op(tmp_path: Path, clean_variable: str) -> None:
    assert load_local_env(tmp_path / "absent.env") is False
    assert clean_variable not in os.environ


def test_config_load_ignores_a_dotenv_in_the_working_directory(
    config_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env_file(tmp_path, "GROQ_API_KEYS=key-from-dotenv\nRECIPIENT_MAIL=\n")
    monkeypatch.chdir(tmp_path)

    config = AppConfig.load()

    assert [key.get_secret_value() for key in config.groq.api_keys] == FAKE_GROQ_API_KEYS.split(",")
    assert config.mail.recipient_mail == "owner@example.com"


class LoadRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> bool:
        self.calls += 1
        return False


def test_create_app_loads_the_local_env_first(config_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = LoadRecorder()
    monkeypatch.setattr(main.app, "load_local_env", recorder)

    app = main.app.create_app()

    assert isinstance(app, FastAPI)
    assert recorder.calls == 1
