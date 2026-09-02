# Retry Backoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `retry` with backoff strategies (constant/linear/exponential), jitter, and a `should_retry` predicate, while keeping it deterministic and injectable.

**Architecture:** `Policy` gains two fields — `backoff: Backoff` (an enum) and `jitter: float` (a fraction in `[0, 1]`). A private `_base_delay(retry_number, policy)` computes the raw delay before retry *n* (1-based); `retry` applies jitter and sleeps via the existing injected `sleep`. Two new keyword-only `retry` parameters keep it deterministic: `should_retry(error, attempt)` stops early on a non-retryable error, and `random_float` (defaulting to `random.random`) supplies the jitter multiplier so tests inject a fixed value. Existing `Policy(max_attempts, delay)` calls are unchanged.

**Out of scope (deliberate):** error-dependent delays (`delay(error, attempt)` — an either/or with static `delay` that complicates the `Policy` shape), and cancellation (no Python `AbortSignal` analog). Both are noted as follow-ups.

**Tech Stack:** Python 3.12+, PEP 695 generics, `ty` 0.0.77, pytest 9, ruff.

---

## File Structure

- **Modify `src/pyeffect/retry.py`** — add `Backoff`, extend `Policy`, add `_base_delay`, extend `retry`.
- **Modify `src/pyeffect/__init__.py`** — export `Backoff`.
- **Create `tests/test_retry_backoff.py`** — runtime tests.
- **Create `tests/typing/retry_backoff_pass.py`** — type contract.
- **Modify `README.md`** — mention backoff in the retry note.

---

### Task 1: `Backoff` enum + extended `Policy`

**Files:**
- Modify: `src/pyeffect/retry.py`
- Test: `tests/test_retry_backoff.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_retry_backoff.py`:

```python
"""Runtime behavior tests for retry backoff, jitter, and should_retry."""

from __future__ import annotations

import pytest

from pyeffect.retry import Backoff, Policy, _base_delay


def test_policy_defaults_are_backward_compatible() -> None:
    policy = Policy(max_attempts=3, delay=0.1)
    assert policy.backoff is Backoff.CONSTANT
    assert policy.jitter == 0.0


def test_policy_rejects_out_of_range_jitter() -> None:
    with pytest.raises(ValueError):
        Policy(max_attempts=3, jitter=1.5)
    with pytest.raises(ValueError):
        Policy(max_attempts=3, jitter=-0.1)


def test_constant_backoff() -> None:
    assert _base_delay(1, Policy(3, delay=2.0)) == 2.0
    assert _base_delay(4, Policy(3, delay=2.0)) == 2.0


def test_linear_backoff() -> None:
    policy = Policy(3, delay=2.0, backoff=Backoff.LINEAR)
    assert _base_delay(1, policy) == 2.0
    assert _base_delay(2, policy) == 4.0
    assert _base_delay(3, policy) == 6.0


def test_exponential_backoff() -> None:
    policy = Policy(3, delay=2.0, backoff=Backoff.EXPONENTIAL)
    assert _base_delay(1, policy) == 2.0
    assert _base_delay(2, policy) == 4.0
    assert _base_delay(3, policy) == 8.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retry_backoff.py -v`
Expected: FAIL with `ImportError: cannot import name 'Backoff'`

- [ ] **Step 3: Add `Backoff` and extend `Policy` in `src/pyeffect/retry.py`**

Change the imports (top of file):

```python
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from pyeffect.result import Ok, Result

__all__ = ["Backoff", "Policy", "retry"]
```

Add `Backoff` before `Policy`:

```python
class Backoff(Enum):
    """How the delay grows between attempts.

    The delay before retry number ``n`` (1-based) is:

    - ``CONSTANT`` — ``delay`` every time.
    - ``LINEAR`` — ``delay * n``.
    - ``EXPONENTIAL`` — ``delay * 2 ** (n - 1)``.
    """

    CONSTANT = "constant"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
```

Extend `Policy` (replace its fields and `__post_init__`):

