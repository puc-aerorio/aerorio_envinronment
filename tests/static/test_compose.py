"""`docker compose config` accepts the base file with every combination of overrides."""

import itertools
import os
import shutil
import subprocess

import pytest

from tests.repo import REPO_ROOT

pytestmark = pytest.mark.static

COMPOSE_DIR = REPO_ROOT / "compose"
BASE = "compose/base.yaml"
OVERRIDES = sorted(
    str(p.relative_to(REPO_ROOT)) for p in COMPOSE_DIR.glob("*.yaml") if p.name != "base.yaml"
)
COMBINATIONS = [
    combo for n in range(len(OVERRIDES) + 1) for combo in itertools.combinations(OVERRIDES, n)
]


def test_overrides_are_found() -> None:
    # Guards the parametrisation below against an empty glob.
    assert "compose/linux-x11.yaml" in OVERRIDES


@pytest.mark.parametrize("overrides", COMBINATIONS, ids=lambda c: "+".join(c) or "base-only")
def test_compose_config_validates(overrides: tuple[str, ...]) -> None:
    docker = shutil.which("docker")
    assert docker, "docker (with the compose plugin) is needed for this check"
    files = [arg for f in (BASE, *overrides) for arg in ("-f", f)]
    result = subprocess.run(
        [docker, "compose", "--project-directory", ".", *files, "config", "--quiet"],
        cwd=REPO_ROOT,
        env={**os.environ, "RENDER_GID": "109"},  # run.sh always sets it with linux-dri.yaml
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
