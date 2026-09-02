# Do-notation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generator-expression do-notation so nested `.and_then(...)` chains become linear code that short-circuits on the first `Err`/`Nothing`.

**Architecture:** The success variants (`Ok`, `Some`) implement `__iter__` to yield their value; the failure variants (`Err`, `Nothing`) implement `__iter__` to raise a private `BaseException` (`_ShortCircuit`). A `do(genexpr)` function runs the generator expression and catches `_ShortCircuit` to short-circuit. `do_effect` wraps the same idea in a lazy, re-runnable `Effect`. `for x in result` binds `x` to the precise success type, which is why the generator-expression form is used instead of `yield from` (whose return value `ty` cannot type).

**Tech Stack:** Python 3.12+, PEP 695 generics, `ty` 0.0.77 (type contract), pytest 9, ruff.

**Why not `yield from`?** `ty` does not propagate a generator's *return* type through `yield from`, so `cart = yield from load_cart(id)` would infer `cart: Unknown`. The generator-expression form (`for cart in load_cart(id)`) reads the value off the *yield* type (`__iter__ -> Iterator[T]`), which `ty` types precisely. Verified against `ty 0.0.77` before writing this plan.

---

## File Structure

- **Create `src/pyeffect/do.py`** — `_ShortCircuit` (control-flow exception) and the `do` driver (Result + Option overloads).
- **Modify `src/pyeffect/result.py`** — add `Ok.__iter__`, `Err.__iter__`.
- **Modify `src/pyeffect/option.py`** — add `Some.__iter__`, `Nothing.__iter__`.
- **Modify `src/pyeffect/effect.py`** — add `Effect.__iter__` and `do_effect`.
- **Modify `src/pyeffect/__init__.py`** — export `do`, `do_effect`.
- **Create `tests/test_do.py`** — runtime tests.
- **Create `tests/typing/do_pass.py`, `tests/typing/do_fail.py`** — type contracts.
- **Modify `README.md`** — document do-notation.

Dependency direction: `do.py` is a runtime *leaf* (its `Result`/`Option` imports are `TYPE_CHECKING`-only), so `result.py`/`option.py`/`effect.py` may import `_ShortCircuit` from it without a cycle.

---

### Task 1: Result do-notation

**Files:**
- Create: `src/pyeffect/do.py`
- Modify: `src/pyeffect/result.py`
- Test: `tests/test_do.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_do.py`:

```python
"""Runtime behavior tests for do-notation and do_effect."""

from __future__ import annotations

from pyeffect.do import do
from pyeffect.result import Err, Ok, Result


def load_cart(cart_id: str) -> Result[dict[str, int], str]:
    return Ok({"items": 2})


def reserve_stock(items: dict[str, int]) -> Result[int, str]:
    return Ok(items["items"])


def test_do_result_binds_values() -> None:
    result = do(
        Ok(f"order:{stock}")
        for cart in load_cart("c1")
        for stock in reserve_stock(cart)
    )
    assert result == Ok("order:2")


def test_do_result_short_circuits_on_err() -> None:
    result = do(Ok(1) for _ in Err("boom"))
    assert result == Err("boom")


def test_do_result_short_circuit_skips_later_steps() -> None:
    calls: list[str] = []

    def fail() -> Result[int, str]:
        calls.append("fail")
        return Err("boom")

    def never() -> Result[int, str]:
        calls.append("never")
        return Ok(1)

    result = do(never() for _ in fail())
    assert result == Err("boom")
    assert calls == ["fail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_do.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pyeffect.do'`

- [ ] **Step 3: Create `src/pyeffect/do.py`**

