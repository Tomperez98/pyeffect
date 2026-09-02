"""Compile-time tests: pin pipe's typing contract with ``ty`` (TEST.md §8).

The pass fixture must check clean. Each fail fixture carries an intentional
type error suppressed by a code-specific ``# ty: ignore[<code>]`` comment;
ty enforces that the code matches the real diagnostic and that the
suppression is still needed. If a fixture stops erroring — or its error
code changes — ty reports ``unused-ignore-comment``, exits non-zero, and
these tests fail. That is the staleness guard: a fixture cannot silently
stop testing what it claims to test.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TYPING_DIR = PROJECT_ROOT / "tests" / "typing"

# (filename, expected error code suppressed by its inline ty-ignore comment)
FIXTURES = [
    ("pipe_pass.py", None),
    ("pipe_fail_mismatch.py", "invalid-argument-type"),
    ("pipe_fail_noncallable.py", "invalid-argument-type"),
    ("pipe_fail_arity.py", "no-matching-overload"),
]


def run_ty(path: Path) -> subprocess.CompletedProcess[str]:
    """Run ty over one fixture; crash the test on any infra failure."""
    return subprocess.run(
        [sys.executable, "-m", "ty", "check", str(path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize(("filename", "expected_code"), FIXTURES)
def test_fixture_checks_clean(filename: str, expected_code: str | None) -> None:
    path = TYPING_DIR / filename
    result = run_ty(path)
    assert result.returncode == 0, (
        f"ty rejected {filename}; expected a clean check:\n{result.stdout}{result.stderr}"
    )
    if expected_code is not None:
        source = path.read_text()
        assert f"ty: ignore[{expected_code}]" in source, (
            f"{filename} must suppress its intentional error with a code-specific "
            f"`# ty: ignore[{expected_code}]` comment"
        )