```python
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
    backoff: Backoff = Backoff.CONSTANT
    jitter: float = 0.0

    def __post_init__(self) -> None:
        # Explicit raises, not assert: `python -O` strips asserts, which would
        # let a broken policy through to a misleading "unreachable" error in
        # `retry`. A broken policy is a defect and must panic unconditionally.
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.delay < 0.0:
            raise ValueError(f"delay must be >= 0, got {self.delay}")
        if not 0.0 <= self.jitter <= 1.0:
            raise ValueError(f"jitter must be in [0, 1], got {self.jitter}")
```

Add `_base_delay` after `Policy`:

```python
def _base_delay(retry_number: int, policy: Policy) -> float:
    """The delay before retry number ``retry_number`` (1-based), before jitter."""

    if policy.backoff is Backoff.CONSTANT:
        return policy.delay
    if policy.backoff is Backoff.LINEAR:
        return policy.delay * retry_number
    return policy.delay * (2 ** (retry_number - 1))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_retry_backoff.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/retry.py tests/test_retry_backoff.py
git commit -m "feat: add Backoff enum and backoff/jitter to retry Policy"
```

---

### Task 2: `retry` uses backoff, jitter, and `should_retry`

**Files:**
- Modify: `src/pyeffect/retry.py`
- Test: `tests/test_retry_backoff.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_retry_backoff.py`:

```python
from pyeffect.result import Err, Ok
from pyeffect.retry import retry


def test_retry_exponential_backoff_delays() -> None:
    sleeps: list[float] = []

    def op(attempt: int) -> object:
        return Ok(attempt) if attempt >= 3 else Err("flaky")

    result = retry(
        op,
        Policy(max_attempts=3, delay=0.5, backoff=Backoff.EXPONENTIAL),
        sleep=sleeps.append,
        random_float=lambda: 0.0,
    )
    assert result == Ok(3)
    assert sleeps == [0.5, 1.0]  # 0.5 * 2^0, then 0.5 * 2^1


def test_should_retry_false_stops_immediately() -> None:
    sleeps: list[float] = []

    def op(attempt: int) -> object:
        return Err("boom")

    result = retry(
        op,
        Policy(max_attempts=5, delay=0.1),
        sleep=sleeps.append,
        should_retry=lambda error, attempt: False,
    )
    assert result == Err("boom")
    assert sleeps == []


def test_should_retry_selective() -> None:
    attempts: list[int] = []

    def op(attempt: int) -> object:
        attempts.append(attempt)
        if attempt == 1:
            return Err("transient")
        return Ok(attempt)

    result = retry(
        op,
        Policy(max_attempts=3, delay=0.0),
        should_retry=lambda error, attempt: error == "transient",
    )
    assert result == Ok(2)
    assert attempts == [1, 2]


def test_jitter_shortens_delay() -> None:
    sleeps: list[float] = []

    def op(attempt: int) -> object:
        return Ok(attempt) if attempt >= 2 else Err("flaky")

    retry(
        op,
        Policy(max_attempts=2, delay=1.0, jitter=0.5),
        sleep=sleeps.append,
        random_float=lambda: 1.0,  # maximal jitter: halve the delay
    )
    assert sleeps == [0.5]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_retry_backoff.py -v`
Expected: FAIL — `retry()` does not accept `should_retry`/`random_float` (TypeError)

- [ ] **Step 3: Rewrite `retry` in `src/pyeffect/retry.py`**

Replace the existing `retry` function with:

```python
def retry[T, E](
    operation: Callable[[int], Result[T, E]],
    policy: Policy,
    *,
    sleep: Callable[[float], None] = time.sleep,
    should_retry: Callable[[E, int], bool] = lambda error, attempt: True,
    random_float: Callable[[], float] = random.random,
) -> Result[T, E]:
    """Run ``operation`` up to ``policy.max_attempts`` times.

    ``operation`` receives the 1-based attempt number and must return a
    :data:`Result`. On ``Ok`` it stops immediately; after the final attempt
    it returns the last ``Err`` — a value the caller decides how to handle.

    Between attempts it sleeps the policy's delay (grown by ``backoff`` and
    shortened by ``jitter``). ``should_retry(error, attempt)`` can veto a
    retry: when it returns ``False``, the ``Err`` is returned immediately
    without sleeping or retrying. ``random_float`` supplies the jitter
    multiplier (default ``random.random``); inject a constant to make tests
    deterministic. Failure is expected, so it is returned, never raised.
    """
    for attempt in range(1, policy.max_attempts + 1):
        result = operation(attempt)
        if isinstance(result, Ok):
            return result
        if attempt == policy.max_attempts:
            return result
        if not should_retry(result.error, attempt):
            return result
        delay = _base_delay(attempt, policy)
        if policy.jitter:
            delay *= 1.0 - policy.jitter * random_float()
        sleep(delay)
    raise AssertionError("unreachable: Policy.max_attempts >= 1 guarantees a return")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_retry_backoff.py tests/test_retry.py -v`
