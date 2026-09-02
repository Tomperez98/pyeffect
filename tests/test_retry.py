"""Runtime behavior tests for retry: deterministic, injectable, no sleeping."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result, attempt
from pyeffect.retry import Policy, retry


def failing_until(
    attempts_list: list[int], succeed_at: int
) -> Callable[[int], Result[int, str]]:
    """An operation that fails until the ``succeed_at``-th attempt."""

    def operation(attempt: int) -> Result[int, str]:
        attempts_list.append(attempt)
        if attempt < succeed_at:
            return Err("not yet")
        return Ok(attempt)

    return operation


def test_succeeds_on_first_attempt() -> None:
    attempts: list[int] = []
    result = retry(failing_until(attempts, 1), Policy(max_attempts=3))
    assert result == Ok(1)
    assert attempts == [1]


def test_retries_until_success() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    result = retry(
        failing_until(attempts, 3),
        Policy(max_attempts=5, delay=0.0),
        sleep=sleeps.append,
    )

    assert result == Ok(3)
    assert attempts == [1, 2, 3]
    # One sleep between each failed attempt, none after success.
    assert sleeps == [0.0, 0.0]


def test_exhausts_and_returns_last_err_as_a_value() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    result = retry(
        failing_until(attempts, 99),
        Policy(max_attempts=3, delay=0.5),
        sleep=sleeps.append,
    )

    assert result == Err("not yet")
    assert attempts == [1, 2, 3]
    # No sleep after the final attempt.
    assert sleeps == [0.5, 0.5]


def test_no_sleep_after_success() -> None:
    sleeps: list[float] = []
    retry(failing_until([], 1), Policy(max_attempts=3), sleep=sleeps.append)
    assert sleeps == []


def test_operation_receives_1_based_attempt_numbers() -> None:
    attempts: list[int] = []
    retry(failing_until(attempts, 1), Policy(max_attempts=3))
    assert attempts == [1]


def test_composes_with_attempt() -> None:
    # A raising operation wrapped at the boundary, retried as a Result.
    attempts: list[int] = []

    def flaky() -> int:
        attempts.append(1)
        if len(attempts) < 2:
            raise ValueError("not yet")
        return 42

    result = retry(lambda n: attempt(flaky), Policy(max_attempts=3))
    assert result == Ok(42)
    assert attempts == [1, 1]


def test_policy_rejects_zero_attempts() -> None:
    with pytest.raises(Panic):
        Policy(max_attempts=0)


def test_policy_rejects_negative_delay() -> None:
    with pytest.raises(Panic):
        Policy(max_attempts=2, delay=-1.0)


def test_policy_accepts_valid_values() -> None:
    assert Policy(max_attempts=1).max_attempts == 1
    assert Policy(max_attempts=3, delay=0.5).delay == 0.5


def test_dynamic_delay_uses_the_error() -> None:
    sleeps: list[float] = []

    def op(attempt: int) -> Result[int, str]:
        return Err("rate-limited") if attempt < 3 else Ok(attempt)

    result = retry(
        op,
        Policy(max_attempts=3),
        sleep=sleeps.append,
        delay=lambda error, attempt: 1.5 if error == "rate-limited" else 0.0,
    )
    assert result == Ok(3)
    assert sleeps == [1.5, 1.5]


def test_dynamic_delay_rejects_backoff_combination() -> None:
    with pytest.raises(Panic):
        retry(
            lambda n: Err("x"),
            Policy(max_attempts=2, backoff="exponential"),
            delay=lambda error, attempt: 1.0,
        )


def test_throwing_should_retry_is_a_panic() -> None:
    def op(attempt: int) -> Result[int, str]:
        return Err("boom")

    with pytest.raises(Panic) as excinfo:
        retry(
            op,
            Policy(max_attempts=3, delay=0.0),
            should_retry=lambda error, attempt: (_ for _ in ()).throw(
                ValueError("nope")
            ),
        )
    assert isinstance(excinfo.value.cause, ValueError)
