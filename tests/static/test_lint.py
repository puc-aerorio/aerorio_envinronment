"""Static checks: shellcheck on every shell script, hadolint on the Dockerfile, ruff on Python.

Findings are fixed in the code, or suppressed at the line with a `# shellcheck disable=` /
`# hadolint ignore=` / `# noqa:` comment that says why.
"""

import sys
from pathlib import Path

import pytest

from tests.repo import relative, run_in_repo, shell_scripts

pytestmark = pytest.mark.static

VENV_BIN = Path(sys.executable).parent  # shellcheck, hadolint and ruff from the uv venv


def test_shell_scripts_are_found() -> None:
    # Guards the discovery below: an empty list would make shellcheck pass vacuously.
    assert {"run.sh", "tools/start_simulation.sh"} <= {relative(p) for p in shell_scripts()}


@pytest.mark.parametrize("script", shell_scripts(), ids=relative)
def test_shellcheck(script: Path) -> None:
    result = run_in_repo(str(VENV_BIN / "shellcheck"), "--external-sources", relative(script))
    assert result.returncode == 0, result.stdout + result.stderr


def test_hadolint() -> None:
    result = run_in_repo(str(VENV_BIN / "hadolint"), "Dockerfile")
    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff() -> None:
    result = run_in_repo(str(VENV_BIN / "ruff"), "check", "tools", "tests")
    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff_format() -> None:
    # Only tests/: the team's Tools keep their own formatting.
    result = run_in_repo(str(VENV_BIN / "ruff"), "format", "--check", "tests")
    assert result.returncode == 0, result.stdout + result.stderr
