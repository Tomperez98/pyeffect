# pyeffect

Handle expected failures as **values** — a fully typed `Result`, `Option`,
and lazy `Effect` core for Python 3.14+.

```python
from pyeffect import Err, Ok, Result, attempt

result: Result[int, str] = attempt(lambda: int("42")).map(lambda n: n * 2)
match result:
    case Ok(value):
        print(value)  # 84
    case Err(error):
        print(f"failed: {error}")
```

## What it is

`pyeffect` is a functional core for Python that turns expected failure
(network errors, bad input, absence) into values you can compose, instead of
exceptions you must catch. `Result` and `Option` handle the data; `Effect`
defers side effects until you run them.

### The one rule

> **Bugs panic, expected failures return values.**

- **Panic** when the program reaches a state that should be impossible —
  `unwrap()` on `Err`/`Nothing`, a broken retry `Policy`, an over-arity
  `curry`. The damage stops at the exact line.
- **Return a value** when failure is expected — network errors, bad input,
  absence. The caller decides what to do with it.

## Install

Not on PyPI yet — clone the repo and install from source:

```bash
uv sync
```

That installs `pyeffect` and the dev dependencies (pytest, ruff, ty) into
`.venv`.

## A complete example

Paste this and it runs — expected output is in the comments:

```python
from pyeffect import Effect, Err, Ok, Result, attempt, from_optional

# Expected failure is a value the caller handles.
result: Result[int, str] = attempt(lambda: int("42")).map(lambda n: n * 2)
match result:
    case Ok(value):
        print(value)  # 84
    case Err(error):
        print(f"failed: {error}")

# Absence is a value too.
assert from_optional({"a": 1}.get("b")).unwrap_or(0) == 0

# Side effects are deferred until you run them.
effect = (
    Effect.attempt(lambda: open("config.json").read())
    .map(str.strip)
    .context("while loading config")
    .catch(lambda e: Effect.success("{}"))
)
print(effect.run())  # {} — the read failed, the fallback ran
```

## What's inside

| Module | Types |
|---|---|
| `pyeffect.result` | `Ok` / `Err` / `Result[T, E]`, `attempt`, `guard`, `traverse`, `partition`, `flatten`, `transpose`, `ErrorContext` |
| `pyeffect.option` | `Some` / `Nothing` / `Option[T]`, `from_optional`, `flatten`, `transpose` |
| `pyeffect.do` | `do` — generator-expression do-notation for `Result`/`Option` |
| `pyeffect.effect` | `Effect[T, E]` — a lazy, re-runnable computation; `sequence`, `attempt`, `retry_result`, `do_effect` |
| `pyeffect.retry` | `retry` + `Policy` + `Backoff` — deterministic, injectable backoff (constant/linear/exponential), jitter, and `should_retry` |
| `pyeffect.tagged` | `TaggedError`, `MatchError`, `match_error`, `match_error_partial` |
| `pyeffect.pipe` | `pipe(value, f, g, ...)` — left-to-right threading |
| `pyeffect.compose` | `compose`, `curry`, `lift` / `lift2` / `lift3`, `identity`, `tap`, `flip`, `unpack`, `constant`, `partial` |

The combinators are methods: `Effect` carries `map`, `and_then`, `catch`,
`context`, `inspect`, `inspect_err`, `map_or`, `flatten`, `zip`, and `retry`;
every variant has the eager boolean combinators `and_` / `or_` (trailing
underscore because `and`/`or` are Python keywords), plus `Option.xor`.

`flatten` and `transpose` are module-level functions on `result` and
`option` (`from pyeffect.result import flatten, transpose`) because Python's
invariant generics make the equivalent methods untypeable at call sites.

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
    return match_error(
        error,
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        },
    )
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

## `Effect` is the impurity boundary

Python is eager: every call executes immediately, so purity is lost the
moment you touch IO or time. `Effect` restores it — **constructing and
composing run nothing; `run()` / `run_result()` are the only impure
moments.** Dependencies (readers, clocks, backends) are captured in the
thunk's closure, and `sleep` is injected, so tests run with zero delay and
no real I/O.

The library is **sync-first by design**: the value layer (`Result`,
`Option`, `pipe`, `compose`) is pure and async-agnostic, and `Effect` is a
sync thunk over `Result`. An `AsyncEffect` sibling (awaitable thunks,
`asyncio.sleep`-injected retry) is planned for when network use-cases
demand it — not before.

## Typing notes

Every combinator is checked with [`ty`](https://github.com/astral-sh/ty) as
part of the test suite (`tests/typing/` pins the contracts, including
intentional failures that must stay rejected). Known constraints of Python
generics, documented in the module docstrings:

- **No variance in PEP 695** — `Effect.success` / `Effect.failure` leave the
  unbound slot as `Any`; anchor the chain with an annotation or an operation
  that fixes the slot (`attempt`'s `catch`, `map_err`, `context`).
- **No higher-kinded types** — there are no generic `Functor` / `Monad`
  typeclasses; each type implements `map` / `and_then` structurally.
- **Fixed arity ceilings** — `pipe` / `compose` type-check up to ten
  functions, `curry` up to five; the runtimes accept more.

## Development

```bash
uv run pytest      # runtime + doctest tests
uv run ty check src tests   # typing contract; also gates the tests/typing/ fixtures
uv run ruff check src tests
```
