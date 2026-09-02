# ruff: noqa: UP047 -- PEP 695 type params on @overload are not checked by ty;
# classic TypeVars required for attempt/guard. Classes and methods use PEP 695.
"""A minimal, fully typed ``Result``: ``Ok``/``Err`` with fail-fast unwrapping.

``Result[T, E]`` is the union ``Ok[T] | Err[E]``. It is the value-carrying
form of *expected* failure — a caller receives a ``Result`` and decides what
to do with it, instead of catching an exception::

    >>> from pyeffect.result import Ok, Err, attempt, traverse
    >>> Ok(1).map(lambda x: x + 1)
    Ok(value=2)
    >>> attempt(lambda: 1 / 0, catch=lambda e: str(e))
    Err(error='division by zero')
    >>> Ok(1).ok()
    Some(value=1)
    >>> Err("boom").err()
    Some(value='boom')
    >>> Ok(1).fold(lambda v: v * 2, lambda e: 0)
    2
    >>> Ok(1).map_or(0, lambda v: v * 2)
    2
    >>> Ok(1).zip(Ok("a"))
    Ok(value=(1, 'a'))
    >>> traverse(lambda x: Ok(x * 2) if x > 0 else Err("neg"), [1, 2])
    Ok(value=[2, 4])
    >>> traverse(lambda x: Ok(x * 2) if x > 0 else Err("neg"), [1, -2])
    Err(error='neg')
    >>> Err("boom").context("while parsing")
    Err(error=ErrorContext(message='while parsing', source='boom'))

Unwrapping is the fail-fast edge: ``unwrap()``/``expect()`` on an ``Err``
raise :class:`UnwrapError`, because treating a failure as a success is a
bug, not an expected outcome.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import wraps
from typing import (
    Any,
    ClassVar,
    NoReturn,
    ParamSpec,
    TypeGuard,
    TypeVar,
    cast,
    overload,
)

from pyeffect.do import _ShortCircuit
from pyeffect.option import Nothing, Option, Some
from pyeffect.panic import Panic
from pyeffect.tagged import UnhandledException

__all__ = [
    "Err",
    "ErrorContext",
    "Ok",
    "Result",
    "UnwrapError",
    "attempt",
    "flatten",
    "guard",
    "is_err",
    "is_ok",
    "partition",
    "recover",
    "transpose",
    "traverse",
]

_P = ParamSpec("_P")
_T = TypeVar("_T")
_T2 = TypeVar("_T2")


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


@dataclass(frozen=True, slots=True)
class ErrorContext:
    """A message attached to a failure, preserving the original error.

    ``context``/``with_context`` swap the error slot for an
    :class:`ErrorContext` so a pipeline can say *what it was doing* when
    it failed — without losing the underlying cause, which stays reachable
    as :attr:`source`. Repeated calls nest: each new message wraps the
    previous context.
    """

    message: str
    source: object


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """The success variant of :data:`Result`, carrying a ``value``."""

    value: T
    status: ClassVar[str] = "ok"

    __match_args__ = ("value",)

    def __iter__(self) -> Iterator[T]:
        """Yield the value so ``for x in ok`` binds ``x`` in do-notation.

        ``Ok`` is iterable so ``do(... for x in result)`` can unwrap it;
        the loop variable's type is ``T``.
        """

        yield self.value

    def map[U, E](self, f: Callable[[T], U]) -> Result[U, E]:
        return Ok(f(self.value))

    def and_then[U, E](self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return f(self.value)

    def and_[U, E](self, other: Result[U, E]) -> Result[U, E]:
        """Return ``other``, discarding this value.

        The eager cousin of :meth:`and_then`: ``Ok(v).and_(other)`` is
        ``other``. Both results share one error type ``E``.
        """

        return other

    def map_err[F, E](self, f: Callable[[E], F]) -> Result[T, F]:
        return Ok(self.value)

    def or_else[F, E](self, f: Callable[[E], Result[T, F]]) -> Result[T, F]:
        return Ok(self.value)

    def or_[F](self, other: Result[T, F]) -> Result[T, F]:
        """Return this ``Ok`` unchanged, ignoring ``other``.

        The eager cousin of :meth:`or_else`. The error type may differ
        (``F``), because an ``Ok`` produces no error.
        """

        return self

    def unwrap(self) -> T:
        return self.value

    def expect(self, message: str) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def unwrap_or_else[E](self, f: Callable[[E], T]) -> T:
        return self.value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def ok(self) -> Option[T]:
        """The value as an :class:`~pyeffect.option.Option`.

        ``Ok(v).ok()`` is ``Some(v)``; the error slot is dropped.
        """

        return Some(self.value)

    def err[E](self) -> Option[E]:
        """The error as an :class:`~pyeffect.option.Option` — always ``Nothing``.

        The inverse of :meth:`ok`; the error slot is unbound on ``Ok``.
        """

        return Nothing()

    def fold[R](self, on_ok: Callable[[T], R], on_err: Callable[..., R]) -> R:
        """Handle both branches in one expression; ``Ok`` takes ``on_ok``.

        ``r.fold(on_ok, on_err)`` is the catamorphism — the single call
        that covers both variants, like a ``match`` that returns a value.

        ``on_err`` is typed ``Callable[..., R]`` because an ``Ok`` cannot
        name the error type that handler would receive; the unused branch
        is deliberately loose.
        """

        return on_ok(self.value)

    def inspect[E](self, f: Callable[[T], object]) -> Result[T, E]:
        """Run ``f`` on the value for its side effect; pass the result through.

        The ``tap`` equivalent for ``Ok`` — the value is returned unchanged.
        """

        f(self.value)
        return self

    def inspect_err[E](self, f: Callable[..., object]) -> Result[T, E]:
        """Never called on ``Ok``; the result passes through unchanged."""

        return self

    def inspect_both[E](
        self, on_ok: Callable[[T], object], on_err: Callable[..., object]
    ) -> Result[T, E]:
        """Run ``on_ok`` for its side effect; pass the result through.

        The two-branch ``tap``: observe either outcome in one call. On an
        ``Ok``, only ``on_ok`` runs.
        """

        on_ok(self.value)
        return self

    def contains(self, value: object) -> bool:
        """Whether the carried value equals ``value``."""

        return self.value == value

    def map_or[R](self, default: R, f: Callable[[T], R]) -> R:
        """Apply ``f`` to the value, or yield ``default`` on error."""

        return f(self.value)

    def map_or_else[R, E](self, default: Callable[..., R], f: Callable[[T], R]) -> R:
        """Apply ``f`` to the value, or ``default(error)`` on error."""

        return f(self.value)

    def zip[U, E](self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        """Pair this value with ``other``'s; short-circuit on the first error."""

        return other.map(lambda u: (self.value, u))

    def map2[U, R, E](
        self, other: Result[U, E], f: Callable[[T, U], R]
    ) -> Result[R, E]:
        """Apply ``f`` to this value and ``other``'s; short-circuit on error."""

        return other.map(lambda u: f(self.value, u))

    def context(self, message: str) -> Result[T, ErrorContext]:
        """Attach context to a failure; ``Ok`` passes through unchanged.

        ``r.context("while parsing")`` makes the error slot an
        :class:`ErrorContext` — the message plus the original error.
        """

        return self

    def with_context(self, f: Callable[..., str]) -> Result[T, ErrorContext]:
        """Like :meth:`context`, but the message is computed lazily on failure.

        The callback never runs on ``Ok``.
        """

        return self

    def to_dict(self) -> dict[str, object]:
        """The wire envelope ``{"status": "ok", "value": ...}``."""

        return {"status": self.status, "value": self.value}


