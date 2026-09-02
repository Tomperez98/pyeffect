# Tagged Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add discriminated errors — a `TaggedError` base carrying a literal `tag`, `.is()` guards, `to_dict()`, and value-returning `match_error` / `match_error_partial` dispatch.

**Architecture:** `TaggedError` is an `Exception` subclass whose subclasses declare a `tag` via `__init_subclass__(tag=...)` (defaulting to the class name). `match_error` looks up the tag in a handler `Mapping` and returns the handler's result, failing fast (`MatchError`) on an unhandled tag; `match_error_partial` passes unhandled tags to a fallback. Type narrowing is provided by Python's native `isinstance`/`match` statement — `ty` narrows `isinstance(x, UserNotFound)`, which is the idiomatic (and only) exhaustive-narrowing mechanism in Python. `match_error` handlers are typed `Callable[[Any], R]`; per-key narrowing like TypeScript's `matchError` is not expressible in Python's type system, so narrowing inside handlers is done with `isinstance`.

**Tech Stack:** Python 3.12+, PEP 695 generics, `ty` 0.0.77, pytest 9, ruff.

---

## File Structure

- **Create `src/pyeffect/tagged.py`** — `TaggedError`, `MatchError`, `match_error`, `match_error_partial`.
- **Modify `src/pyeffect/__init__.py`** — export the four names.
- **Create `tests/test_tagged.py`** — runtime tests.
- **Create `tests/typing/tagged_pass.py`** — type contract (narrowing + dispatch return types).
- **Modify `README.md`** — document tagged errors.

---

### Task 1: `TaggedError` base class

**Files:**
- Create: `src/pyeffect/tagged.py`
- Test: `tests/test_tagged.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tagged.py`:

```python
"""Runtime behavior tests for TaggedError and match_error."""

from __future__ import annotations

import pytest

from pyeffect.tagged import (
    MatchError,
    TaggedError,
    match_error,
    match_error_partial,
)


class UserNotFound(TaggedError, tag="UserNotFound"):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user {user_id} not found")


class PermissionDenied(TaggedError, tag="PermissionDenied"):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"missing {permission}")


class Unspecified(TaggedError):
    """No explicit tag: defaults to the class name."""


def test_explicit_tag() -> None:
    assert UserNotFound("u").tag == "UserNotFound"


def test_tag_defaults_to_class_name() -> None:
    assert Unspecified().tag == "Unspecified"


def test_is_a_real_exception() -> None:
    err = UserNotFound("u")
    assert isinstance(err, Exception)
    assert str(err) == "user u not found"


def test_is_guard() -> None:
    assert UserNotFound.is_(UserNotFound("u"))
    assert not UserNotFound.is_(PermissionDenied("p"))
    assert TaggedError.is_(UserNotFound("u"))


def test_to_dict() -> None:
    assert UserNotFound("u").to_dict() == {
        "tag": "UserNotFound",
        "message": "user u not found",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tagged.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pyeffect.tagged'`

- [ ] **Step 3: Create `src/pyeffect/tagged.py`**

