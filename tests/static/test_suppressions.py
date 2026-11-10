"""Every linter suppression says why, so the next reader can tell a decision from a shortcut.

A reason is either a `# ...` comment after the directive on the same line, or a comment line
directly above it (the Dockerfile style, since `# hadolint ignore=` must sit right above its
instruction).
"""

import re
from pathlib import Path

import pytest

from tests.repo import REPO_ROOT, relative, repo_files, shell_scripts

pytestmark = pytest.mark.static

# A directive, and whatever follows it on the line.
SHELL_DIRECTIVE = re.compile(r"^\s*#\s*(?:shellcheck|hadolint)\s+\S+(?P<rest>.*)$")
# Anchored: only a real noqa directive (bare, or with codes; then nothing or a comment), not prose
# that mentions one.
NOQA = re.compile(r"#\s*noqa(?::\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*)?(?P<rest>\s*(?:#.*)?)$")
HADOLINT_CONFIG_RULE = re.compile(r"^\s*-\s*(?:DL|SC)\d+\s*$")


def _is_reason(text: str) -> bool:
    return bool(re.match(r"\s*#\s*\S", text))


def _is_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("#") and not SHELL_DIRECTIVE.match(line)


def unexplained(path: Path, directive: re.Pattern[str]) -> list[str]:
    lines = path.read_text(errors="replace").splitlines()
    found = []
    for i, line in enumerate(lines):
        match = directive.search(line)
        if not match:
            continue
        rest = match.groupdict().get("rest", "")
        if rest and _is_reason(rest):
            continue
        if i > 0 and _is_comment(lines[i - 1]):
            continue
        found.append(f"{path}:{i + 1}: {line.strip()}")
    return found


def python_files() -> list[Path]:
    return [
        p
        for p in repo_files()
        if p.suffix == ".py" and relative(p).startswith(("tools/", "tests/"))
    ]


def test_every_suppression_has_a_reason() -> None:
    found = []
    for path in [*shell_scripts(), REPO_ROOT / "Dockerfile"]:
        found += unexplained(path, SHELL_DIRECTIVE)
    for path in python_files():
        found += unexplained(path, NOQA)
    found += unexplained(REPO_ROOT / ".hadolint.yaml", HADOLINT_CONFIG_RULE)
    assert not found, "suppressions without a reason:\n" + "\n".join(found)


def test_a_bare_suppression_is_caught(tmp_path: Path) -> None:
    # Guards the check above against matching nothing.
    script = tmp_path / "bare.sh"
    script.write_text("#!/bin/bash\necho ok\n# shellcheck disable=SC2086\necho $1\n")
    assert len(unexplained(script, SHELL_DIRECTIVE)) == 1


def test_a_bare_noqa_is_caught_but_prose_about_noqa_is_not(tmp_path: Path) -> None:
    module = tmp_path / "m.py"
    module.write_text('import os  # noqa: F401\n"""mentions `# noqa:` in prose"""\n')
    assert len(unexplained(module, NOQA)) == 1