```python
# ruff: noqa: UP047 -- PEP 695 type params on @overload are not checked by ty;
# classic TypeVars required (ty 0.0.77 silently skips overload checking).
"""Do-notation: linear composition of ``Result``/``Option``.

``do`` runs a generator expression in which each ``for ... in result``
clause unwraps a ``Result``/``Option`` and the first expression is the
final value. An ``Err``/``Nothing`` short-circuits the whole block::

    >>> from pyeffect.do import do
    >>> from pyeffect.result import Ok, Err
    >>> do(Ok(x * 2) for x in Ok(21))
    Ok(value=42)
    >>> do(Ok(x) for x in Err("boom"))
    Err(error='boom')

The success variants (``Ok``/``Some``) implement ``__iter__`` to yield
their value, so ``for x in result`` binds ``x`` precisely. The failure
variants (``Err``/``Nothing``) raise :class:`_ShortCircuit`, a private
``BaseException`` that ``do`` catches to short-circuit.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from pyeffect.option import Option
    from pyeffect.result import Result

__all__ = ["do"]

_T = TypeVar("_T")
_E = TypeVar("_E")


class _ShortCircuit(BaseException):
    """Control-flow signal raised when a failure variant is iterated.

    Subclasses ``BaseException`` (not ``Exception``) so user ``except
    Exception`` blocks cannot swallow the short-circuit — it is control
    flow, like ``StopIteration``. Carries the failure variant
    (``Err``/``Nothing``) back to :func:`do`.
    """

    __slots__ = ("result",)

    def __init__(self, result: Any) -> None:
        self.result = result
        super().__init__()


@overload
def do(gen: Generator[Result[_T, _E]]) -> Result[_T, _E]: ...
@overload
def do(gen: Generator[Option[_T]]) -> Option[_T]: ...
def do(gen: Generator[Any, None, Any]) -> Any:
    """Run a do-notation block expressed as a generator expression.

    Each ``for ... in result`` clause unwraps one ``Result``/``Option``:
    an ``Ok``/``Some`` binds its value to the loop variable, an
    ``Err``/``Nothing`` short-circuits the whole expression to that
    failure. The first (and only) yielded expression is the final
    ``Result``/``Option``.

    The generator must yield exactly one value — the generator-expression
    form always does. Yielding a bare non-``Result`` value is a bug the
    type checker rejects.
    """
    try:
        return next(gen)
    except _ShortCircuit as short:
        return short.result
```

- [ ] **Step 4: Add `__iter__` to `Ok` and `Err` in `src/pyeffect/result.py`**

Change the collections import at the top (line 38) and add the `do` import (after line 43):

```python
from collections.abc import Callable, Iterable, Iterator
from typing import Any, NoReturn, ParamSpec, TypeVar, cast, overload

from pyeffect.do import _ShortCircuit
from pyeffect.option import Nothing, Option, Some
```

Add `__iter__` to `Ok`, immediately after `__match_args__ = ("value",)` (line 100):

```python
    def __iter__(self) -> Iterator[T]:
        """Yield the value so ``for x in ok`` binds ``x`` in do-notation.

        ``Ok`` is iterable so ``do(... for x in result)`` can unwrap it;
        the loop variable's type is ``T``.
        """

        yield self.value
```

Add `__iter__` to `Err`, immediately after `__match_args__ = ("error",)` (line 244):

```python
    def __iter__(self) -> Iterator[NoReturn]:
        """Raise :class:`_ShortCircuit` when advanced — never yields.

        Makes do-notation short-circuit: iterating an ``Err`` raises the
        private control-flow signal that :func:`pyeffect.do.do` catches.
        """

        def _iter() -> Iterator[NoReturn]:
            raise _ShortCircuit(self)
            yield  # pragma: no cover -- unreachable, makes _iter a generator

        return _iter()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_do.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/pyeffect/do.py src/pyeffect/result.py tests/test_do.py
git commit -m "feat: add do-notation for Result"
```

---

### Task 2: Option do-notation

**Files:**
- Modify: `src/pyeffect/option.py`
- Test: `tests/test_do.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_do.py` (add a new import from `pyeffect.option`):

