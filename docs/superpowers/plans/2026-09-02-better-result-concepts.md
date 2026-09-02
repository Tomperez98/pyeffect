# better-result Concepts for pyeffect — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the high-value concepts from [better-result](https://better-result.dev) into `pyeffect` — a unified `Panic` defect type, an `UnhandledException` tagged error, error-dependent retry delays, widening recovery, a serializable `status` discriminant + codec, and several small parity wins.

**Architecture:** `pyeffect` is a zero-dependency, sync-first, fully-typed functional core (`Result`/`Option`/`Effect`). The one rule is *"bugs panic, expected failures return values."* This plan makes that rule concrete by introducing a single throwable `Panic` type for all defects, keeping expected failures as `Err` values, and adding a serialization boundary that never leaks a `Panic` as an `Err`. Backward compatibility is intentionally **not** preserved — the API is being corrected in place.

**Tech Stack:** Python ≥ 3.12 (PEP 695 generics), `uv`, `pytest`, `ruff`, `ty` (astral-sh type checker). Type contracts are pinned by `tests/typing/*_pass.py` / `*_fail.py` fixtures that `uv run ty check` validates.

---

## Scope

**In scope (this plan):**

1. **`Panic`** — a unified defect type (`panic.py`); `UnwrapError`, `UnwrapNothingError`, `MatchError`, broken `Policy`, and broken `curry` all become `Panic` (sub)classes.
2. **`UnhandledException`** — the default tagged error returned by `attempt`/`guard` when no `catch` translator is supplied.
3. **Retry** — error-dependent `delay(error, attempt)`; a throwing `should_retry`/`delay` callback becomes `Panic`.
4. **`recover`** — recovery that may widen the success type (`Result[T | U, F]`), as a module function (mirroring `flatten`/`transpose`) plus an `Effect.recover` method.
5. **Quick parity wins** — `status` discriminant on `Ok`/`Err`, narrowing `is_ok`/`is_err` type guards, `inspect_both`, `TaggedError.match()` instance method, data-last `match_error`, optional-fallback `match_error_partial`.
6. **Serialization** — `Ok`/`Err.to_dict()` envelope, `from_dict`, and a pluggable `Codec` with safe/unsafe variants.
7. **Docs & exports** — README, `__init__.py`, `llms.txt`, and updated typing fixtures.

**Deferred to separate plans (explicitly out of scope):**

- **Async** (`AsyncEffect`, `tryPromise`, `allAsync`, `partitionAsync`, cancellation via signal) — the library is sync-first by design; this is a large subsystem on its own.
- **A full schema-library integration** (Zod-style validators) — `Codec` accepts plain functions; wiring real schema libraries is additive later.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pyeffect/panic.py` | **New.** `Panic`, `panic()`, `is_panic()` — the single defect type. |
| `src/pyeffect/result.py` | `Ok`/`Err`/`Result`, `attempt`/`guard`/`traverse`/`flatten`/`transpose`/`partition`, `UnwrapError`, `ErrorContext`. **Modify:** `UnwrapError(Panic)`, `UnhandledException` default catch, `recover`, `status`, `to_dict`, `is_ok`/`is_err`, `inspect_both`. |
| `src/pyeffect/option.py` | `Some`/`Nothing`, `UnwrapNothingError`. **Modify:** `UnwrapNothingError(Panic)`. |
| `src/pyeffect/tagged.py` | `TaggedError`, `MatchError`, `match_error`, `match_error_partial`. **Modify:** `MatchError(Panic)`, add `UnhandledException`, `TaggedError.match()`, data-last `match_error`, optional-fallback `match_error_partial`. |
| `src/pyeffect/retry.py` | `retry`, `Policy`, `Backoff`. **Modify:** `Policy` validates with `Panic`; `retry` gains `delay(error, attempt)` and wraps callback defects as `Panic`. |
| `src/pyeffect/effect.py` | `Effect`, `do_effect`, `sequence`. **Modify:** `Effect.attempt` default catch → `UnhandledException`; add `Effect.recover`, `Effect.inspect_both`. |
| `src/pyeffect/compose.py` | `compose`, `curry`, `lift*`. **Modify:** `curry` construction errors → `Panic`. |
| `src/pyeffect/codec.py` | **New.** `Codec`, `ResultSerializationError`, `ResultDeserializationError`, `from_dict`. |
| `src/pyeffect/__init__.py` | Re-export all public symbols. |
| `tests/test_panic.py`, `tests/test_codec.py` | **New.** Runtime tests. |
| `tests/typing/panic_pass.py`, `tests/typing/codec_pass.py` | **New.** Typing fixtures. |
| `tests/test_result.py`, `test_option.py`, `test_tagged.py`, `test_retry.py`, `test_retry_backoff.py`, `test_compose.py`, `test_effect.py` | **Modify.** Update assertions that relied on `ValueError`/`TypeError`/raw-exception errors; add new-feature tests. |
| `tests/typing/result_pass.py`, `effect_pass.py`, `tagged_pass.py`, `retry_pass.py` | **Modify.** Pin new signatures. |
| `README.md`, `llms.txt` | **Modify/Create.** Docs. |

---

## Phase 1 — Unified `Panic` defect type

### Task 1.1: Create `panic.py`

**Files:**
- Create: `src/pyeffect/panic.py`
- Test: `tests/test_panic.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_panic.py`:

```python
"""Runtime behavior tests for Panic: the unified defect type."""

from __future__ import annotations

import pytest

from pyeffect.panic import Panic, is_panic, panic


def test_panic_is_an_exception() -> None:
    assert issubclass(Panic, Exception)


def test_panic_carries_message_and_cause() -> None:
    err = Panic("broken invariant", cause="the-cause")
    assert str(err) == "broken invariant"
    assert err.cause == "the-cause"
    assert err.tag == "Panic"


def test_panic_is_guard() -> None:
    assert Panic.is_(Panic("x"))
    assert is_panic(Panic("x"))
    assert not is_panic(ValueError("x"))


def test_panic_to_dict() -> None:
    err = Panic("broken", cause=ValueError("inner"))
    assert err.to_dict() == {
        "tag": "Panic",
        "message": "broken",
        "cause": "ValueError: inner",
    }


def test_panic_helper_raises() -> None:
    with pytest.raises(Panic) as excinfo:
        panic("unreachable", cause=42)
    assert excinfo.value.cause == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_panic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pyeffect.panic'`

- [ ] **Step 3: Write the implementation**

Create `src/pyeffect/panic.py`:

```python
"""The unified defect type: :class:`Panic`.

``pyeffect`` has one rule — *bugs panic, expected failures return values*.
``Panic`` is the throwable kind for bugs: an asserted invariant failed, a
callback broke a combinator contract, or a caller unwrapped a failure it
promised could not happen.

Catch ``Panic`` only at a defect boundary (process entry point, request
crash reporter, worker supervisor, test assertion). Never convert a
``Panic`` back into an ``Err`` — that hides the bug and corrupts the typed
error contract.
"""

from __future__ import annotations

from typing import Any, NoReturn

__all__ = ["Panic", "is_panic", "panic"]


class Panic(Exception):
    """A defect — a bug or broken invariant — thrown, never returned as ``Err``.

    Attributes:
        tag: The literal ``"Panic"`` discriminator, mirroring
            :class:`~pyeffect.tagged.TaggedError`.
        cause: The underlying value that triggered the defect, if any.
    """

    tag: str = "Panic"

    def __init__(self, message: str, cause: object | None = None) -> None:
        self.cause = cause
        super().__init__(message)

    @classmethod
    def is_(cls, value: object) -> bool:
        """Whether ``value`` is a :class:`Panic` (or a subclass)."""

        return isinstance(value, cls)

    def to_dict(self) -> dict[str, Any]:
        """A minimal serializable form of the defect."""

        return {
            "tag": self.tag,
            "message": str(self),
            "cause": _describe(self.cause),
        }


def _describe(value: object | None) -> str | None:
    """A safe string form of a cause: ``TypeName: message`` for exceptions."""

    if value is None:
        return None
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    return repr(value)


def panic(message: str, cause: object | None = None) -> NoReturn:
    """Raise a :class:`Panic`; typed ``NoReturn`` so it reads as ``return panic(...)``."""

    raise Panic(message, cause)


def is_panic(value: object) -> bool:
    """Whether ``value`` is a :class:`Panic` (or a subclass)."""

    return isinstance(value, Panic)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_panic.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/panic.py tests/test_panic.py
git commit -m "feat: add Panic unified defect type"
```