```python
"""Discriminated errors: a ``TaggedError`` with a literal ``tag``.

A ``TaggedError`` subclass declares a string tag that callers can switch on
without string-matching on the message::

    >>> from pyeffect.tagged import TaggedError, match_error
    >>> class NotFound(TaggedError, tag="NotFound"):
    ...     def __init__(self, key: str) -> None:
    ...         self.key = key
    ...         super().__init__(f"{key} not found")
    >>> match_error(NotFound("x"), {"NotFound": lambda e: 404})
    404

Narrowing is Python's native ``isinstance``/``match`` (``ty`` narrows the
branch); ``.is_`` is a convenience boolean guard that does not narrow.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

__all__ = ["MatchError", "TaggedError", "match_error", "match_error_partial"]

_R = TypeVar("_R")


class TaggedError(Exception):
    """Base class for errors carrying a literal ``tag``.

    Subclasses declare the tag with a keyword argument
    (``class UserNotFound(TaggedError, tag="UserNotFound")``); when omitted
    it defaults to the class name. The tag lives on the class, so every
    instance of a subclass shares it.
    """

    tag: str

    def __init_subclass__(cls, *, tag: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.tag = tag if tag is not None else cls.__name__

    def __init__(self, message: str = "") -> None:
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """A minimal serializable form; subclasses override to add payload."""

        return {"tag": self.tag, "message": str(self)}

    @classmethod
    def is_(cls, value: object) -> bool:
        """Whether ``value`` is an instance of this class.

        A boolean convenience guard. For *type narrowing*, use
        ``isinstance(value, cls)`` or a ``match`` statement — ``ty``
        narrows those, but cannot narrow through a plain ``bool`` method.
        """

        return isinstance(value, cls)


class MatchError(KeyError):
    """Raised by :func:`match_error` when no handler covers the error's tag.

    A tag with no handler is a bug — the match was supposed to be
    exhaustive — so it fails fast instead of returning a wrong value.
    """

    def __init__(self, tag: object, error: object) -> None:
        self.tag = tag
        self.error = error
        super().__init__(f"no handler for tag {tag!r}")


def match_error(error: object, handlers: Mapping[str, Callable[[Any], _R]]) -> _R:
    """Dispatch on ``error.tag`` and return the selected handler's result.

    ``handlers`` maps tag strings to single-argument callables. The handler
    receives the error unchanged. A tag with no handler raises
    :class:`MatchError` (fail fast). Handlers are typed ``Callable[[Any],
    ...]`` — Python cannot narrow a handler's parameter per dict key, so
    narrow with ``isinstance``/``match`` inside the handler when you need a
    specific field.
    """

    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    if handler is None:
        raise MatchError(tag, error)
    return handler(error)


def match_error_partial(
    error: object,
    handlers: Mapping[str, Callable[[Any], _R]],
    fallback: Callable[[Any], _R],
) -> _R:
    """Like :func:`match_error`, but unhandled tags go to ``fallback``.

    Use this to transform a subset of variants while leaving the rest
    unchanged or mapped to a default.
    """

    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    return handler(error) if handler is not None else fallback(error)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tagged.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/tagged.py tests/test_tagged.py
git commit -m "feat: add TaggedError and match_error dispatch"
```

---

### Task 2: Dispatch behavior

**Files:**
- Test: `tests/test_tagged.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tagged.py`:

```python
def test_match_error_dispatches() -> None:
    result = match_error(
        UserNotFound("u"),
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        },
    )
    assert result == 404


def test_match_error_receives_the_error() -> None:
    result = match_error(
        PermissionDenied("admin"),
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: e.permission,
        },
    )
    assert result == "admin"


def test_match_error_raises_on_unhandled_tag() -> None:
    with pytest.raises(MatchError):
        match_error(UserNotFound("u"), {"PermissionDenied": lambda e: 403})


def test_match_error_partial_falls_back() -> None:
    result = match_error_partial(
        UserNotFound("u"),
        {"PermissionDenied": lambda e: 403},
        lambda e: 500,
    )
    assert result == 500


def test_match_error_partial_handles_known_tag() -> None:
    result = match_error_partial(
        UserNotFound("u"),
        {"UserNotFound": lambda e: 404},
        lambda e: 500,
    )
    assert result == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tagged.py -v`
Expected: FAIL with `ImportError` (names not defined yet — if they already pass, the functions were defined in Task 1; in that case skip to Step 4)