```python
from pyeffect.option import Nothing, Some


def test_do_option_binds_values() -> None:
    result = do(
        Some(stock) for cart in Some({"items": 2}) for stock in Some(cart["items"])
    )
    assert result == Some(2)


def test_do_option_short_circuits_on_nothing() -> None:
    result = do(Some(1) for _ in Nothing())
    assert result == Nothing()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_do.py -v`
Expected: FAIL with `TypeError: 'Some' object is not iterable`

- [ ] **Step 3: Add `__iter__` to `Some` and `Nothing` in `src/pyeffect/option.py`**

Change the collections import (line 25) and add the `do` import (after line 27):

```python
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, NoReturn

from pyeffect.do import _ShortCircuit
```

Add `__iter__` to `Some`, immediately after `__match_args__ = ("value",)` (line 61):

```python
    def __iter__(self) -> Iterator[T]:
        """Yield the value so ``for x in some`` binds ``x`` in do-notation."""

        yield self.value
```

Add `__iter__` to `Nothing`, immediately after the class docstring (line 137 area, before the first `map`):

```python
    def __iter__(self) -> Iterator[NoReturn]:
        """Raise :class:`_ShortCircuit` when advanced — never yields."""

        def _iter() -> Iterator[NoReturn]:
            raise _ShortCircuit(self)
            yield  # pragma: no cover -- unreachable, makes _iter a generator

        return _iter()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_do.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/option.py tests/test_do.py
git commit -m "feat: add do-notation for Option"
```

---

### Task 3: Effect do-notation

**Files:**
- Modify: `src/pyeffect/effect.py`
- Test: `tests/test_do.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_do.py`:

```python
from pyeffect.effect import Effect, do_effect


def test_do_effect_is_lazy() -> None:
    calls: list[str] = []

    def step() -> Effect[int, str]:
        calls.append("ran")
        return Effect.success(1)

    effect = do_effect(lambda: (Effect.success(f"v={x}") for x in step()))
    assert calls == []
    assert effect.run() == "v=1"
    assert calls == ["ran"]


def test_do_effect_is_re_runnable() -> None:
    calls: list[str] = []

    def step() -> Effect[int, str]:
        calls.append("ran")
        return Effect.success(1)

    effect = do_effect(lambda: (Effect.success(f"v={x}") for x in step()))
    assert effect.run() == "v=1"
    assert effect.run() == "v=1"
    assert calls == ["ran", "ran"]


def test_do_effect_short_circuits() -> None:
    effect = do_effect(
        lambda: (Effect.success("never") for _ in Effect.failure("nope"))
    )
    assert effect.run_result() == Err("nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_do.py -v`
Expected: FAIL with `ImportError: cannot import name 'do_effect'`

- [ ] **Step 3: Add `Effect.__iter__` and `do_effect` to `src/pyeffect/effect.py`**

Change the imports (lines 41-45) to add `Generator`, `Iterator`, and `_ShortCircuit`:

```python
from collections.abc import Callable, Generator, Iterable, Iterator
from typing import Any, TypeVar, overload

from pyeffect.do import _ShortCircuit
from pyeffect.result import Err, ErrorContext, Ok, Result, attempt
from pyeffect.retry import Policy
from pyeffect.retry import retry as retry_result
```

Add `__iter__` to `Effect`, immediately after `run(self)` (ends at line ~258, before `def sequence`):

```python
    def __iter__(self) -> Iterator[T]:
        """Run the effect and yield its value (do-notation support).

        Iterating an effect executes its thunk — but only when the
        enclosing ``do_effect`` thunk runs, so laziness is preserved. A
        failure raises :class:`_ShortCircuit`.
        """

        result = self.run_result()
        if isinstance(result, Ok):
            yield result.value
        else:
            raise _ShortCircuit(result)
```

Add `do_effect` after `sequence` (end of file):