---

### Task 1.2: Make `UnwrapError` a `Panic`

**Files:**
- Modify: `src/pyeffect/result.py` (import + `UnwrapError` class)
- Test: `tests/test_result.py` (add one test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_result.py`:

```python
from pyeffect.panic import Panic


def test_unwrap_error_is_a_panic() -> None:
    with pytest.raises(Panic) as excinfo:
        Err("boom").unwrap()
    assert isinstance(excinfo.value, UnwrapError)
    assert excinfo.value.cause == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_result.py::test_unwrap_error_is_a_panic -v`
Expected: FAIL — `excinfo.value.cause` raises `AttributeError` (UnwrapError has no `cause`)

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/result.py`, add the import (after `from pyeffect.option import ...`):

```python
from pyeffect.panic import Panic
```

Change the class definition from:

```python
class UnwrapError(Exception):
    """Raised when ``unwrap()``/``expect()`` is called on an ``Err``.

    Unwrapping a failure is a bug — the caller promised success. Panic
    instead of silently returning a wrong value.

    Attributes:
        error: The payload of the ``Err`` that was unwrapped.
    """

    def __init__(self, error: object, context: str = "unwrap() on Err") -> None:
        self.error = error
        self.context = context
        super().__init__(f"{context}: Err({error!r})")
```

to:

```python
class UnwrapError(Panic):
    """Raised when ``unwrap()``/``expect()`` is called on an ``Err``.

    Unwrapping a failure is a bug — the caller promised success. Panic
    instead of silently returning a wrong value. It is a :class:`Panic`
    subtype, so catching ``Panic`` catches it at a defect boundary, while
    ``pytest.raises(UnwrapError)`` stays precise.

    Attributes:
        error: The payload of the ``Err`` that was unwrapped.
        cause: The same payload, exposed via the :class:`Panic` contract.
    """

    def __init__(self, error: object, context: str = "unwrap() on Err") -> None:
        self.error = error
        self.context = context
        super().__init__(f"{context}: Err({error!r})", cause=error)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_result.py -v`
Expected: PASS — existing `test_unwrap_on_err_is_a_defect_and_panics`, `test_expect_on_err_panics_with_message`, and `test_unwrap_error_exposes_context` still pass (they use `pytest.raises(UnwrapError)` and read `.error`/`.context`, both preserved).

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/test_result.py
git commit -m "feat: make UnwrapError a Panic subtype"
```

---

### Task 1.3: Make `UnwrapNothingError` a `Panic`

**Files:**
- Modify: `src/pyeffect/option.py`
- Test: `tests/test_option.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_option.py`:

```python
from pyeffect.panic import Panic


def test_unwrap_nothing_error_is_a_panic() -> None:
    with pytest.raises(Panic) as excinfo:
        Nothing().unwrap()
    assert isinstance(excinfo.value, UnwrapNothingError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_option.py::test_unwrap_nothing_error_is_a_panic -v`
Expected: FAIL with `DID NOT RAISE` (UnwrapNothingError is not yet a Panic)

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/option.py`, add `from pyeffect.panic import Panic` after `from pyeffect.do import _ShortCircuit`, and change:

```python
class UnwrapNothingError(Exception):
    """Raised when ``unwrap()``/``expect()`` is called on ``Nothing``.

    Unwrapping an absence is a bug — the caller promised a value. Panic
    instead of silently returning a wrong value.
    """

    def __init__(self, context: str = "unwrap() on Nothing") -> None:
        self.context = context
        super().__init__(context)
```

to:

```python
class UnwrapNothingError(Panic):
    """Raised when ``unwrap()``/``expect()`` is called on ``Nothing``.

    Unwrapping an absence is a bug — the caller promised a value. Panic
    instead of silently returning a wrong value. A :class:`Panic` subtype,
    so ``except Panic`` catches it while ``pytest.raises(UnwrapNothingError)``
    stays precise.
    """

    def __init__(self, context: str = "unwrap() on Nothing") -> None:
        self.context = context
        super().__init__(context)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_option.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/option.py tests/test_option.py
git commit -m "feat: make UnwrapNothingError a Panic subtype"
```

---

### Task 1.4: Make `MatchError` a `Panic`

**Files:**
- Modify: `src/pyeffect/tagged.py`
- Test: `tests/test_tagged.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tagged.py`:

```python
from pyeffect.panic import Panic


def test_match_error_is_a_panic() -> None:
    with pytest.raises(Panic) as excinfo:
        match_error(UserNotFound("u"), {"PermissionDenied": lambda e: 403})
    assert isinstance(excinfo.value, MatchError)
    assert excinfo.value.cause is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tagged.py::test_match_error_is_a_panic -v`
Expected: FAIL with `DID NOT RAISE` (MatchError is not yet a Panic)

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/tagged.py`, add `from pyeffect.panic import Panic` and change:

```python
class MatchError(KeyError):
    """Raised by :func:`match_error` when no handler covers the error's tag.

    A tag with no handler is a bug — the match was supposed to be
    exhaustive — so it fails fast instead of returning a wrong value.
    """

    def __init__(self, tag: object, error: object) -> None:
        self.tag = tag
        self.error = error
        super().__init__(f"no handler for tag {tag!r}")
```

to:

```python
class MatchError(Panic):
    """Raised by :func:`match_error` when no handler covers the error's tag.

    A tag with no handler is a bug — the match was supposed to be
    exhaustive — so it fails fast instead of returning a wrong value.
    """

    def __init__(self, tag: object, error: object) -> None:
        self.tag = tag
        self.error = error
        super().__init__(f"no handler for tag {tag!r}", cause=error)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tagged.py -v`
Expected: PASS — `test_match_error_raises_on_unhandled_tag` uses `pytest.raises(MatchError)`, still valid.

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/tagged.py tests/test_tagged.py
git commit -m "feat: make MatchError a Panic subtype"
```

---

### Task 1.5: `Policy` validation raises `Panic` (not `ValueError`)

**Files:**
- Modify: `src/pyeffect/retry.py`
- Test: `tests/test_retry.py`, `tests/test_retry_backoff.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_retry.py`, change the two `ValueError` expectations:

```python
from pyeffect.panic import Panic
```

```python
def test_policy_rejects_zero_attempts() -> None:
    with pytest.raises(Panic):
        Policy(max_attempts=0)


def test_policy_rejects_negative_delay() -> None:
    with pytest.raises(Panic):
        Policy(max_attempts=2, delay=-1.0)
```

In `tests/test_retry_backoff.py`:

```python
from pyeffect.panic import Panic
```

```python
def test_policy_rejects_out_of_range_jitter() -> None:
    with pytest.raises(Panic):
        Policy(max_attempts=3, jitter=1.5)
    with pytest.raises(Panic):
        Policy(max_attempts=3, jitter=-0.1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retry.py tests/test_retry_backoff.py -v`
Expected: FAIL — `pytest.raises(Panic)` does not catch `ValueError` (3 failures)

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/retry.py`, add `from pyeffect.panic import Panic` and replace the `__post_init__` body:

```python
    def __post_init__(self) -> None:
        # A broken policy is a defect and must panic unconditionally.
        if self.max_attempts < 1:
            raise Panic(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.delay < 0.0:
            raise Panic(f"delay must be >= 0, got {self.delay}")
        if not 0.0 <= self.jitter <= 1.0:
            raise Panic(f"jitter must be in [0, 1], got {self.jitter}")
```

Also update the docstring note in the `Policy` class that mentions "panics at construction" — no code change needed, it already says that.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retry.py tests/test_retry_backoff.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/retry.py tests/test_retry.py tests/test_retry_backoff.py
git commit -m "feat: Policy validation raises Panic instead of ValueError"
```

---

### Task 1.6: `curry` construction errors raise `Panic` (not `TypeError`)

**Files:**
- Modify: `src/pyeffect/compose.py`
- Test: `tests/test_compose.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_compose.py`, add `from pyeffect.panic import Panic` and change:

```python
def test_curry_rejects_variadic() -> None:
    with pytest.raises(Panic):
        curry(lambda *args: sum(args))


def test_curry_rejects_required_keyword_only() -> None:
    def needs_kw(*, required: int) -> int:
        return required

    with pytest.raises(Panic):
        curry(needs_kw)  # ty: ignore[no-matching-overload]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_compose.py -k curry -v`
Expected: FAIL — `pytest.raises(Panic)` does not catch `TypeError` (2 failures)

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/compose.py`, add `from pyeffect.panic import Panic` (after the `from pyeffect.result import ...` line) and change the two raises in `_positional_arity`:

```python
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            raise Panic(f"curry requires a fixed arity, got variadic {f!r}")
        if (
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            and parameter.default is inspect.Parameter.empty
        ):
            raise Panic(
                f"curry requires positional parameters only, got required "
                f"keyword-only {parameter.name!r} in {f!r}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_compose.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/compose.py tests/test_compose.py
git commit -m "feat: curry construction errors raise Panic instead of TypeError"
```

---

## Phase 2 — `UnhandledException` tagged error

### Task 2.1: Add `UnhandledException` to `tagged.py`

**Files:**
- Modify: `src/pyeffect/tagged.py`
- Test: `tests/test_tagged.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tagged.py`:

```python
from pyeffect.tagged import UnhandledException


def test_unhandled_exception_preserves_cause() -> None:
    cause = ValueError("boom")
    err = UnhandledException(cause)
    assert err.tag == "UnhandledException"
    assert err.cause is cause
    assert str(err) == "ValueError: boom"


def test_unhandled_exception_to_dict() -> None:
    err = UnhandledException(ValueError("boom"))
    assert err.to_dict() == {
        "tag": "UnhandledException",
        "message": "ValueError: boom",
        "cause": "ValueError: boom",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tagged.py -k unhandled -v`
Expected: FAIL with `ImportError: cannot import name 'UnhandledException'`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/tagged.py`, update `__all__` to include `"UnhandledException"` and add after the `TaggedError` class (before `MatchError`):

```python
class UnhandledException(TaggedError, tag="UnhandledException"):
    """The default error when a boundary captures an exception without translating it.

    ``attempt``/``guard`` wrap an unknown exception in this tagged error so
    every ``Err`` stays uniformly matchable by tag. The original exception
    is preserved as :attr:`cause`.
    """

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(f"{type(cause).__name__}: {cause}")

    def to_dict(self) -> dict[str, Any]:
        """Include the preserved cause alongside tag and message."""

        return {
            "tag": self.tag,
            "message": str(self),
            "cause": f"{type(self.cause).__name__}: {self.cause}",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tagged.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/tagged.py tests/test_tagged.py
git commit -m "feat: add UnhandledException tagged error"
```

---

### Task 2.2: `attempt`/`guard` default to `UnhandledException`

**Files:**
- Modify: `src/pyeffect/result.py` (`attempt`, `guard`, imports)
- Test: `tests/test_result.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_result.py`, update the import block and the two failure tests:

```python
from pyeffect.result import (
    Err,
    ErrorContext,
    Ok,
    Result,
    UnwrapError,
    attempt,
    flatten,
    guard,
    transpose,
    traverse,
)
from pyeffect.tagged import UnhandledException
```

```python
def test_attempt_failure() -> None:
    result = attempt(lambda: 1 / 0)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnhandledException)
    assert isinstance(result.error.cause, ZeroDivisionError)


def test_guard_decorated_failure() -> None:
    def raiser(x: int) -> int:
        raise ValueError(f"bad {x}")

    result = guard(raiser)(1)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnhandledException)
    assert isinstance(result.error.cause, ValueError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_result.py -k "attempt_failure or guard_decorated_failure" -v`
Expected: FAIL — `result.error` is a `ZeroDivisionError`/`ValueError`, not `UnhandledException`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/result.py`, add `from pyeffect.tagged import UnhandledException` (after the `from pyeffect.option import ...` line) and change the two overloads + implementations:

```python
@overload
def attempt(fn: Callable[[], _T]) -> Result[_T, UnhandledException]: ...
@overload
def attempt(
    fn: Callable[[], _T], *, catch: Callable[[Exception], _T2]
) -> Result[_T, _T2]: ...
def attempt(
    fn: Callable[[], _T],
    *,
    catch: Callable[[Exception], Any] = lambda e: UnhandledException(e),
) -> Result[_T, Any]:
    """Run ``fn`` and capture its failure as a value.

    Only ``Exception`` is captured — ``KeyboardInterrupt`` and
    ``SystemExit`` are bugs/interrupts and must propagate (fail fast).
    Without a custom ``catch``, the failure is wrapped in
    :class:`~pyeffect.tagged.UnhandledException` (preserving ``.cause``).
    """
    try:
        return Ok(fn())
    except Exception as exc:  # noqa: BLE001 -- the boundary contract: capture every Exception
        return Err(catch(exc))
```

```python
@overload
def guard(fn: Callable[_P, _T]) -> Callable[_P, Result[_T, UnhandledException]]: ...
@overload
def guard(
    fn: Callable[_P, _T],
    *,
    catch: Callable[[Exception], _T2],
) -> Callable[_P, Result[_T, _T2]]: ...
def guard(
    fn: Callable[_P, _T],
    *,
    catch: Callable[[Exception], Any] = lambda e: UnhandledException(e),
) -> Callable[_P, Result[_T, Any]]:
    """Decorate ``fn`` so it returns a :data:`Result` instead of raising."""

    @wraps(fn)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> Result[_T, Any]:
        return attempt(lambda: fn(*args, **kwargs), catch=catch)

    return wrapped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_result.py -v`
Expected: PASS — `test_attempt_with_custom_catch` and `test_guard_with_custom_catch` still pass (custom `catch` is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/test_result.py
git commit -m "feat: attempt/guard wrap unhandled exceptions in UnhandledException"
```

---

### Task 2.3: Update `Effect.attempt` default catch

**Files:**
- Modify: `src/pyeffect/effect.py`
- Test: `tests/typing/effect_pass.py`

- [ ] **Step 1: Write the failing typing fixture change**

In `tests/typing/effect_pass.py`, change:

```python
    # attempt: the exception boundary, deferred. The default error slot is
    # Exception — concrete, not Any — and catch narrows it exactly.
    assert_type(Effect.attempt(lambda: n).run_result(), Result[int, Exception])
```

to:

```python
    # attempt: the exception boundary, deferred. The default error slot is
    # UnhandledException — a tagged error — and catch narrows it exactly.
    assert_type(Effect.attempt(lambda: n).run_result(), Result[int, UnhandledException])
```

and add the import `from pyeffect.tagged import UnhandledException`.

- [ ] **Step 2: Run ty to verify it fails**

Run: `uv run ty check`
Expected: FAIL — `Effect.attempt(...).run_result()` is `Result[int, Exception]`, not `Result[int, UnhandledException]`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/effect.py`, add `from pyeffect.tagged import UnhandledException` and change the `Effect.attempt` overloads:

```python
    @overload
    @staticmethod
    def attempt(fn: Callable[[], _AttemptT]) -> Effect[_AttemptT, UnhandledException]: ...
    @overload
    @staticmethod
    def attempt(
        fn: Callable[[], _AttemptT], *, catch: Callable[[Exception], _AttemptE]
    ) -> Effect[_AttemptT, _AttemptE]: ...
    @staticmethod
    def attempt(
        fn: Callable[[], _AttemptT],
        *,
        catch: Callable[[Exception], Any] = lambda e: UnhandledException(e),
    ) -> Effect[_AttemptT, Any]:
```

- [ ] **Step 4: Run ty and tests to verify they pass**

Run: `uv run ty check && uv run pytest tests/test_effect.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/effect.py tests/typing/effect_pass.py
git commit -m "feat: Effect.attempt wraps unhandled exceptions in UnhandledException"
```

---

## Phase 3 — Error-dependent retry delays + `Panic` on callback defects

### Task 3.1: Add dynamic `delay(error, attempt)` to `retry`

**Files:**
- Modify: `src/pyeffect/retry.py`
- Test: `tests/test_retry.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retry.py`:

```python
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
```

Add `from pyeffect.panic import Panic` to the imports at the top of `tests/test_retry.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retry.py -k "dynamic or throwing" -v`
Expected: FAIL — `retry()` does not accept a `delay` kwarg (`TypeError`), and the Panic-wrapping test fails

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/retry.py`, replace the `retry` function:

```python
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
```

Note: this replaces the previous inline `delay *= 1.0 - policy.jitter * random_float()` logic with `_jitter`, and the final `raise AssertionError(...)` with `raise Panic(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retry.py tests/test_retry_backoff.py -v`
Expected: PASS — existing jitter/backoff tests still pass because `_jitter` reproduces the old behavior.

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/retry.py tests/test_retry.py
git commit -m "feat: add error-dependent retry delays and Panic on callback defects"
```

---

### Task 3.2: Pin retry typing

**Files:**
- Modify: `tests/typing/retry_pass.py`
- Modify: `tests/typing/retry_fail.py`

- [ ] **Step 1: Write the fixture changes**

In `tests/typing/retry_pass.py`, add after the existing `selective` block:

```python
    dynamic = retry(
        op,
        Policy(max_attempts=3),
        delay=lambda error, attempt: 1.0 if error == "flaky" else 0.0,
    )
    assert_type(dynamic, Result[int, str])
```

In `tests/typing/retry_fail.py`, add a second intentional failure:

```python
from pyeffect.result import Ok
```

```python
def main() -> None:
    # The operation must return a Result; 42 is a plain int.
    retry(lambda n: 42, Policy(max_attempts=3))  # ty: ignore[invalid-argument-type]

    # The delay callback's error parameter is the operation's error type;
    # comparing it to an int is invalid (the error is str).
    retry(
        lambda n: Ok(n),
        Policy(max_attempts=3),
        delay=lambda error, attempt: error + 1,  # ty: ignore[invalid-argument-type]
    )
```

Wait — `retry_fail.py` currently has `retry(lambda n: 42, ...)`. The second addition needs `Ok` imported. Adjust the file's imports accordingly.

- [ ] **Step 2: Run ty to verify behavior**

Run: `uv run ty check`
Expected: PASS — `retry_pass.py` accepted; `retry_fail.py` still flagged with the intended ignores (if ty reports an unused ignore, the diagnostic changed — read ty's output).

- [ ] **Step 3: Commit**

```bash
git add tests/typing/retry_pass.py tests/typing/retry_fail.py
git commit -m "test: pin retry dynamic-delay typing"
```

---

## Phase 4 — Widening `recover`

### Task 4.1: Add module-level `recover` to `result.py`

**Files:**
- Modify: `src/pyeffect/result.py`
- Test: `tests/test_result.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_result.py`:

```python
from pyeffect.result import recover


def test_recover_widens_success_type() -> None:
    result: Result[int, str] = Err("boom")
    recovered = recover(result, lambda e: Ok(len(e)))
    assert recovered == Ok(4)


def test_recover_passes_ok_through() -> None:
    result: Result[int, str] = Ok(5)
    recovered = recover(result, lambda e: Ok("guest"))
    assert recovered == Ok(5)


def test_recover_keeps_error_on_err_recovery() -> None:
    result: Result[int, str] = Err("boom")
    recovered = recover(result, lambda e: Err(e.upper()))
    assert recovered == Err("BOOM")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_result.py -k recover -v`
Expected: FAIL with `ImportError: cannot import name 'recover'`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/result.py`, add `"recover"` to `__all__`, and add the function after `transpose`:

```python
def recover[T, U, E, F](
    result: Result[T, E], f: Callable[[E], Result[U, F]]
) -> Result[T | U, F]:
    """Recover from a failure, possibly widening the success type.

    ``recover`` is :func:`or_else` generalized: the callback may return an
    ``Ok[U]`` with a *different* success type, so the result's success slot
    widens to ``T | U``. An ``Ok`` passes through unchanged.

    A method spelling is impossible: Python's invariant generics cannot make
    ``Ok.recover`` and ``Err.recover`` share one signature, so ``recover`` is
    a module function like :func:`flatten` and :func:`transpose`.

    >>> from pyeffect.result import Ok, Err, recover
    >>> recover(Err("boom"), lambda e: Ok(len(e)))
    Ok(value=4)
    """

    match result:
        case Ok():
            # Ok[T] is a member of Ok[T | U] | Err[F]; invariant generics
            # cannot widen it, so re-assert the union type (see transpose).
            return cast(Result[T | U, F], result)
        case Err():
            return cast(Result[T | U, F], f(result.error))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_result.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/test_result.py
git commit -m "feat: add recover that widens the success type"
```

---

### Task 4.2: Add `Effect.recover`

**Files:**
- Modify: `src/pyeffect/effect.py`
- Test: `tests/test_effect.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_effect.py`:

```python
def test_recover_widens_effect_success_type() -> None:
    effect: Effect[int, str] = Effect.failure("boom")
    recovered = effect.recover(lambda e: Effect.success(len(e)))
    assert recovered.run_result() == Ok(4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_effect.py::test_recover_widens_effect_success_type -v`
Expected: FAIL with `AttributeError: 'Effect' object has no attribute 'recover'`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/effect.py`, import `recover` aliased, and add a method after `catch`:

At the top, change `from pyeffect.result import Err, ErrorContext, Ok, Result, attempt` to:

```python
from pyeffect.result import (
    Err,
    ErrorContext,
    Ok,
    Result,
    attempt,
    recover as recover_result,
)
```

Then add the method after `catch` (and before `or_`):

```python
    def recover[U, E2](self, f: Callable[[E], Effect[U, E2]]) -> Effect[T | U, E2]:
        """Recover from failure, possibly widening the success type (lazy).

        ``recover`` is :meth:`catch` generalized: the callback may succeed
        with a *different* type ``U``, so the effect's success slot widens to
        ``T | U``.
        """

        def thunk() -> Result[T | U, E2]:
            return recover_result(self._thunk(), lambda error: f(error).run_result())

        return Effect(thunk)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_effect.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/effect.py tests/test_effect.py
git commit -m "feat: add Effect.recover that widens the success type"
```

---

### Task 4.3: Pin recover typing

**Files:**
- Modify: `tests/typing/result_pass.py`
- Modify: `tests/typing/effect_pass.py`

- [ ] **Step 1: Write the fixture changes**

In `tests/typing/result_pass.py`, add `recover` to the import from `pyeffect.result`, and add:

```python
# recover: widens the success type to T | U.
def to_guest(e: str) -> Result[str, str]:
    return Ok("guest")


widened: Result[int | str, str] = recover(r, to_guest)
assert_type(widened, Result[int | str, str])
```

In `tests/typing/effect_pass.py`, add:

```python
    # recover: widens the success type to T | U, lazily.
    recovered: Effect[int | str, str] = failing.recover(lambda e: Effect.success(len(e)))
    assert_type(recovered, Effect[int | str, str])
```

(Note: `failing: Effect[int, str]` is already defined in that fixture.)

- [ ] **Step 2: Run ty to verify it passes**

Run: `uv run ty check`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/typing/result_pass.py tests/typing/effect_pass.py
git commit -m "test: pin recover widening typing"
```

---

## Phase 5 — Quick parity wins

### Task 5.1: `status` discriminant on `Ok`/`Err`

**Files:**
- Modify: `src/pyeffect/result.py`
- Test: `tests/test_result.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_result.py`:

```python
def test_status_discriminant() -> None:
    assert Ok(1).status == "ok"
    assert Err("boom").status == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_result.py::test_status_discriminant -v`
Expected: FAIL with `AttributeError: 'Ok' object has no attribute 'status'`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/result.py`, add `ClassVar` to the `typing` import (`from typing import Any, ClassVar, NoReturn, ParamSpec, TypeVar, cast, overload`), then add a `status` class attribute to each dataclass:

In `Ok`:

```python
@dataclass(frozen=True, slots=True)
class Ok[T]:
    """The success variant of :data:`Result`, carrying a ``value``."""

    value: T
    status: ClassVar[str] = "ok"

    __match_args__ = ("value",)
```

In `Err`:

```python
@dataclass(frozen=True, slots=True)
class Err[E]:
    """The failure variant of :data:`Result`, carrying an ``error``."""

    error: E
    status: ClassVar[str] = "error"

    __match_args__ = ("error",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_result.py -v`
Expected: PASS — positional construction `Ok(1)`/`Err("boom")` is unaffected because `ClassVar` is not a field.

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/test_result.py
git commit -m "feat: add status discriminant to Ok and Err"
```

---

### Task 5.2: `is_ok`/`is_err` type guards

**Files:**
- Modify: `src/pyeffect/result.py`
- Test: `tests/typing/result_pass.py`

- [ ] **Step 1: Write the failing fixture**

In `tests/typing/result_pass.py`, add `is_ok, is_err` to the `pyeffect.result` import, and add:

```python
    # is_ok/is_err: TypeGuard narrowing in an if-statement.
    def read_value(result: Result[int, str]) -> int:
        if is_ok(result):
            return result.value  # narrowed to Ok[int]
        return len(result.error)  # narrowed to Err[str]
```

- [ ] **Step 2: Run ty to verify it fails**

Run: `uv run ty check`
Expected: FAIL — `is_ok` is not defined (and the fixture would not narrow)

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/result.py`, add `TypeGuard` to the `typing` import, add `"is_ok"`, `"is_err"` to `__all__`, and add the functions after the `Result` type alias (after the comment about `Result` being a union):

```python
def is_ok[T](result: Result[T, Any]) -> TypeGuard[Ok[T]]:
    """Narrow a ``Result`` to :class:`Ok` inside an ``if`` (a type guard).

    The boolean method ``.is_ok()`` does not narrow; this function does, the
    Python analogue of better-result's ``Result.isOk`` type predicate.
    """

    return isinstance(result, Ok)


def is_err[E](result: Result[Any, E]) -> TypeGuard[Err[E]]:
    """Narrow a ``Result`` to :class:`Err` inside an ``if`` (a type guard)."""

    return isinstance(result, Err)
```

- [ ] **Step 4: Run ty and tests to verify they pass**

Run: `uv run ty check && uv run pytest tests/test_result.py -v`
Expected: PASS

> **Note:** if `ty` 0.0.77 does not narrow through `TypeGuard` with PEP 695 generics, keep the two functions but change the return annotation to `bool`, add a docstring stating they do not narrow (matching `TaggedError.is_`), and simplify the fixture to assert `is_ok(result) is True`. The behavior is still useful as a uniform predicate.

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/typing/result_pass.py
git commit -m "feat: add is_ok/is_err TypeGuard functions"
```

---

### Task 5.3: `inspect_both` on `Ok`/`Err`

**Files:**
- Modify: `src/pyeffect/result.py`
- Test: `tests/test_result.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_result.py`:

```python
def test_inspect_both_runs_ok_branch() -> None:
    seen: list[int] = []
    result = Ok(2).inspect_both(seen.append, lambda e: None)
    assert result == Ok(2)
    assert seen == [2]


def test_inspect_both_runs_err_branch() -> None:
    seen: list[str] = []
    result = Err("boom").inspect_both(lambda v: None, seen.append)
    assert result == Err("boom")
    assert seen == ["boom"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_result.py -k inspect_both -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/result.py`, add to `Ok` (after `inspect_err`):

```python
    def inspect_both[E](
        self, on_ok: Callable[[T], object], on_err: Callable[..., object]
    ) -> Result[T, E]:
        """Run ``on_ok`` for its side effect; pass the result through.

        The two-branch ``tap``: observe either outcome in one call. On an
        ``Ok``, only ``on_ok`` runs.
        """

        on_ok(self.value)
        return self
```

Add to `Err` (after `inspect_err`):

```python
    def inspect_both[T](
        self, on_ok: Callable[..., object], on_err: Callable[[E], object]
    ) -> Result[T, E]:
        """Run ``on_err`` for its side effect; pass the result through.

        The two-branch ``tap``: observe either outcome in one call. On an
        ``Err``, only ``on_err`` runs.
        """

        on_err(self.error)
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_result.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/test_result.py
git commit -m "feat: add inspect_both two-branch observer"
```

---

### Task 5.4: `TaggedError.match()` instance method

**Files:**
- Modify: `src/pyeffect/tagged.py`
- Test: `tests/test_tagged.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tagged.py`:

```python
def test_tagged_error_match_instance_method() -> None:
    result = UserNotFound("u").match(
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        }
    )
    assert result == 404


def test_tagged_error_match_raises_on_missing_tag() -> None:
    with pytest.raises(MatchError):
        UserNotFound("u").match({"PermissionDenied": lambda e: 403})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tagged.py -k "instance_method or missing_tag" -v`
Expected: FAIL with `AttributeError: 'UserNotFound' object has no attribute 'match'`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/tagged.py`, add a `match` method to `TaggedError` (after `to_dict`, before `is_`):

```python
    def match[R](self, handlers: Mapping[str, Callable[[Any], R]]) -> R:
        """Exhaustively dispatch on this error's tag.

        ``error.match(handlers)`` is :func:`match_error` as a method. The
        handler map must cover the tag; a missing tag raises :class:`MatchError`.
        """

        return match_error(self, handlers)
```

(`match_error` is defined later in the module; it is resolved at call time, so the forward reference is fine.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tagged.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/tagged.py tests/test_tagged.py
git commit -m "feat: add TaggedError.match instance method"
```

---

### Task 5.5: Data-last `match_error` + optional-fallback `match_error_partial`

**Files:**
- Modify: `src/pyeffect/tagged.py`
- Test: `tests/test_tagged.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tagged.py`:

```python
def test_match_error_data_last() -> None:
    dispatch = match_error(
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        }
    )
    assert dispatch(UserNotFound("u")) == 404


def test_match_error_partial_without_fallback_passes_through() -> None:
    result = match_error_partial(
        UserNotFound("u"),
        {"PermissionDenied": lambda e: 403},
    )
    assert result is not None  # the unhandled error passes through unchanged
    assert isinstance(result, UserNotFound)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tagged.py -k "data_last or without_fallback" -v`
Expected: FAIL — data-last raises `TypeError` (missing positional arg); partial-without-fallback raises `TypeError` (missing `fallback`)

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/tagged.py`, add `overload` and `cast` to the `typing` import, and replace `match_error` and `match_error_partial`:

```python
@overload
def match_error[R](error: object, handlers: Mapping[str, Callable[[Any], R]]) -> R: ...
@overload
def match_error[R](
    handlers: Mapping[str, Callable[[Any], R]],
) -> Callable[[object], R]: ...
def match_error[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]] | None = None,
) -> Any:
    """Dispatch on ``error.tag`` and return the selected handler's result.

    ``match_error(error, handlers)`` is data-first; ``match_error(handlers)``
    is data-last and returns a curried function. A tag with no handler raises
    :class:`MatchError` (fail fast).
    """

    if handlers is None:
        # Data-last form: the first argument is actually the handlers map.
        def dispatch(value: object) -> R:
            return match_error(value, cast(Mapping[str, Callable[[Any], R]], error))

        return dispatch

    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    if handler is None:
        raise MatchError(tag, error)
    return handler(error)


@overload
def match_error_partial[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]],
    fallback: Callable[[Any], R],
) -> R: ...
@overload
def match_error_partial[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]],
) -> R | Any: ...
def match_error_partial[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]],
    fallback: Callable[[Any], Any] | None = None,
) -> Any:
    """Like :func:`match_error`, but unhandled tags do not fail.

    With a ``fallback``, unhandled tags are passed to it. Without one, the
    unhandled error passes through unchanged (identity fallback).
    """

    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    if handler is not None:
        return handler(error)
    return error if fallback is None else fallback(error)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tagged.py -v`
Expected: PASS — the existing `test_match_error_partial_falls_back` (3-arg) and `test_match_error_partial_handles_known_tag` (3-arg) still work via the first overload.

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/tagged.py tests/test_tagged.py
git commit -m "feat: data-last match_error and optional-fallback match_error_partial"
```

