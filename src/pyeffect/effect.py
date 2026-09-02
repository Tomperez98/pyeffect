# Classic TypeVars are required for the attempt overloads: PEP 695 type
# params on @overload are not checked by ty (ty 0.0.77 silently skips
# overload checking and falls back to the implementation signature).
"""A lazy, fully typed ``Effect``: defer a computation, compose, then run.

An ``Effect[T, E]`` is a *description* of a computation that succeeds with
``T`` or fails with ``E``. Constructing and composing it runs nothing; only
``run``/``run_result`` execute the underlying thunk, so effects are
re-runnable and side effects happen exactly when you run them::

    >>> from pyeffect.effect import Effect
    >>> Effect.success(2).map(lambda x: x * 3).run()
    6
    >>> Effect.attempt(lambda: 1 / 0, catch=lambda e: str(e)).run_result()
    Err(error='division by zero')
    >>> Effect.success(1).zip(Effect.success("a")).run()
    (1, 'a')
    >>> Effect.failure("boom").context("while parsing").run_result()
    Err(error=ErrorContext(message='while parsing', source='boom'))

Dependencies are captured in the thunk's closure — the idiomatic Python
form of dependency injection. ``and_then`` preserves the error type (Python
generics are invariant, so a widened error union cannot be expressed
honestly); combine effects with different failure types via ``map_err`` or
``catch`` first.

Why ``Any`` slots? :meth:`Effect.success` and :meth:`Effect.failure` leave
the *other* slot as ``Any`` rather than ``Never``: under Python's invariant
generics a ``Never`` error slot would refuse to flow into chains whose
error type is fixed later, so ``Effect.success(1).and_then(...)`` would not
type-check at all. The cost is that the unbound slot stays ``Any`` until
the chain is anchored — with an annotation (``effect: Effect[int, str] =
Effect.failure("boom")``) or with an operation that fixes the slot
(:meth:`Effect.attempt`'s ``catch``, ``map_err``, ``catch``). This is the
documented compromise of PEP 695 typing, which has no variance annotations.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator, Iterable, Iterator
from typing import Any, TypeVar, overload

from pyeffect.do import _ShortCircuit
from pyeffect.result import Err, ErrorContext, Ok, Result, attempt
from pyeffect.retry import Policy
from pyeffect.retry import retry as retry_result

__all__ = ["Effect", "do_effect", "sequence"]

_AttemptT = TypeVar("_AttemptT")
_AttemptE = TypeVar("_AttemptE")


class Effect[T, E]:
    """A deferred computation that succeeds with ``T`` or fails with ``E``."""

    __slots__ = ("_thunk",)

    def __init__(self, thunk: Callable[[], Result[T, E]]) -> None:
        self._thunk = thunk

    @staticmethod
    def success[U](value: U) -> Effect[U, Any]:
        """An effect that yields ``value``.

        The error slot is unbound (``Any``) so it composes into chains
        with any error type — under Python's invariant generics a
        ``Never`` error slot would refuse to flow into typed chains.
        """

        return Effect(lambda: Ok(value))

    @staticmethod
    def failure[V](error: V) -> Effect[Any, V]:
        """An effect that fails with ``error``.

        The success slot is unbound (``Any``) — declare it with an
        annotation (``effect: Effect[int, str] = Effect.failure("boom")``)
        and :meth:`catch` recovers with full precision.
        """

        return Effect(lambda: Err(error))

    @overload
    @staticmethod
    def attempt(fn: Callable[[], _AttemptT]) -> Effect[_AttemptT, Exception]: ...
    @overload
    @staticmethod
    def attempt(
        fn: Callable[[], _AttemptT], *, catch: Callable[[Exception], _AttemptE]
    ) -> Effect[_AttemptT, _AttemptE]: ...
    @staticmethod
    def attempt(
        fn: Callable[[], _AttemptT],
        *,
        catch: Callable[[Exception], Any] = lambda e: e,
    ) -> Effect[_AttemptT, Any]:
        """An effect that runs ``fn`` and captures its failure as a value.

        The exception boundary for effects: :func:`pyeffect.result.attempt`
        deferred until ``run``/``run_result``. Only ``Exception`` is
        captured — ``KeyboardInterrupt`` and ``SystemExit`` are
        bugs/interrupts and must propagate (fail fast).
        """

        def thunk() -> Result[_AttemptT, Any]:
            return attempt(fn, catch=catch)

        return Effect(thunk)

    def map[U](self, f: Callable[[T], U]) -> Effect[U, E]:
        """Transform the success value; a failure passes through unchanged."""

        return Effect(lambda: self._thunk().map(f))

    def map_err[E2](self, f: Callable[[E], E2]) -> Effect[T, E2]:
        """Transform the failure value; a success passes through unchanged."""

        return Effect(lambda: self._thunk().map_err(f))

    def inspect(self, f: Callable[[T], object]) -> Effect[T, E]:
        """Run ``f`` on the success value for its side effect, lazily."""

        return Effect(lambda: self._thunk().inspect(f))

    def inspect_err(self, f: Callable[[E], object]) -> Effect[T, E]:
        """Run ``f`` on the failure for its side effect, lazily."""

        return Effect(lambda: self._thunk().inspect_err(f))

    def and_then[U](self, f: Callable[[T], Effect[U, E]]) -> Effect[U, E]:
        """Chain onto the success value; a failure short-circuits."""

        def thunk() -> Result[U, E]:
            return self._thunk().and_then(lambda value: f(value).run_result())

        return Effect(thunk)

    def and_[U](self, other: Effect[U, E]) -> Effect[U, E]:
        """Run ``self``; on success run and return ``other`` (the eager ``and``)."""

        return self.and_then(lambda _: other)

    def flatten[U](self: Effect[Effect[U, E], E]) -> Effect[U, E]:
        """Collapse a nested effect: running it runs the inner effect."""

        def thunk() -> Result[U, E]:
            outer = self._thunk()
            if isinstance(outer, Ok):
                return outer.value.run_result()
            return outer

        return Effect(thunk)

    def zip[U](self, other: Effect[U, E]) -> Effect[tuple[T, U], E]:
        """Pair this effect's value with ``other``'s; fail fast on the first error.

        Nothing runs at construction. When the result is run, the thunks
        execute left to right, and the second is skipped entirely if the
        first fails.
        """

        def thunk() -> Result[tuple[T, U], E]:
            first = self._thunk()
            if isinstance(first, Ok):
                second = other._thunk()
                if isinstance(second, Ok):
                    return Ok((first.value, second.value))
                return second
            return first

        return Effect(thunk)

    def map2[U, R](self, other: Effect[U, E], f: Callable[[T, U], R]) -> Effect[R, E]:
        """Apply ``f`` to this effect's value and ``other``'s; fail fast.

        ``a.map2(b, f)`` is ``a.zip(b).map(unpack(f))``, deferred and lazy.
        """

        def thunk() -> Result[R, E]:
            first = self._thunk()
            if isinstance(first, Ok):
                second = other._thunk()
                if isinstance(second, Ok):
                    return Ok(f(first.value, second.value))
                return second
            return first

        return Effect(thunk)

    def catch[E2](self, f: Callable[[E], Effect[T, E2]]) -> Effect[T, E2]:
        """Recover from failure; a success passes through unchanged."""

        def thunk() -> Result[T, E2]:
            return self._thunk().or_else(lambda error: f(error).run_result())

        return Effect(thunk)

    def or_[F](self, other: Effect[T, F]) -> Effect[T, F]:
        """Run ``self``; on failure run and return ``other`` (the eager ``or``)."""

        return self.catch(lambda _: other)

    def map_or[R](self, default: R, f: Callable[[T], R]) -> Effect[R, E]:
        """Apply ``f`` to the value, or yield ``default`` on failure."""

        return Effect(lambda: Ok(self._thunk().map_or(default, f)))

    def map_or_else[R](
        self, default: Callable[[E], R], f: Callable[[T], R]
    ) -> Effect[R, E]:
        """Apply ``f`` to the value, or ``default(error)`` on failure."""

        return Effect(lambda: Ok(self._thunk().map_or_else(default, f)))

    def context(self, message: str) -> Effect[T, ErrorContext]:
        """Attach context to the failure; a success passes through unchanged.

        Mirrors :meth:`pyeffect.result.Result.context` — the error slot
        becomes an :class:`~pyeffect.result.ErrorContext` carrying the
        message and the original error.
        """

        return Effect(lambda: self._thunk().context(message))

    def with_context(self, f: Callable[[E], str]) -> Effect[T, ErrorContext]:
        """Like :meth:`context`, but the message is computed lazily on failure."""

        return Effect(lambda: self._thunk().with_context(f))

    def retry(
        self,
        policy: Policy,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Effect[T, E]:
        """Re-run this effect's thunk according to ``policy``."""

        def thunk() -> Result[T, E]:
            return retry_result(lambda _attempt: self._thunk(), policy, sleep=sleep)

        return Effect(thunk)

    def run_result(self) -> Result[T, E]:
        """Execute the effect and return its :data:`Result`."""

        return self._thunk()

    def run(self) -> T:
        """Execute the effect and return the value.

        Panics with :class:`~pyeffect.result.UnwrapError` on failure — the
        caller chose the fail-fast edge. Use :meth:`run_result` or
        :meth:`catch` to handle failure as a value.
        """

        return self._thunk().unwrap()

    def __iter__(self) -> Iterator[T]:
        """Run the effect and yield its value (do-notation support).

        Iterating an effect executes its thunk — but only when the
        enclosing ``do_effect`` thunk runs, so laziness is preserved. A
        failure raises :class:`_ShortCircuit`.
        """

        result = self.run_result()
        match result:
            case Ok():
                yield result.value
            case Err():
                raise _ShortCircuit(result)


def sequence[T, E](effects: Iterable[Effect[T, E]]) -> Effect[list[T], E]:
    """Run a list of effects in order; fail fast on the first failure.

    The effects are materialized up front, so the resulting effect is
    re-runnable even when given a generator.
    """

    materialized = list(effects)

    def thunk() -> Result[list[T], E]:
        values: list[T] = []
        for effect in materialized:
            result = effect.run_result()
            if isinstance(result, Ok):
                values.append(result.value)
            else:
                return result
        return Ok(values)

    return Effect(thunk)


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
