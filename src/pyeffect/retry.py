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

import time
from collections.abc import Callable
from dataclasses import dataclass

from pyeffect.result import Ok, Result

__all__ = ["Policy", "retry"]


@dataclass(frozen=True, slots=True)
class Policy:
    """How many attempts, and how long to wait between them.

    A broken policy is a bug, so it panics at construction (fail fast)
    instead of looping forever or never running.

    Attributes:
        max_attempts: Total attempts, including the first (>= 1).
        delay: Seconds to sleep between attempts (>= 0).
    """

    max_attempts: int
    delay: float = 0.0

    def __post_init__(self) -> None:
        # Explicit raises, not assert: `python -O` strips asserts, which would
        # let a broken policy through to a misleading "unreachable" error in
        # `retry`. A broken policy is a defect and must panic unconditionally.
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.delay < 0.0:
            raise ValueError(f"delay must be >= 0, got {self.delay}")


def retry[T, E](
    operation: Callable[[int], Result[T, E]],
    policy: Policy,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> Result[T, E]:
    """Run ``operation`` up to ``policy.max_attempts`` times.

    ``operation`` receives the 1-based attempt number and must return a
    :data:`Result`. On ``Ok`` it stops immediately; after the final attempt
    it returns the last ``Err`` — a value the caller decides how to handle.
    Failure is expected, so it is returned, never raised.
    """
    for attempt in range(1, policy.max_attempts + 1):
        result = operation(attempt)
        if isinstance(result, Ok):
            return result
        if attempt == policy.max_attempts:
            return result
        sleep(policy.delay)
    raise AssertionError("unreachable: Policy.max_attempts >= 1 guarantees a return")