---

## Phase 6 — Serialization

### Task 6.1: `to_dict()` on `Ok`/`Err`

**Files:**
- Modify: `src/pyeffect/result.py`
- Test: `tests/test_result.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_result.py`:

```python
def test_to_dict_envelope() -> None:
    assert Ok(5).to_dict() == {"status": "ok", "value": 5}
    assert Err("boom").to_dict() == {"status": "error", "error": "boom"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_result.py -k to_dict -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Write the minimal implementation**

In `src/pyeffect/result.py`, add `to_dict` to `Ok` (after `with_context`):

```python
    def to_dict(self) -> dict[str, object]:
        """The wire envelope ``{"status": "ok", "value": ...}``."""

        return {"status": self.status, "value": self.value}
```

and to `Err` (after `with_context`):

```python
    def to_dict(self) -> dict[str, object]:
        """The wire envelope ``{"status": "error", "error": ...}``."""

        return {"status": self.status, "error": self.error}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_result.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/test_result.py
git commit -m "feat: add to_dict wire envelope to Ok and Err"
```

---

### Task 6.2: Create `codec.py` (`Codec`, errors, `from_dict`)

**Files:**
- Create: `src/pyeffect/codec.py`
- Test: `tests/test_codec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_codec.py`:

```python
"""Runtime behavior tests for the Result serialization codec."""

