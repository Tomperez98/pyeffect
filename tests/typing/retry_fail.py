"""Typing fixture: retry given a non-Result operation. Must fail `ty`.

The intentional errors are suppressed for repo-wide checks; ty flags an
ignore as unused if the diagnostic ever changes or disappears.
"""

from __future__ import annotations

from pyeffect.result import Err, Ok, Result
from pyeffect.retry import Policy, retry


def op(n: int) -> Result[int, str]:
    return Err("x") if n < 0 else Ok(n)


def main() -> None:
    # The operation must return a Result; 42 is a plain int.
    retry(lambda _: 42, Policy(max_attempts=3))  # ty: ignore[invalid-argument-type]

    # The delay callback's error parameter is the operation's error type;
    # comparing it to an int is invalid (the error is str).
    retry(
        op,
        Policy(max_attempts=3),
        delay=lambda error, _: error + 1,  # ty: ignore[unsupported-operator]
    )