Expected: PASS (all backoff tests + the existing retry tests, unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/retry.py tests/test_retry_backoff.py
git commit -m "feat: retry supports backoff, jitter, and should_retry"
```

---

### Task 3: Public export

**Files:**
- Modify: `src/pyeffect/__init__.py`
- Test: `tests/test_retry_backoff.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_retry_backoff.py`:

```python
def test_public_export() -> None:
    from pyeffect import Backoff as PublicBackoff, Policy as PublicPolicy

    assert PublicBackoff is Backoff
    assert PublicPolicy is Policy
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retry_backoff.py -v`
Expected: FAIL with `ImportError: cannot import name 'Backoff' from 'pyeffect'`

- [ ] **Step 3: Export `Backoff` from `src/pyeffect/__init__.py`**

Change the retry import:

```python
from pyeffect.retry import Backoff, Policy, retry
```

Add `"Backoff"` to `__all__` (after `"attempt"`, alphabetical):

```python
__all__ = ["Backoff", "Effect", ...]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_retry_backoff.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/__init__.py tests/test_retry_backoff.py
git commit -m "feat: export Backoff from pyeffect"
```

---

### Task 4: Typing contract

**Files:**
- Create: `tests/typing/retry_backoff_pass.py`

- [ ] **Step 1: Write the passing typing fixture**

Create `tests/typing/retry_backoff_pass.py`:

```python
"""Typing fixture: retry preserves Result[T, E] through backoff options."""

from typing import assert_type

from pyeffect.retry import Backoff, Policy, retry
from pyeffect.result import Err, Ok, Result


def op(attempt: int) -> Result[int, str]:
    return Ok(attempt) if attempt >= 2 else Err("flaky")


def main() -> None:
    result = retry(
        op,
        Policy(max_attempts=3, delay=0.1, backoff=Backoff.EXPONENTIAL, jitter=0.2),
    )
    assert_type(result, Result[int, str])

    selective = retry(
        op,
        Policy(max_attempts=3),
        should_retry=lambda error, attempt: error == "flaky",
    )
    assert_type(selective, Result[int, str])
```

- [ ] **Step 2: Run `ty` to verify it passes**

Run: `uv run ty check src tests`
Expected: PASS (no diagnostics).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest && uv run ruff check src tests && uv run ty check src tests`
Expected: all three PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/typing/retry_backoff_pass.py
git commit -m "test: pin retry backoff type contract"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the retry row in `README.md`**

In the "What's inside" table, change:

```markdown
| `pyeffect.retry` | `retry` + `Policy` — deterministic, injectable backoff |
```

to:

```markdown
| `pyeffect.retry` | `retry` + `Policy` + `Backoff` — deterministic, injectable backoff (constant/linear/exponential), jitter, and `should_retry` |
```

- [ ] **Step 2: Verify the full suite still passes**

Run: `uv run pytest && uv run ruff check src tests && uv run ty check src tests`
Expected: all three PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document retry backoff"
```

---

## Self-Review

**1. Spec coverage** — Backoff strategies (Task 1), jitter + `should_retry` (Task 2), export (Task 3), type contract (Task 4), docs (Task 5). Backward compatibility preserved (`Policy(3, delay=0.1)` unchanged).

**2. Placeholder scan** — Complete code in every step.

**3. Type consistency** — `Backoff`, `Policy.backoff`/`Policy.jitter`, `should_retry`, `random_float`, and `_base_delay` are named identically across module, tests, fixture, `__init__`, and README. Delay-before-retry-n semantics (1-based) are consistent between `_base_delay` and `retry`.