from __future__ import annotations

import pytest

from pyeffect.codec import (
    Codec,
    ResultDeserializationError,
    ResultSerializationError,
    from_dict,
)
from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result


def test_from_dict_ok_envelope() -> None:
    assert from_dict({"status": "ok", "value": 5}) == Ok(5)


def test_from_dict_err_envelope() -> None:
    assert from_dict({"status": "error", "error": "boom"}) == Err("boom")


def test_from_dict_rejects_non_dict() -> None:
    result = from_dict("nope")
    assert isinstance(result, Err)
    assert isinstance(result.error, ResultDeserializationError)


def test_from_dict_rejects_unknown_status() -> None:
    result = from_dict({"status": "weird"})
    assert isinstance(result, Err)
    assert isinstance(result.error, ResultDeserializationError)


def test_codec_roundtrip() -> None:
    codec: Codec[int, str] = Codec(
        encode_ok=lambda n: str(n),
        encode_err=lambda e: e,
        decode_ok=lambda w: Ok(int(w)),
        decode_err=lambda w: Ok(w),
    )
    encoded = codec.serialize(Ok(5))
    assert encoded == Ok({"status": "ok", "value": "5"})
    assert codec.deserialize({"status": "ok", "value": "5"}) == Ok(5)
    assert codec.deserialize({"status": "error", "error": "boom"}) == Err("boom")


