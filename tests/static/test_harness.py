"""The test harness itself: layers are selected with -m, and a misspelled layer is an error."""

import subprocess
import sys

import pytest

from tests.repo import run_in_repo

pytestmark = pytest.mark.static


def run_pytest(*args: str) -> subprocess.CompletedProcess[str]:
    return run_in_repo(sys.executable, "-m", "pytest", "--collect-only", "-q", *args)


@pytest.mark.parametrize("expr", ["statc", "not statc", "static or smok"])
def test_misspelled_layer_fails_the_run(expr: str) -> None:
    result = run_pytest("-m", expr)
    assert result.returncode != 0, result.stdout
    assert "unknown marker" in (result.stdout + result.stderr).lower()


@pytest.mark.parametrize("expr", ["static", "not simulation", "static or launcher"])
def test_known_layers_select_without_error(expr: str) -> None:
    result = run_pytest("-m", expr)
    assert result.returncode == 0, result.stdout + result.stderr
