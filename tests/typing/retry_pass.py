"""Typing fixture: valid retry calls pinned with assert_type."""

from __future__ import annotations

from typing import assert_type

from pyeffect.result import Err, Ok, Result
from pyeffect.retry import Policy, retry


def operation(n: int) -> Result[int, str]:
    return Ok(n) if n >= 2 else Err("not yet")


def main() -> None:
    policy = Policy(max_attempts=3, delay=0.0)
    assert_type(retry(operation, policy), Result[int, str])

    # sleep is injectable and typed as Callable[[float], None].
    assert_type(retry(operation, policy, sleep=print), Result[int, str])

    dynamic = retry(
        operation,
        Policy(max_attempts=3),
        delay=lambda error, _: 1.0 if error == "not yet" else 0.0,
    )
    assert_type(dynamic, Result[int, str])