def test_codec_serialize_catches_encoder_defects() -> None:
    def boom(x: int) -> object:
        raise ValueError("bad")

    codec: Codec[int, str] = Codec(
        encode_ok=boom,
        encode_err=lambda e: e,
        decode_ok=lambda w: Ok(int(w)),
        decode_err=lambda w: Ok(w),
    )
    result = codec.serialize(Ok(5))
    assert isinstance(result, Err)
    assert isinstance(result.error, ResultSerializationError)


def test_codec_serialize_unsafe_panics() -> None:
    def boom(x: int) -> object:
        raise ValueError("bad")

    codec: Codec[int, str] = Codec(
        encode_ok=boom,
        encode_err=lambda e: e,
        decode_ok=lambda w: Ok(int(w)),
        decode_err=lambda w: Ok(w),
    )
    with pytest.raises(Panic):
        codec.serialize_unsafe(Ok(5))


def test_codec_deserialize_unsafe_keeps_domain_err() -> None:
    codec: Codec[int, str] = Codec(
        encode_ok=lambda n: str(n),
        encode_err=lambda e: e,
        decode_ok=lambda w: Ok(int(w)),
        decode_err=lambda w: Ok(w),
    )
    assert codec.deserialize_unsafe({"status": "error", "error": "boom"}) == Err("boom")


