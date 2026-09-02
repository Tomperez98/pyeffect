"""Typing fixture: retry preserves Result[T, E] through backoff options."""

from __future__ import annotations

from typing import assert_type

from pyeffect.result import Err, Ok, Result
from pyeffect.retry import Policy, retry


def op(attempt: int) -> Result[int, str]:
    return Ok(attempt) if attempt >= 2 else Err("flaky")


def main() -> None:
    result = retry(
        op,
        Policy(max_attempts=3, delay=0.1, backoff="exponential", jitter=0.2),
    )
    assert_type(result, Result[int, str])

    selective = retry(
        op,
        Policy(max_attempts=3),
        should_retry=lambda error, _: error == "flaky",
    )
    assert_type(selective, Result[int, str])