```python
def do_effect[T, E](
    build: Callable[[], Generator[Effect[T, E]]],
) -> Effect[T, E]:
    """Compose a sequence of effects lazily into one re-runnable effect.

    ``build`` must return a *fresh* generator expression each call, so the
    resulting effect is re-runnable: every ``run``/``run_result``
    re-invokes ``build`` and re-executes each step. Each
    ``for ... in effect`` clause runs one effect; the first expression is
    the final effect::

        >>> from pyeffect import Effect
        >>> from pyeffect.effect import do_effect
        >>> do_effect(
        ...     lambda: (Effect.success(x * 2) for x in Effect.success(21))
        ... ).run()
        42
    """

    def thunk() -> Result[T, E]:
        try:
            return next(build()).run_result()
        except _ShortCircuit as short:
            return short.result

    return Effect(thunk)
```

Add `do_effect` to the module `__all__` (line ~49): `__all__ = ["Effect", "do_effect", "sequence"]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_do.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/effect.py tests/test_do.py
git commit -m "feat: add lazy re-runnable do-notation for Effect"
```

---

### Task 4: Public API exports

**Files:**
- Modify: `src/pyeffect/__init__.py`
- Test: `tests/test_do.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_do.py`:

```python
def test_public_exports() -> None:
    from pyeffect import do, do_effect

    assert callable(do)
    assert callable(do_effect)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_do.py -v`
Expected: FAIL with `ImportError: cannot import name 'do'`

- [ ] **Step 3: Export `do` and `do_effect` from `src/pyeffect/__init__.py`**

Add `from pyeffect.do import do` after the `compose` import block, and extend the `effect` import:

```python
from pyeffect.do import do
from pyeffect.effect import Effect, do_effect, sequence
```

Add `"do"` and `"do_effect"` to `__all__` (in alphabetical position):

```python
__all__ = [
    "Effect",
    "Err",
    "ErrorContext",
    "Nothing",
    "Ok",
    "Option",
    "Policy",
    "Result",
    "Some",
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
    "from_optional",
    "guard",
    "identity",
    "lift",
    "lift2",
    "lift3",
    "partial",
    "pipe",
    "retry",
    "sequence",
    "tap",
    "traverse",
    "unpack",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_do.py tests/test_doctests.py -v`
Expected: PASS (the `do`/`do_effect` doctests are now runnable via `pyeffect`)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/__init__.py tests/test_do.py
git commit -m "feat: export do and do_effect from pyeffect"
```

---

### Task 5: Typing contracts

**Files:**
- Create: `tests/typing/do_pass.py`
- Create: `tests/typing/do_fail.py`

- [ ] **Step 1: Write the passing typing fixture**

Create `tests/typing/do_pass.py`:

```python
"""Typing fixture: do/do_effect pin the success type through every step."""

from typing import assert_type

from pyeffect import Effect, Err, Nothing, Ok, Option, Result, Some, do, do_effect


def load_cart(cart_id: str) -> Result[dict[str, int], str]:
    return Ok({"items": 2})


def reserve_stock(items: dict[str, int]) -> Result[int, str]:
    return Ok(items["items"])


def main() -> None:
    # Result: the success type flows precisely; the error slot is not
    # inferable from a generator expression (documented limitation).
    result = do(
        Ok(f"order:{stock}")
        for cart in load_cart("c1")
        for stock in reserve_stock(cart)
    )
    assert_type(result.unwrap(), str)

    # Option: fully precise — Option has no error slot to infer.
    option = do(
        Some(stock) for cart in Some({"items": 2}) for stock in Some(cart["items"])
    )
    assert_type(option, Option[int])

    # Effect: success type flows; the effect stays lazy and re-runnable.
    effect = do_effect(
        lambda: (Effect.success(f"order:{stock}") for stock in Effect.success(2))
    )
    assert_type(effect.run(), str)


def short_circuit() -> None:
    # Short-circuiting still type-checks: Err/Nothing flow as their variant.
    r = do(Ok(1) for _ in Err("boom"))
    assert_type(r.unwrap(), int)

    o = do(Some(1) for _ in Nothing())
    assert_type(o, Option[int])