def test_codec_deserialize_unsafe_panics_on_bad_envelope() -> None:
    codec: Codec[int, str] = Codec(
        encode_ok=lambda n: str(n),
        encode_err=lambda e: e,
        decode_ok=lambda w: Ok(int(w)),
        decode_err=lambda w: Ok(w),
    )
    with pytest.raises(Panic):
        codec.deserialize_unsafe("not-a-dict")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_codec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pyeffect.codec'`

- [ ] **Step 3: Write the implementation**

Create `src/pyeffect/codec.py`:

```python
"""Serialization boundary for :data:`~pyeffect.result.Result`.

A ``Result`` in memory is not proof that JSON or stored data has the same
shape. A :class:`Codec` validates both the envelope and its payloads, while
allowing in-memory and wire representations to differ (e.g. ``date`` objects
vs ISO text). Zero dependencies: "schemas" are plain functions.

The wire envelope is one of::

    {"status": "ok", "value": <encoded value>}
    {"status": "error", "error": <encoded error>}
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result
from pyeffect.tagged import TaggedError

__all__ = [
    "Codec",
    "ResultDeserializationError",
    "ResultSerializationError",
    "from_dict",
]

_STATUS_OK = "ok"
_STATUS_ERROR = "error"


class ResultSerializationError(TaggedError, tag="ResultSerializationError"):
    """A payload failed to encode to its wire form."""

    def __init__(
        self, value: object, message: str = "could not serialize value"
    ) -> None:
        self.value = value
        super().__init__(message)


class ResultDeserializationError(TaggedError, tag="ResultDeserializationError"):
    """An envelope or payload failed to decode from its wire form."""

    def __init__(
        self, value: object, message: str = "could not deserialize value"
    ) -> None:
        self.value = value
        super().__init__(message)


def from_dict(data: object) -> Result[Any, ResultDeserializationError]:
    """Decode a bare envelope without payload validation.

    Use a :class:`Codec` when payloads need validation or mapping; this only
    checks the envelope shape and returns payloads as-is.
    """

    if not isinstance(data, dict):
        return Err(ResultDeserializationError(data))
    status = data.get("status")
    if status == _STATUS_OK and "value" in data:
        return Ok(data["value"])
    if status == _STATUS_ERROR and "error" in data:
        return Err(data["error"])
    return Err(ResultDeserializationError(data))


@dataclass(frozen=True, slots=True)
class Codec[T, E]:
    """Maps a ``Result[T, E]`` to and from a ``{"status", ...}`` envelope.

    Attributes:
        encode_ok: ``T -> wire`` for success payloads (may raise; caught as a
            serialization error).
        encode_err: ``E -> wire`` for error payloads.
        decode_ok: ``wire -> Result[T, Any]`` for success payloads.
        decode_err: ``wire -> Result[E, Any]`` for error payloads.
    """

    encode_ok: Callable[[T], object]
    encode_err: Callable[[E], object]
    decode_ok: Callable[[object], Result[T, Any]]
    decode_err: Callable[[object], Result[E, Any]]

    def serialize(
        self, result: Result[T, E]
    ) -> Result[dict[str, object], ResultSerializationError]:
        """Encode ``result`` into an envelope, or return a serialization error."""

        match result:
            case Ok(value):
                try:
                    return Ok({"status": _STATUS_OK, "value": self.encode_ok(value)})
                except Exception:
                    return Err(ResultSerializationError(value))
            case Err(error):
                try:
                    return Ok(
                        {"status": _STATUS_ERROR, "error": self.encode_err(error)}
                    )
                except Exception:
                    return Err(ResultSerializationError(error))

    def serialize_unsafe(self, result: Result[T, E]) -> dict[str, object]:
        """Encode ``result``; a serialization error is a defect (:class:`Panic`)."""

        match self.serialize(result):
            case Ok(envelope):
                return envelope
            case Err(error):
                raise Panic("serialization failed", cause=error)

    def deserialize(self, data: object) -> Result[T, E | ResultDeserializationError]:
        """Decode an envelope, returning the domain Result or a deserialization error."""

        if not isinstance(data, dict):
            return Err(ResultDeserializationError(data))
        status = data.get("status")
        if status == _STATUS_OK:
            return self.decode_ok(data.get("value")).map_err(ResultDeserializationError)
        if status == _STATUS_ERROR:
            decoded = self.decode_err(data.get("error")).map_err(
                ResultDeserializationError
            )
            # A valid decoded Err is a domain Err; a decode failure is a
            # deserialization error. Both occupy the Err slot, whose type
            # widens to E | ResultDeserializationError — invariant generics
            # cannot express that widening without a re-assertion.
            return decoded.fold(
                on_ok=lambda domain_error: cast(
                    Result[T, E | ResultDeserializationError], Err(domain_error)
                ),
                on_err=lambda issue: cast(
                    Result[T, E | ResultDeserializationError], Err(issue)
                ),
            )
        return Err(ResultDeserializationError(data))

    def deserialize_unsafe(self, data: object) -> Result[T, E]:
        """Decode an envelope; a deserialization error is a defect (:class:`Panic`).

        A valid serialized ``Err`` remains a domain ``Err`` — only a malformed
        envelope or a payload that fails its decode schema panics.
        """

        result = self.deserialize(data)
        match result:
            case Ok(value):
                return Ok(value)
            case Err(error):
                if isinstance(error, ResultDeserializationError):
                    raise Panic("deserialization failed", cause=error)
                return Err(cast(E, error))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_codec.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/codec.py tests/test_codec.py
git commit -m "feat: add Result serialization codec and envelope decoding"
```

