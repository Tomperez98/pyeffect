# pyeffect

Handle expected failures as values. Bugs panic.

A zero-dependency, fully-typed functional core for Python 3.12+ — `Result`
and `Option` for data, a lazy `Effect` for side effects, with retry and
serialization built in.

```python
from pyeffect import Err, Ok, Result, attempt

result: Result[int, str] = attempt(lambda: int("42"), catch=lambda e: str(e)).map(lambda n: n * 2)
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
  `unwrap()` on `Err`/`Nothing`, a broken retry `Policy`, a non-exhaustive
  `match_error`, an over-arity `curry`. Every defect raises the same type —
  `Panic` (with `UnwrapError` / `UnwrapNothingError` / `MatchError` as
  precise subtypes) — so a defect boundary catches `Panic` and reports the
  bug. The damage stops at the exact line.
- **Return a value** when failure is expected — network errors, bad input,
  absence. The caller decides what to do with it.

## Why pyeffect

- **One rule, two outcomes.** `Err` is a value the caller handles; a broken
  invariant raises a single `Panic` type — no `except Exception` guessing.
- **Zero dependencies, sync-first.** `Result`/`Option` are plain unions,
  `Effect` is a thunk. No higher-kinded-type machinery; async stays out
  until you need it.
- **Checked by `ty` in CI.** Every combinator's type signature is pinned by
  fixtures; a wrong type fails the build.

## Install

```bash
pip install pyeffect
```

Requires Python 3.12+. To develop against the source instead:

```bash
uv sync   # installs pyeffect + dev deps (pytest, ruff, ty) into .venv
```

## A complete example

Paste this and it runs — expected output is in the comments:

```python
from pyeffect import Effect, Err, Ok, Result, attempt, from_optional

# Expected failure is a value the caller handles.
result: Result[int, str] = attempt(lambda: int("42"), catch=lambda e: str(e)).map(lambda n: n * 2)
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
| `pyeffect.result` | `Ok` / `Err` / `Result[T, E]`, `attempt`, `guard`, `traverse`, `partition`, `flatten`, `transpose`, `recover`, `is_ok` / `is_err`, `ErrorContext` |
| `pyeffect.option` | `Some` / `Nothing` / `Option[T]`, `from_optional`, `flatten`, `transpose` |
| `pyeffect.do` | `do` — generator-expression do-notation for `Result`/`Option` |
| `pyeffect.effect` | `Effect[T, E]` — a lazy, re-runnable computation; `sequence`, `do_effect` |
| `pyeffect.retry` | `retry` + `Policy` + `Backoff` — deterministic, injectable backoff (constant/linear/exponential), jitter, dynamic `delay`, and `should_retry` |
| `pyeffect.tagged` | `TaggedError`, `UnhandledException`, `MatchError`, `match_error`, `match_error_partial`, `error.match()` |
| `pyeffect.panic` | `Panic`, `panic`, `is_panic` — the unified defect type |
| `pyeffect.codec` | `Codec`, `from_dict`, `ResultSerializationError`, `ResultDeserializationError` |
| `pyeffect.pipe` | `pipe(value, f, g, ...)` — left-to-right threading |
| `pyeffect.compose` | `compose`, `curry`, `lift` / `lift2` / `lift3`, `identity`, `tap`, `flip`, `unpack`, `constant`, `partial` |

The combinators are methods on each variant — `map`, `map_err`, `and_then`,
`or_else`, `inspect`, `inspect_err`, `inspect_both`, `fold`, `unwrap` /
`expect` / `unwrap_or` / `unwrap_or_else`, `zip`, `map2`, `contains`,
`map_or` / `map_or_else`, and `context` / `with_context` — with eager
`and_` / `or_` (trailing underscore because `and`/`or` are Python keywords)
and `Option.xor`. `Effect` mirrors them lazily and adds `retry`.

`flatten` and `transpose` are module-level functions on `result` and
`option`, and `recover` on `result` (`from pyeffect.result import flatten,
transpose, recover`) — Python's invariant generics make the equivalent
methods untypeable at call sites. `Effect.flatten` and `Effect.recover` are
methods instead, since `Effect` is a single class rather than a union.

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

The tag defaults to the class name when omitted; `tag`, `.is_()`,
`to_dict()`, and `error.match(...)` (the instance spelling of `match_error`)
are always available. Unknown exceptions are wrapped in `UnhandledException`
by `attempt`/`guard` unless a `catch` translator is supplied.

## Recovery and serialization

`recover` is `or_else` generalized: it may return a *different* success type,
widening the result to `T | U`:

```python
from pyeffect import Err, Ok, recover

assert recover(Err("boom"), lambda e: Ok(len(e))) == Ok(4)
assert recover(Ok(5), lambda e: Ok("guest")) == Ok(5)
```

Every `Result` carries a serializable `status` discriminant (`"ok"` /
`"error"`) and a `to_dict()` wire envelope; `from_dict` decodes it back:

```python
from pyeffect import Err, Ok, from_dict

assert Ok(5).to_dict() == {"status": "ok", "value": 5}
assert from_dict({"status": "error", "error": "boom"}) == Err("boom")
```

A pluggable `Codec` (`pyeffect.codec`) validates payloads in both
directions with safe (`Result`-returning) and unsafe (`Panic`-raising)
variants — see its module docstring.

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