```

- [ ] **Step 2: Write the failing typing fixture**

Create `tests/typing/do_fail.py`:

```python
"""Typing fixture: do rejects non-generators and bare-value yields.

The intentional errors are suppressed for repo-wide checks; ty flags the
ignores as unused if the diagnostics ever change or disappear.
"""

from pyeffect import Ok, do


def main() -> None:
    # do requires a generator expression; a bare Result is not one.
    do(Ok(1))  # ty: ignore[no-matching-overload]

    # The generator must yield a Result/Option, not a bare value.
    do(42 for _ in [1])  # ty: ignore[no-matching-overload]
```

- [ ] **Step 3: Run `ty` to verify both fixtures behave as intended**

Run: `uv run ty check src tests`
Expected: PASS (no diagnostics — `do_pass.py` type-checks and `do_fail.py`'s two intentional errors are consumed by their `ty: ignore` comments).

If `ty` reports a different diagnostic code than `no-matching-overload` for the `do_fail.py` lines, update the two `# ty: ignore[...]` codes to match.

- [ ] **Step 4: Run the full test + lint + type suite**

Run: `uv run pytest && uv run ruff check src tests && uv run ty check src tests`
Expected: all three PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/typing/do_pass.py tests/typing/do_fail.py
git commit -m "test: pin do-notation type contracts"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a do-notation section to `README.md`**

After the "What's inside" table, insert:

```markdown
## Do-notation: linear composition

Nested `.and_then(...)` chains become linear with `do` — the generator-
expression spelling of `Result.gen` / `yield*`. Each `for ... in result`
clause unwraps a `Result` (or `Option`), the first expression is the final
value, and an `Err`/`Nothing` short-circuits the whole block:

```python
from pyeffect import Ok, Err, Result, do

def checkout(cart_id: str) -> Result[str, str]:
    return do(
        Ok(f"order:{stock}")
        for cart in load_cart(cart_id)
        for stock in reserve_stock(cart["items"])
    )
```

`do` runs eagerly. `do_effect` composes `Effect`s lazily into one
re-runnable effect — its argument is a thunk returning a *fresh* generator
expression, so every `.run()` re-executes the steps:

```python
from pyeffect import Effect, do_effect

effect = do_effect(
    lambda: (Effect.success(f"order:{stock}") for stock in Effect.success(2))
)
effect.run()  # "order:2" — nothing ran until now
```

The success type flows through every step precisely. Python's invariant
generics cannot infer the *error* type from a generator expression, so
`do` leaves it loose — pin it with an annotation or `map_err`, exactly as
with `and_then`.
```

Update the "What's inside" table to add the new module row and the `do_effect` entry:

```markdown
| `pyeffect.do` | `do` — generator-expression do-notation for `Result`/`Option` |
| `pyeffect.effect` | `Effect[T, E]` — a lazy, re-runnable computation; `sequence`, `attempt`, `retry_result`, `do_effect` |
```

- [ ] **Step 2: Verify doctests and the full suite still pass**

Run: `uv run pytest && uv run ruff check src tests && uv run ty check src tests`
Expected: all three PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document do-notation"
```

---

## Self-Review

**1. Spec coverage** — Do-notation is delivered for all three monads: `Result` (Task 1), `Option` (Task 2), `Effect` (Task 3), with public exports (Task 4), type contracts (Task 5), and docs (Task 6). Short-circuit, laziness, and re-runnability are all tested.

**2. Placeholder scan** — Every code step contains complete code; no TBDs, no "similar to Task N".

**3. Type consistency** — `_ShortCircuit` is defined once in `do.py` and imported by `result.py`, `option.py`, `effect.py`. `do` (value driver) and `do_effect` (lazy driver) are distinct and consistently named across tests, fixtures, exports, and README.
