"""A faked Host for `run.sh --dry-run`: a detection root plus `docker`/`nvidia-smi` stubs on PATH."""

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.repo import REPO_ROOT


@dataclass
class DryRun:
    returncode: int
    stdout: str
    stderr: str
    env: dict[str, str] = field(default_factory=dict)
    compose_files: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)

    def container_config(self) -> dict:
        """The Container's resolved service config: the printed compose command, resolved by
        the real `docker compose config` instead of being run."""
        docker = shutil.which("docker")
        assert docker, "docker (with compose) is needed to resolve the compose files"
        subcommand = self.command.index("run")
        argv = [docker, *self.command[1:subcommand], "config", "--format", "json"]
        result = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            env={**os.environ, **self.env},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)["services"]["sim"]

    def container_environment(self) -> dict[str, str]:
        """The environment the Container would get."""
        return self.container_config().get("environment", {})


def _parse(stdout: str) -> tuple[dict[str, str], list[str], list[str]]:
    """Split the printed command (last line) into VAR=value prefixes, -f files and the argv."""
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {}, [], []
    words = shlex.split(lines[-1])
    env: dict[str, str] = {}
    while words and "=" in words[0] and not words[0].startswith("-"):
        key, _, value = words.pop(0).partition("=")
        env[key] = value
    files = [words[i + 1] for i, w in enumerate(words[:-1]) if w == "-f"]
    return env, files, words


@dataclass
class FakeHost:
    """What the launcher can observe about a Host. Tests set the fields, then call dry_run()."""

    root: Path
    bin: Path
    dri: bool = False
    nvidia_smi_works: bool = False
    docker_nvidia_runtime: bool = False
    image_present: bool = True
    container_running: bool = False

    @property
    def render_device(self) -> Path:
        return self.root / "dev/dri/renderD128"

    def _stub(self, name: str, body: str) -> None:
        stub = self.bin / name
        stub.write_text("#!/usr/bin/env bash\n" + body)
        stub.chmod(0o755)

    def _materialize(self) -> None:
        if self.dri:
            self.render_device.parent.mkdir(parents=True, exist_ok=True)
            self.render_device.touch()
        self._stub("nvidia-smi", "exit 0\n" if self.nvidia_smi_works else "exit 9\n")
        runtimes = "io.containerd.runc.v2 nvidia runc" if self.docker_nvidia_runtime else "runc"
        running = "true" if self.container_running else "false"
        self._stub(
            "docker",
            f"""case "$1 ${{2:-}}" in
  "info "*) echo " Runtimes: {runtimes}" ;;
  "image inspect") exit {0 if self.image_present else 1} ;;
  "container inspect") echo {running} ;;
  *) echo "stub docker: unexpected call: $*" >&2; exit 99 ;;
esac
""",
        )

    def dry_run(self, *args: str) -> DryRun:
        self._materialize()
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root / "home"),
            "AERORIO_HOST_ROOT": str(self.root),
            "DISPLAY": ":1",
        }
        result = subprocess.run(
            [str(REPO_ROOT / "run.sh"), "--dry-run", *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        parsed_env, files, command = _parse(result.stdout)
        return DryRun(result.returncode, result.stdout, result.stderr, parsed_env, files, command)


@pytest.fixture
def host(tmp_path: Path) -> FakeHost:
    root, stub_bin = tmp_path / "root", tmp_path / "bin"
    root.mkdir()
    stub_bin.mkdir()
    return FakeHost(root=root, bin=stub_bin)