---

### Task 6.3: Pin codec typing

**Files:**
- Create: `tests/typing/codec_pass.py`

- [ ] **Step 1: Write the fixture**

```python
"""Typing fixture: Codec/from_dict pinned with assert_type."""

from typing import Any, assert_type

from pyeffect.codec import Codec, ResultDeserializationError, from_dict
from pyeffect.result import Err, Ok, Result


def main(n: int, boom: str) -> None:
    codec: Codec[int, str] = Codec(
        encode_ok=lambda x: str(x),
        encode_err=lambda e: e,
        decode_ok=lambda w: Ok(int(w)),
        decode_err=lambda w: Ok(w),
    )

    # serialize returns a Result over the wire envelope.
    assert_type(
        codec.serialize(Ok(n)),
        Result[dict[str, object], Any],
    )

    # deserialize: success stays T; the error widens to E | DeserializationError.
    assert_type(
        codec.deserialize({"status": "ok", "value": "1"}),
        Result[int, str | ResultDeserializationError],
    )

    # unsafe deserialize narrows the error back to E.
    assert_type(
        codec.deserialize_unsafe({"status": "error", "error": boom}),
        Result[int, str],
    )

    # from_dict returns a loosely-typed Result.
    assert_type(
        from_dict({"status": "ok", "value": 1}), Result[Any, ResultDeserializationError]
    )
```

- [ ] **Step 2: Run ty to verify it passes**

Run: `uv run ty check`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/typing/codec_pass.py
git commit -m "test: pin codec typing"
```

---

## Phase 7 — Docs, exports, and integration

### Task 7.1: Update `__init__.py` exports

**Files:**
- Modify: `src/pyeffect/__init__.py`
- Test: `tests/test_result.py` (public exports are already tested per-module; add one here)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_result.py`:

```python
def test_public_exports_include_new_symbols() -> None:
    from pyeffect import (
        Codec,
        Panic,
        ResultDeserializationError,
        ResultSerializationError,
        UnhandledException,
        from_dict,
        is_err,
        is_ok,
        is_panic,
        panic,
        recover,
    )

    assert Panic is not None
    assert callable(is_ok)
    assert callable(is_err)
    assert callable(is_panic)
    assert callable(panic)
    assert callable(recover)
    assert callable(from_dict)
    assert Codec is not None
    assert UnhandledException is not None
    assert ResultSerializationError is not None
    assert ResultDeserializationError is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_result.py::test_public_exports_include_new_symbols -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

Rewrite `src/pyeffect/__init__.py`:

```python
"""pyeffect: a fully typed functional core for Python."""