@dataclass(frozen=True, slots=True)
class Err[E]:
    """The failure variant of :data:`Result`, carrying an ``error``."""

    error: E
    status: ClassVar[str] = "error"

    __match_args__ = ("error",)

    def __iter__(self) -> Iterator[NoReturn]:
        """Raise :class:`_ShortCircuit` when advanced — never yields.

        Makes do-notation short-circuit: iterating an ``Err`` raises the
        private control-flow signal that :func:`pyeffect.do.do` catches.
        """

        def _iter() -> Iterator[NoReturn]:
            raise _ShortCircuit(self)
            yield  # pragma: no cover -- unreachable, makes _iter a generator

        return _iter()

    def map[U, T](self, f: Callable[[T], U]) -> Result[U, E]:
        return Err(self.error)

    def and_then[U, T](self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return Err(self.error)

    def and_[U](self, other: Result[U, E]) -> Result[U, E]:
        """Return ``self`` unchanged, discarding ``other``.

        The eager cousin of :meth:`and_then`; an ``Err`` short-circuits.
        """

        return self

    def map_err[F, T](self, f: Callable[[E], F]) -> Result[T, F]:
        return Err(f(self.error))

    def or_else[F, T](self, f: Callable[[E], Result[T, F]]) -> Result[T, F]:
        return f(self.error)

    def or_[T, F](self, other: Result[T, F]) -> Result[T, F]:
        """Return ``other``, discarding this error.

        The eager cousin of :meth:`or_else`; the error type may differ.
        """

        return other

    def unwrap(self) -> NoReturn:
        raise UnwrapError(self.error)

    def expect(self, message: str) -> NoReturn:
        raise UnwrapError(self.error, context=message)

    def unwrap_or[T](self, default: T) -> T:
        return default

    def unwrap_or_else[T](self, f: Callable[[E], T]) -> T:
        return f(self.error)

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def ok[T](self) -> Option[T]:
        """The value as an :class:`~pyeffect.option.Option` — always ``Nothing``.

        The success slot is unbound on ``Err``.
        """

        return Nothing()

    def err(self) -> Option[E]:
        """The error as an :class:`~pyeffect.option.Option`.

        ``Err(e).err()`` is ``Some(e)``.
        """

        return Some(self.error)

    def fold[R](self, on_ok: Callable[..., R], on_err: Callable[[E], R]) -> R:
        """Handle both branches in one expression; ``Err`` takes ``on_err``.

        ``on_ok`` is typed ``Callable[..., R]`` because an ``Err`` cannot
        name the value type that handler would receive; the unused branch
        is deliberately loose.
        """

        return on_err(self.error)

    def inspect[T](self, f: Callable[..., object]) -> Result[T, E]:
        """Never called on ``Err``; the result passes through unchanged."""

        return self

    def inspect_err[T](self, f: Callable[[E], object]) -> Result[T, E]:
        """Run ``f`` on the error for its side effect; pass the result through.

        The ``tap`` equivalent for ``Err``.
        """

        f(self.error)
        return self

    def inspect_both[T](
        self, on_ok: Callable[..., object], on_err: Callable[[E], object]
    ) -> Result[T, E]:
        """Run ``on_err`` for its side effect; pass the result through.

        The two-branch ``tap``: observe either outcome in one call. On an
        ``Err``, only ``on_err`` runs.
        """

        on_err(self.error)
        return self

    def contains(self, value: object) -> bool:
        """Whether the carried value equals ``value`` — always ``False``."""

        return False

    def map_or[R, T](self, default: R, f: Callable[..., R]) -> R:
        """Apply ``f`` to the value, or yield ``default`` on error."""

        return default

    def map_or_else[R, T](self, default: Callable[[E], R], f: Callable[..., R]) -> R:
        """Apply ``f`` to the value, or ``default(error)`` on error."""

        return default(self.error)

    def zip[U, T](self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        """Pair this value with ``other``'s; short-circuit on the first error."""

        return self

    def map2[U, R, T](self, other: Result[U, E], f: Callable[..., R]) -> Result[R, E]:
        """Apply ``f`` to this value and ``other``'s; short-circuit on error."""

        return self

    def context[T](self, message: str) -> Result[T, ErrorContext]:
        """Attach context to this failure, preserving the original error."""

        return Err(ErrorContext(message, self.error))

    def with_context[T](self, f: Callable[[E], str]) -> Result[T, ErrorContext]:
        """Like :meth:`context`, but the message is computed lazily on failure."""

        return Err(ErrorContext(f(self.error), self.error))

    def to_dict(self) -> dict[str, object]:
        """The wire envelope ``{"status": "error", "error": ...}``."""

        return {"status": self.status, "error": self.error}


# Note: ``Result`` is a typing union (Ok[T] | Err[E]), not a runtime class.
# ``isinstance(x, Result)`` raises TypeError — use ``match``, ``is_ok()``,
# or ``isinstance(x, (Ok, Err))`` instead.
type Result[T, E] = Ok[T] | Err[E]


def is_ok[T](result: Result[T, Any]) -> TypeGuard[Ok[T]]:
    """Narrow a ``Result`` to :class:`Ok` inside an ``if`` (a type guard).

    The boolean method ``.is_ok()`` does not narrow; this function does, the
    Python analogue of better-result's ``Result.isOk`` type predicate.
    """

    return isinstance(result, Ok)


def is_err[E](result: Result[Any, E]) -> TypeGuard[Err[E]]:
    """Narrow a ``Result`` to :class:`Err` inside an ``if`` (a type guard)."""

    return isinstance(result, Err)


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


def traverse[T, U, E](
    f: Callable[[T], Result[U, E]], values: Iterable[T]
) -> Result[list[U], E]:
    """Map ``f`` over ``values``; collect successes or short-circuit on ``Err``.

    ``traverse`` is the applicative way to run a fallible function over a
    sequence: every element must succeed, and the first failure wins (fail
    fast — later elements are not evaluated).
    """
    successes: list[U] = []
    for value in values:
        result = f(value)
        if isinstance(result, Ok):
            successes.append(result.value)
        else:
            return result
    return Ok(successes)


def flatten[T, E](result: Result[Result[T, E], E]) -> Result[T, E]:
    """Collapse a nested result: ``Ok(Ok(x))`` is ``Ok(x)``.

    ``Ok(Err(e))`` surfaces the inner failure as the outer one; ``Err(e)``
    passes through unchanged. The nesting is expressed in the type —
    ``flatten`` is not callable on a non-nested ``Result``.

    >>> from pyeffect.result import Ok, Err, flatten
    >>> flatten(Ok(Ok(1)))
    Ok(value=1)
    >>> flatten(Ok(Err("boom")))
    Err(error='boom')
    >>> flatten(Err("boom"))
    Err(error='boom')
    """

    match result:
        case Ok(inner):
            return inner
        case Err(_):
            return result


def transpose[T, E](result: Result[Option[T], E]) -> Option[Result[T, E]]:
    """Swap the nesting: ``Result<Option<T>, E>`` to ``Option<Result<T, E>>``.

    ``Ok(Some(x))`` is ``Some(Ok(x))``, ``Ok(Nothing())`` is ``Nothing()``,
    and ``Err(e)`` is ``Some(Err(e))``.

    >>> from pyeffect.result import Ok, Err, transpose
    >>> from pyeffect.option import Some, Nothing
    >>> transpose(Ok(Some(1)))
    Some(value=Ok(value=1))
    >>> transpose(Ok(Nothing()))
    Nothing()
    >>> transpose(Err("boom"))
    Some(value=Err(error='boom'))
    """

    if isinstance(result, Err):
        # ``Err[E]`` is a member of the ``Result[T, E]`` union, but invariant
        # generics cannot widen it back to the union once ``isinstance`` has
        # narrowed it — so re-assert the union type for ``Some``'s slot.
        return Some(cast(Result[T, E], result))
    opt = result.value  # Option[T]
    if isinstance(opt, Some):
        return Some(cast(Result[T, E], Ok(opt.value)))
    return Nothing()


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
    """

    match result:
        case Ok():
            # Ok[T] is a member of Ok[T | U] | Err[F]; invariant generics
            # cannot widen it, so re-assert the union type (see transpose).
            return cast(Result[T | U, F], result)
        case Err():
            return cast(Result[T | U, F], f(result.error))


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
        match result:
            case Ok():
                values.append(result.value)
            case Err():
                errors.append(result.error)
    return values, errors
