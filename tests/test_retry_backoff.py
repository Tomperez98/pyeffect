"""Runtime behavior tests for retry backoff, jitter, and should_retry."""

from __future__ import annotations

import pytest

from pyeffect.panic import PanicError
from pyeffect.result import Err, Ok, Result
from pyeffect.retry import Backoff, Policy, _base_delay, retry


def test_policy_defaults_are_backward_compatible() -> None:
    policy = Policy(max_attempts=3, delay=0.1)
    assert policy.backoff == "constant"
    assert policy.jitter == 0.0


def test_policy_rejects_out_of_range_jitter() -> None:
    with pytest.raises(PanicError):
        Policy(max_attempts=3, jitter=1.5)
    with pytest.raises(PanicError):
        Policy(max_attempts=3, jitter=-0.1)


def test_constant_backoff() -> None:
    assert _base_delay(1, Policy(3, delay=2.0)) == 2.0
    assert _base_delay(4, Policy(3, delay=2.0)) == 2.0


def test_linear_backoff() -> None:
    policy = Policy(3, delay=2.0, backoff="linear")
    assert _base_delay(1, policy) == 2.0
    assert _base_delay(2, policy) == 4.0
    assert _base_delay(3, policy) == 6.0


def test_exponential_backoff() -> None:
    policy = Policy(3, delay=2.0, backoff="exponential")
    assert _base_delay(1, policy) == 2.0
    assert _base_delay(2, policy) == 4.0
    assert _base_delay(3, policy) == 8.0


def test_retry_exponential_backoff_delays() -> None:
    sleeps: list[float] = []

    def op(attempt: int) -> Result[int, str]:
        return Ok(attempt) if attempt >= 3 else Err("flaky")

    result = retry(
        op,
        Policy(max_attempts=3, delay=0.5, backoff="exponential"),
        sleep=sleeps.append,
        random_float=lambda: 0.0,
    )
    assert result == Ok(3)
    assert sleeps == [0.5, 1.0]


def test_should_retry_false_stops_immediately() -> None:
    sleeps: list[float] = []

    def op(attempt: int) -> Result[int, str]:
        return Err("boom")

    result = retry(
        op,
        Policy(max_attempts=5, delay=0.1),
        sleep=sleeps.append,
        should_retry=lambda _error, _attempt: False,
    )
    assert result == Err("boom")
    assert sleeps == []


def test_should_retry_selective() -> None:
    attempts: list[int] = []

    def op(attempt: int) -> Result[int, str]:
        attempts.append(attempt)
        if attempt == 1:
            return Err("transient")
        return Ok(attempt)

    result = retry(
        op,
        Policy(max_attempts=3, delay=0.0),
        should_retry=lambda error, _: error == "transient",
    )
    assert result == Ok(2)
    assert attempts == [1, 2]


def test_jitter_shortens_delay() -> None:
    sleeps: list[float] = []

    def op(attempt: int) -> Result[int, str]:
        return Ok(attempt) if attempt >= 2 else Err("flaky")

    retry(
        op,
        Policy(max_attempts=2, delay=1.0, jitter=0.5),
        sleep=sleeps.append,
        random_float=lambda: 1.0,  # maximal jitter: halve the delay
    )
    assert sleeps == [0.5]


def test_public_export() -> None:
    from pyeffect import Backoff as PublicBackoff, Policy as PublicPolicy

    assert PublicBackoff is Backoff
    assert PublicPolicy is Policy