- [ ] **Step 3: (Already implemented in Task 1)** `match_error` / `match_error_partial` are defined in `src/pyeffect/tagged.py`. No code change needed here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tagged.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_tagged.py
git commit -m "test: cover match_error dispatch and fallback"
```

---

### Task 3: Public exports

**Files:**
- Modify: `src/pyeffect/__init__.py`
- Test: `tests/test_tagged.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tagged.py`:

```python
def test_public_exports() -> None:
    from pyeffect import MatchError, TaggedError, match_error, match_error_partial

    assert TaggedError is not None
    assert MatchError is not None
    assert callable(match_error)
    assert callable(match_error_partial)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tagged.py -v`
Expected: FAIL with `ImportError: cannot import name 'TaggedError' from 'pyeffect'`

- [ ] **Step 3: Export the names from `src/pyeffect/__init__.py`**

Add after the `retry` import:

```python
from pyeffect.tagged import MatchError, TaggedError, match_error, match_error_partial
```

Add to `__all__` at the three alphabetical positions shown (each snippet is the exact surrounding entries in the existing list):

```python
("ErrorContext",)
("MatchError",)
("Nothing",)
```

```python
("Some",)
("TaggedError",)
("UnwrapError",)
```

```python
("lift3",)
("match_error",)
("match_error_partial",)
("partial",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tagged.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pyeffect/__init__.py tests/test_tagged.py
git commit -m "feat: export TaggedError and match_error from pyeffect"
```

---

### Task 4: Typing contract

**Files:**
- Create: `tests/typing/tagged_pass.py`

- [ ] **Step 1: Write the passing typing fixture**

Create `tests/typing/tagged_pass.py`:

```python
"""Typing fixture: TaggedError tags, isinstance narrowing, match dispatch."""

from typing import assert_type

from pyeffect.tagged import TaggedError, match_error, match_error_partial


class UserNotFound(TaggedError, tag="UserNotFound"):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user {user_id} not found")


class PermissionDenied(TaggedError, tag="PermissionDenied"):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"missing {permission}")


def narrow(error: UserNotFound | PermissionDenied) -> str:
    # isinstance narrows the union; the else branch is PermissionDenied.
    if isinstance(error, UserNotFound):
        return error.user_id
    return error.permission


def main() -> None:
    assert_type(UserNotFound("u").tag, str)
    assert_type(UserNotFound("u").to_dict(), dict[str, object])
    assert_type(narrow(UserNotFound("u")), str)

    # match_error returns the handler result type.
    status: int = match_error(
        UserNotFound("u"),
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        },
    )
    assert_type(status, int)

    recovered: str = match_error_partial(
        UserNotFound("u"),
        {"UserNotFound": lambda e: "not-found"},
        lambda e: "other",
    )
    assert_type(recovered, str)
```

- [ ] **Step 2: Run `ty` to verify it passes**

Run: `uv run ty check src tests`
Expected: PASS (no diagnostics).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest && uv run ruff check src tests && uv run ty check src tests`
Expected: all three PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/typing/tagged_pass.py
git commit -m "test: pin tagged-error type contracts"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Tagged errors" section to `README.md`**

After the "Do-notation" section, insert:

```markdown
## Tagged errors

Errors are values you can discriminate by a literal `tag` instead of
string-matching on a message. Subclass `TaggedError` with a `tag`, then
dispatch with `match_error` (fails fast on an unhandled tag) or
`match_error_partial` (passes unhandled tags to a fallback):

```python
from pyeffect import TaggedError, match_error

class UserNotFound(TaggedError, tag="UserNotFound"):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user {user_id} not found")

class PermissionDenied(TaggedError, tag="PermissionDenied"):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"missing {permission}")

def status(error: UserNotFound | PermissionDenied) -> int:
    return match_error(error, {
        "UserNotFound": lambda e: 404,
        "PermissionDenied": lambda e: 403,
    })
```

Narrow to a concrete error with native `isinstance`/`match` — `ty` narrows
the branch:

```python
def describe(error: UserNotFound | PermissionDenied) -> str:
    match error:
        case UserNotFound(user_id=uid):
            return f"no user {uid}"
        case PermissionDenied(permission=perm):
            return f"missing {perm}"
```

The tag defaults to the class name when omitted; `tag`, `.is_()`, and
`to_dict()` are always available.
```

Update the "What's inside" table:

```markdown
| `pyeffect.tagged` | `TaggedError`, `MatchError`, `match_error`, `match_error_partial` |
```

- [ ] **Step 2: Verify the full suite still passes**

Run: `uv run pytest && uv run ruff check src tests && uv run ty check src tests`
Expected: all three PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document tagged errors"
```

---

## Self-Review

**1. Spec coverage** — Discriminated tag (Task 1), `.is_`/`to_dict` (Task 1), dispatch + fallback (Task 2), exports (Task 3), type contract (Task 4), docs (Task 5). All covered.

**2. Placeholder scan** — Every code step is complete; no TBDs.

**3. Type consistency** — `TaggedError`/`MatchError`/`match_error`/`match_error_partial` names are identical across module, tests, fixtures, `__init__`, and README. `tag` is a class attribute set in `__init_subclass__`, accessed as `error.tag` everywhere.
