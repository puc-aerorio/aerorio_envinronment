"""Where the repo is and which of its files each static check covers."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SHELLS = {"sh", "bash", "dash"}


def repo_files() -> list[Path]:
    """Files git tracks, plus new ones not yet added (but not ignored ones)."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths = (REPO_ROOT / p for p in out.split("\0") if p)
    return [p for p in paths if p.is_file()]  # skips deleted-but-still-indexed files


def _interpreter(path: Path) -> str | None:
    """The program named on the file's shebang line (`env` resolved), or None."""
    try:
        with path.open("rb") as f:
            first = f.readline(256).decode(errors="replace")
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    words = first[2:].split()
    if not words:
        return None
    program = Path(words[0]).name
    if program == "env" and len(words) > 1:
        program = words[1]
    return program


def shell_scripts() -> list[Path]:
    """Every shell script in the repo, found by `.sh` extension or by shebang."""
    return [p for p in repo_files() if p.suffix == ".sh" or _interpreter(p) in SHELLS]


def relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def run_in_repo(*cmd: str) -> subprocess.CompletedProcess[str]:
    """Run a command from the repo root, capturing output; the caller checks the exit code."""
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
