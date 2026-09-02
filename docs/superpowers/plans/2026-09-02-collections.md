# Collections: `partition` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `result.partition` — collect every `Ok` and every `Err` from an iterable of `Result`s without short-circuiting.

**Architecture:** A single module-level function in `result.py` that folds an `Iterable[Result[T, E]]` into `tuple[list[T], list[E]]`. It mirrors the existing `traverse` (short-circuit) and `effect.sequence` (short-circuit), but keeps *both* branches. No new module is needed.

**Scope note (what this plan deliberately omits):** "Collect all or short-circuit on first error" already exists as `traverse(lambda x: x, results)` (Result) and `effect.sequence(effects)` (Effect), so no new `all`/`sequence` function is added — `all` would shadow the builtin and `sequence` already names the Effect variant. `partition` is the one collection capability with no existing equivalent. An `Effect.partition` (lazy) is a possible follow-up but is out of scope here.

**Tech Stack:** Python 3.12+, PEP 695 generics, `ty` 0.0.77, pytest 9, ruff.

---

## File Structure

- **Modify `src/pyeffect/result.py`** — add `partition`, add it to `__all__`.
- **Modify `src/pyeffect/__init__.py`** — export `partition`.
- **Create `tests/test_collections.py`** — runtime tests.
- **Create `tests/typing/collections_pass.py`** — type contract.

---

### Task 1: `partition`

**Files:**
- Modify: `src/pyeffect/result.py`
- Test: `tests/test_collections.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_collections.py`:

```python
"""Runtime behavior tests for result.partition."""

from __future__ import annotations

from pyeffect.result import Err, Ok, Result, partition


def test_partition_splits_ok_and_err() -> None:
    values, errors = partition([Ok(1), Err("a"), Ok(2), Err("b")])
    assert values == [1, 2]
    assert errors == ["a", "b"]


def test_partition_preserves_relative_order() -> None:
    values, errors = partition([Ok(1), Ok(2), Ok(3)])
    assert values == [1, 2, 3]
    assert errors == []


def test_partition_all_errors() -> None:
    values, errors = partition([Err("x"), Err("y")])
    assert values == []
    assert errors == ["x", "y"]


def test_partition_empty() -> None:
    values, errors = partition([])
    assert values == []
    assert errors == []


def test_partition_accepts_a_generator() -> None:
    def results() -> Result[int, str]:
        yield Ok(1)
        yield Err("boom")
        yield Ok(2)

    values, errors = partition(results())
    assert values == [1, 2]
    assert errors == ["boom"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_collections.py -v`
Expected: FAIL with `ImportError: cannot import name 'partition'`

- [ ] **Step 3: Add `partition` to `src/pyeffect/result.py`**

Add `partition` to the module `__all__` (after `guard`):

```python
__all__ = [
    "Err",
    "ErrorContext",
    "Ok",
    "Result",
    "UnwrapError",
    "attempt",
    "flatten",
    "guard",
    "partition",
    "transpose",
    "traverse",
]
```

Add the function after `traverse` (which ends around the `Ok(successes)` return):

```python
def partition[T, E](results: Iterable[Result[T, E]]) -> tuple[list[T], list[E]]:
    """Split a sequence of results into its successes and failures.

    Unlike :func:`traverse`, ``partition`` does not short-circuit: every
    element is visited, successes are collected in order into the first
    list and failures into the second::

        >>> from pyeffect.result import Ok, Err, partition
        >>> partition([Ok(1), Err("a"), Ok(2)])
        ([1, 2], ['a'])
    """

    values: list[T] = []
    errors: list[E] = []
    for result in results:
        if isinstance(result, Ok):
            values.append(result.value)
        else:
            errors.append(result.error)
    return values, errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collections.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/result.py tests/test_collections.py
git commit -m "feat: add result.partition"
```

---

### Task 2: Public export

**Files:**
- Modify: `src/pyeffect/__init__.py`
- Test: `tests/test_collections.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_collections.py`:

```python
def test_public_export() -> None:
    from pyeffect import partition

    assert partition([Ok(1), Err("a")]) == ([1], ["a"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_collections.py -v`
Expected: FAIL with `ImportError: cannot import name 'partition' from 'pyeffect'`

- [ ] **Step 3: Export `partition` from `src/pyeffect/__init__.py`**

Extend the `pyeffect.result` import:

```python
from pyeffect.result import (
    Err,
    ErrorContext,
    Ok,
    Result,
    UnwrapError,
    attempt,
    guard,
    partition,
    traverse,
)
```

Add `"partition"` to `__all__` (between `"partial"` and `"pipe"`):

```python
__all__ = [
    ...
    "partial",
    "partition",
    "pipe",
    ...
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collections.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/__init__.py tests/test_collections.py
git commit -m "feat: export partition from pyeffect"
```

---

### Task 3: Typing contract

**Files:**
- Create: `tests/typing/collections_pass.py`

- [ ] **Step 1: Write the passing typing fixture**

Create `tests/typing/collections_pass.py`:

```python
"""Typing fixture: partition returns typed (values, errors) lists."""

from typing import assert_type

from pyeffect.result import Err, Ok, Result, partition


def main() -> None:
    results: list[Result[int, str]] = [Ok(1), Err("a"), Ok(2), Err("b")]

    values, errors = partition(results)
    assert_type(values, list[int])
    assert_type(errors, list[str])

    # The success and error types follow from the input element type.
    mixed = partition([Ok(1.5), Err("x")])
    assert_type(mixed, tuple[list[float], list[str]])
```

- [ ] **Step 2: Run `ty` to verify it passes**

Run: `uv run ty check src tests`
Expected: PASS (no diagnostics).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest && uv run ruff check src tests && uv run ty check src tests`
Expected: all three PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/typing/collections_pass.py
git commit -m "test: pin partition type contract"
```

---

## Self-Review

**1. Spec coverage** — `partition` collects both branches in order (Task 1), is exported (Task 2), and its tuple-of-lists return type is pinned (Task 3).

**2. Placeholder scan** — Complete code in every step.

**3. Type consistency** — `partition` is the single name throughout; return type `tuple[list[T], list[E]]` is consistent in the implementation, docstring, tests, and typing fixture.