from pyeffect.codec import (
    Codec,
    ResultDeserializationError,
    ResultSerializationError,
    from_dict,
)
from pyeffect.compose import (
    compose,
    constant,
    curry,
    flip,
    identity,
    lift,
    lift2,
    lift3,
    partial,
    tap,
    unpack,
)
from pyeffect.do import do
from pyeffect.effect import Effect, do_effect, sequence
from pyeffect.option import (
    Nothing,
    Option,
    Some,
    UnwrapNothingError,
    flatten,
    from_optional,
)
from pyeffect.panic import Panic, is_panic, panic
from pyeffect.pipe import pipe
from pyeffect.result import (
    Err,
    ErrorContext,
    Ok,
    Result,
    UnwrapError,
    attempt,
    guard,
    is_err,
    is_ok,
    partition,
    recover,
    traverse,
)
from pyeffect.retry import Backoff, Policy, retry
from pyeffect.tagged import (
    MatchError,
    TaggedError,
    UnhandledException,
    match_error,
    match_error_partial,
)

__all__ = [
    "Backoff",
    "Codec",
    "Effect",
    "Err",
    "ErrorContext",
    "MatchError",
    "Nothing",
    "Ok",
    "Option",
    "Panic",
    "Policy",
    "Result",
    "ResultDeserializationError",
    "ResultSerializationError",
    "Some",
    "TaggedError",
    "UnhandledException",
    "UnwrapError",
    "UnwrapNothingError",
    "attempt",
    "compose",
    "constant",
    "curry",
    "do",
    "do_effect",
    "flatten",
    "flip",
    "from_dict",
    "from_optional",
    "guard",
    "identity",
    "is_err",
    "is_ok",
    "is_panic",
    "lift",
    "lift2",
    "lift3",
    "match_error",
    "match_error_partial",
    "panic",
    "partial",
    "partition",
    "pipe",
    "recover",
    "retry",
    "sequence",
    "tap",
    "traverse",
    "unpack",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_result.py::test_public_exports_include_new_symbols -v && uv run pytest -q`
Expected: PASS; the full suite passes.

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/__init__.py tests/test_result.py
git commit -m "feat: export new symbols from pyeffect"
```

---

### Task 7.2: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the content**

Add/replace these sections in `README.md`:

1. In the "What it is" intro, after the "one rule" blockquote, add:

```markdown
### The one rule

> **Bugs panic, expected failures return values.**

- **Panic** when the program reaches a state that should be impossible —
  `unwrap()` on `Err`/`Nothing`, a broken retry `Policy`, a non-exhaustive
  `match_error`, an over-arity `curry`. Every defect raises the same type —
  `Panic` (with `UnwrapError`/`UnwrapNothingError`/`MatchError` as precise
  subtypes) — so a defect boundary catches `Panic` and reports the bug.
- **Return a value** when failure is expected — network errors, bad input,
  absence. The caller decides what to do with it.
```

2. Replace the "Tagged errors" section's intro to mention `error.match(...)` and `UnhandledException`.

3. Add a "Recovery and serialization" section:

```markdown
## Recovery and serialization

`recover` is `or_else` generalized: it may return a *different* success type,
widening the result to `T | U`:

```python
from pyeffect import Ok, Err, recover

result = recover(Err("boom"), lambda e: Ok(len(e)))  # Ok(4)
```

Every `Result` carries a serializable `status` discriminant and a `to_dict()`
wire envelope; `from_dict` and a pluggable `Codec` decode it back:

```python
from pyeffect import Codec, Err, Ok, from_dict

assert Ok(5).to_dict() == {"status": "ok", "value": 5}
assert from_dict({"status": "error", "error": "boom"}) == Err("boom")
```

The `Codec` maps payloads to/from their wire form with safe (`Result`-returning)
and unsafe (`Panic`-raising) variants — see the module docstring in
`pyeffect.codec`.
```

- [ ] **Step 2: Verify README renders**

Run: `uv run python -c "import pyeffect; print(pyeffect.__all__)"`
Expected: prints the full export list without error.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document Panic, recover, and serialization"
```

---

### Task 7.3: Add `llms.txt` (agent-readable contract)

**Files:**
- Create: `llms.txt`

- [ ] **Step 1: Write the file**

```markdown
# pyeffect

> Typed, composable error handling for Python with Result values, tagged
> errors, and lazy Effect composition. The one rule: bugs panic, expected
> failures return values.

## Search vocabulary

- `Result`, `Ok`, `Err` — the value-carrying form of expected failure.
- `attempt`, `guard` — capture exceptions; wrap unknown ones in `UnhandledException`.
- `map`, `map_err`, `and_then`, `or_else`, `recover`, `fold` — combinators.
- `Panic`, `panic`, `is_panic` — the unified defect type; `UnwrapError`,
  `UnwrapNothingError`, `MatchError` are precise subtypes.
- `TaggedError`, `match_error`, `match_error_partial`, `error.match()` — tagged errors.
- `do`, `do_effect` — generator-expression do-notation.
- `Effect` — lazy, re-runnable computation; `run`/`run_result` are the only impure moments.
- `retry`, `Policy`, `Backoff` — deterministic, injectable retry with dynamic delays.
- `Codec`, `from_dict`, `ResultSerializationError`, `ResultDeserializationError` — serialization.
- `Option`, `Some`, `Nothing`, `from_optional` — expected absence.

## Agent checklist

1. Return `Err` for failures the caller can decide on; let `Panic` expose bugs.
2. Tag domain errors with `TaggedError`; translate unknown exceptions at
   adapters via `attempt`/`guard`.
3. Compose with `do` (generator expressions); do not `unwrap()` in normal flow.
4. Handle the complete error union at a policy boundary with `fold`/`match_error`.
5. Catch `Panic` only at defect boundaries; never turn it back into an `Err`.
```

- [ ] **Step 2: Commit**

```bash
git add llms.txt
git commit -m "docs: add llms.txt agent-readable contract"
```

---

### Task 7.4: Final full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire gate**

Run: `uv run ty check && uv run ruff check && uv run pytest`
Expected: PASS on all three (type check, lint, tests including doctests).

- [ ] **Step 2: Commit any stragglers**

```bash
git status
git add -A
git commit -m "chore: final integration pass"  # only if there are changes
```

---

## Self-Review

**Spec coverage** — every recommendation is mapped to a task:
1. `Panic` → Phase 1. 2. Retry dynamic delay → Phase 3. 3. `recover` widening → Phase 4. 4. Serialization → Phase 6 (+ `status`/`to_dict`). 5. `UnhandledException` → Phase 2. 6. Quick wins → Phase 5. 7. Async → explicitly deferred (out of scope, noted). 8. `llms.txt` → Task 7.3.

**Placeholder scan** — no TBD/TODO; every code step shows full code. The one conditional note in Task 5.2 is concrete guidance (a specific `ty` fallback), not a placeholder.

**Type consistency** — `recover` is consistently `Result[T | U, F]` / `Effect[T | U, E2]`; `UnhandledException` is imported identically in `result.py` and `effect.py`; `is_ok`/`is_err` names match their `__all__`/`__init__` entries; the codec's `ResultSerializationError`/`ResultDeserializationError`/`Codec`/`from_dict` names match across `codec.py`, `tests`, and `__init__.py`.

**Known risks to verify during execution:**
- `ty` 0.0.77 support for `TypeGuard` narrowing of a PEP 695 union (Task 5.2 has a fallback).
- `ty` acceptance of `T | U` in PEP 695 return annotations (Task 4.1) — if it rejects, switch the cast target to `Result[Any, F]` with a doc note, mirroring the existing `Effect.success` `Any`-slot compromise.
- `ty` narrowing of `E | ResultDeserializationError` via `isinstance` in `deserialize_unsafe` — the `cast(E, error)` is already in place as the safe fallback.
