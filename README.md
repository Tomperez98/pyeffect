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
| `pyeffect.result` | `Ok` / `Err` / `Result[T, E]`, `attempt`, `guard`, `traverse`, `flatten`, `transpose`, `ErrorContext` |
| `pyeffect.option` | `Some` / `Nothing` / `Option[T]`, `from_optional`, `flatten`, `transpose` |
| `pyeffect.effect` | `Effect[T, E]` — a lazy, re-runnable computation; `sequence`, `attempt`, `retry_result` |
| `pyeffect.retry` | `retry` + `Policy` — deterministic, injectable backoff |
| `pyeffect.pipe` | `pipe(value, f, g, ...)` — left-to-right threading |
| `pyeffect.compose` | `compose`, `curry`, `lift` / `lift2` / `lift3`, `identity`, `tap`, `flip`, `unpack`, `constant`, `partial` |

The combinators are methods: `Effect` carries `map`, `and_then`, `catch`,
`context`, `inspect`, `inspect_err`, `map_or`, `flatten`, `zip`, and `retry`;
every variant has the eager boolean combinators `and_` / `or_` (trailing
underscore because `and`/`or` are Python keywords), plus `Option.xor`.

`flatten` and `transpose` are module-level functions on `result` and
`option` (`from pyeffect.result import flatten, transpose`) because Python's
invariant generics make the equivalent methods untypeable at call sites.

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
