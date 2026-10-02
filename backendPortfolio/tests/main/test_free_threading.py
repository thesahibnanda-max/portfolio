import importlib
import sys
import sysconfig
from pathlib import Path

import pytest

import main

MAIN_ROOT = Path(main.__file__).parent
MODULES = sorted(
    ".".join(("main", *path.relative_to(MAIN_ROOT).with_suffix("").parts)).removesuffix(".__init__")
    for path in MAIN_ROOT.rglob("*.py")
)


def test_interpreter_is_a_free_threaded_build() -> None:
    assert sysconfig.get_config_var("Py_GIL_DISABLED") == 1


@pytest.mark.parametrize("module_name", MODULES)
def test_importing_module_keeps_gil_disabled(module_name: str) -> None:
    importlib.import_module(module_name)

    assert sys._is_gil_enabled() is False


def test_every_source_module_is_checked() -> None:
    assert len(MODULES) >= 30
    assert "main.app" in MODULES
    assert "main.package.clients.github.github_client" in MODULES
