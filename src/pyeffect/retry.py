"""Deterministic, injectable retry for Result-returning operations.

The operation receives its 1-based attempt number, so a test can script
exactly when it fails; ``sleep`` is injected, so tests run with zero delay
and no real sleeping::

    >>> from pyeffect.retry import Policy, retry
    >>> from pyeffect.result import Ok, Err
    >>> retry(lambda n: Ok(n), Policy(max_attempts=3))
    Ok(value=1)
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, assert_never

from pyeffect.panic import Panic
from pyeffect.result import Ok, Result

__all__ = ["Backoff", "Policy", "retry"]


type Backoff = Literal["constant", "linear", "exponential"]


@dataclass(frozen=True, slots=True)
class Policy:
    """How many attempts, how long to wait, and how that wait grows.

    A broken policy is a bug, so it panics at construction (fail fast)
    instead of looping forever or never running.

    Attributes:
        max_attempts: Total attempts, including the first (>= 1).
        delay: Base seconds to sleep between attempts (>= 0).
        backoff: How ``delay`` grows across attempts.
        jitter: Fraction in ``[0, 1]`` by which a delay may be randomly
            shortened (0 = none, 1 = fully randomized).
    """

    max_attempts: int
    delay: float = 0.0
    backoff: Backoff = "constant"
    jitter: float = 0.0

    def __post_init__(self) -> None:
        # A broken policy is a defect and must panic unconditionally.
        if self.max_attempts < 1:
            raise Panic(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.delay < 0.0:
            raise Panic(f"delay must be >= 0, got {self.delay}")
        if not 0.0 <= self.jitter <= 1.0:
            raise Panic(f"jitter must be in [0, 1], got {self.jitter}")


def _base_delay(retry_number: int, policy: Policy) -> float:
    """The delay before retry number ``retry_number`` (1-based), before jitter."""
    match policy.backoff:
        case "constant":
            return policy.delay
        case "linear":
            return policy.delay * retry_number
        case "exponential":
            return policy.delay * (2 ** (retry_number - 1))
        case _:
            assert_never(policy.backoff)


def retry[T, E](
    operation: Callable[[int], Result[T, E]],
    policy: Policy,
    *,
    sleep: Callable[[float], None] = time.sleep,
    should_retry: Callable[[E, int], bool] = lambda error, attempt: True,
    delay: Callable[[E, int], float] | None = None,
    random_float: Callable[[], float] = random.random,
) -> Result[T, E]:
    """Run ``operation`` up to ``policy.max_attempts`` times.

    ``operation`` receives the 1-based attempt number and must return a
    :data:`Result`. On ``Ok`` it stops immediately; after the final attempt
    it returns the last ``Err`` — a value the caller decides how to handle.

    ``delay(error, attempt)`` supplies an error-dependent final delay. When
    provided it overrides the policy's static ``delay``/``backoff``/``jitter``
    (combining it with ``backoff`` or ``jitter`` is a defect and panics).
    A throwing ``should_retry`` or ``delay`` callback is a defect and becomes
    a :class:`Panic`, never a returned ``Err``.
    """
    if delay is not None and (policy.backoff != "constant" or policy.jitter != 0.0):
        raise Panic("a dynamic delay cannot be combined with backoff or jitter")

    for attempt in range(1, policy.max_attempts + 1):
        result = operation(attempt)
        if isinstance(result, Ok):
            return result
        if attempt == policy.max_attempts:
            return result
        try:
            if not should_retry(result.error, attempt):
                return result
        except Exception as exc:
            raise Panic("should_retry callback raised", cause=exc) from exc
        try:
            wait = (
                delay(result.error, attempt)
                if delay is not None
                else _base_delay(attempt, policy) * _jitter(policy, random_float)
            )
        except Exception as exc:
            raise Panic("delay callback raised", cause=exc) from exc
        sleep(wait)
    raise Panic("unreachable: Policy.max_attempts >= 1 guarantees a return")


def _jitter(policy: Policy, random_float: Callable[[], float]) -> float:
    """The multiplier ``(1 - jitter * r)`` applied to a static delay."""

    if policy.jitter:
        return 1.0 - policy.jitter * random_float()
    return 1.0
