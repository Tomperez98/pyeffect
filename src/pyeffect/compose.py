# ruff: noqa: UP047 -- PEP 695 type params on @overload are not checked by ty;
# classic TypeVars required. Non-overload functions below use PEP 695.
"""Function composition: ``compose``, ``tap``, and small combinators.

``compose`` builds a new function from existing ones, right to left::

    >>> from pyeffect.compose import compose
    >>> compose(str, lambda x: x + 1)(2)
    '3'

``tap`` runs a side effect on a value and passes it through unchanged — a
convenient debug step inside a ``pipe``.

``curry`` turns a multi-argument function into nested single-argument
calls; ``lift``/``lift2``/``lift3`` push plain functions into the
``Result`` domain::

    >>> from pyeffect.compose import curry, lift2
    >>> from pyeffect.result import Ok
    >>> curry(lambda a, b: a + b)(2)(3)
    5
    >>> lift2(lambda a, b: a + b)(Ok(1), Ok(2))
    Ok(value=3)
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar, overload

from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result

__all__ = [
    "compose",
    "constant",
    "curry",
    "flip",
    "identity",
    "lift",
    "lift2",
    "lift3",
    "partial",
    "tap",
    "unpack",
]

_A = TypeVar("_A")
_B = TypeVar("_B")
_C = TypeVar("_C")
_D = TypeVar("_D")
_E = TypeVar("_E")
_F = TypeVar("_F")
_G = TypeVar("_G")
_H = TypeVar("_H")
_I = TypeVar("_I")
_J = TypeVar("_J")
_K = TypeVar("_K")


@overload
def compose() -> Callable[[_A], _A]: ...
@overload
def compose(f: Callable[[_A], _B]) -> Callable[[_A], _B]: ...
@overload
def compose(f: Callable[[_A], _B], g: Callable[[_C], _A]) -> Callable[[_C], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
) -> Callable[[_D], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
    i: Callable[[_E], _D],
) -> Callable[[_E], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
    i: Callable[[_E], _D],
    j: Callable[[_F], _E],
) -> Callable[[_F], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
    i: Callable[[_E], _D],
    j: Callable[[_F], _E],
    k: Callable[[_G], _F],
) -> Callable[[_G], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
    i: Callable[[_E], _D],
    j: Callable[[_F], _E],
    k: Callable[[_G], _F],
    l: Callable[[_H], _G],
) -> Callable[[_H], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
    i: Callable[[_E], _D],
    j: Callable[[_F], _E],
    k: Callable[[_G], _F],
    l: Callable[[_H], _G],
    m: Callable[[_I], _H],
) -> Callable[[_I], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
    i: Callable[[_E], _D],
    j: Callable[[_F], _E],
    k: Callable[[_G], _F],
    l: Callable[[_H], _G],
    m: Callable[[_I], _H],
    n: Callable[[_J], _I],
) -> Callable[[_J], _B]: ...
@overload
def compose(
    f: Callable[[_A], _B],
    g: Callable[[_C], _A],
    h: Callable[[_D], _C],
    i: Callable[[_E], _D],
    j: Callable[[_F], _E],
    k: Callable[[_G], _F],
    l: Callable[[_H], _G],
    m: Callable[[_I], _H],
    n: Callable[[_J], _I],
    o: Callable[[_K], _J],
) -> Callable[[_K], _B]: ...
def compose(*functions: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Compose functions right to left: ``compose(f, g)(x) == f(g(x))``.

    ``compose()`` (no functions) is the identity function. Up to ten
    functions are fully type-checked; the runtime accepts any number.
    """
    if not functions:
        return identity

    def composed(value: Any) -> Any:
        for fn in reversed(functions):
            value = fn(value)
        return value

    return composed


def identity[A](value: A) -> A:
    """Return ``value`` unchanged."""

    return value


def tap[A](fn: Callable[[A], object]) -> Callable[[A], A]:
    """Return a function that runs ``fn`` on the value, then returns it.

    The return value of ``fn`` is discarded — ``tap`` is for side effects
    (logging, recording) inside a pipeline.
    """

    def tapped(value: A) -> A:
        fn(value)
        return value

    return tapped


def constant[A](value: A) -> Callable[..., A]:
    """Return a function that ignores its arguments and yields ``value``."""

    def const(*args: object, **kwargs: object) -> A:
        return value

    return const


def flip[A, B, C](f: Callable[[A, B], C]) -> Callable[[B, A], C]:
    """Swap the first two arguments of a binary function."""

    def flipped(b: B, a: A) -> C:
        return f(a, b)

    return flipped


@overload
def unpack[A, R](f: Callable[[A], R]) -> Callable[[tuple[A]], R]: ...
@overload
def unpack[A, B, R](f: Callable[[A, B], R]) -> Callable[[tuple[A, B]], R]: ...
@overload
def unpack[A, B, C, R](f: Callable[[A, B, C], R]) -> Callable[[tuple[A, B, C]], R]: ...
def unpack(f: Callable[..., Any]) -> Callable[[tuple[Any, ...]], Any]:
    """Return a function that applies ``f`` to the elements of a tuple.

    ``unpack(f)((1, 2))`` is ``f(1, 2)``. Arities 1-3 are fully
    type-checked; the runtime accepts any arity.
    """

    def applied(args: tuple[Any, ...]) -> Any:
        return f(*args)

    return applied


def _positional_arity(f: Callable[..., Any]) -> int:
    """Count the fixed positional parameters of ``f``.

    Currying must know when a call has supplied every positional argument.
    A ``*args`` parameter makes that unknowable, and a required
    keyword-only parameter can never be supplied positionally — both are
    defects and crash at construction instead of misbehaving at call time.
    """
    parameters = inspect.signature(f).parameters.values()
    for parameter in parameters:
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
    return sum(
        1
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )


@overload
def curry[R](f: Callable[[], R]) -> Callable[[], R]: ...
@overload
def curry[A, R](f: Callable[[A], R]) -> Callable[[A], R]: ...
@overload
def curry[A, B, R](
    f: Callable[[A, B], R],
) -> Callable[[A], Callable[[B], R]]: ...
@overload
def curry[A, B, C, R](
    f: Callable[[A, B, C], R],
) -> Callable[[A], Callable[[B], Callable[[C], R]]]: ...
@overload
def curry[A, B, C, D, R](
    f: Callable[[A, B, C, D], R],
) -> Callable[[A], Callable[[B], Callable[[C], Callable[[D], R]]]]: ...
@overload
def curry[A, B, C, D, E, R](
    f: Callable[[A, B, C, D, E], R],
) -> Callable[[A], Callable[[B], Callable[[C], Callable[[D], Callable[[E], R]]]]]: ...
def curry(f: Callable[..., Any]) -> Callable[..., Any]:
    """Curry ``f`` so each step supplies one positional argument.

    ``curry(f)(a)(b)(c)`` is ``f(a, b, c)``; a step may also supply
    several arguments at once (``curry(f)(a, b)(c)``), and the step that
    completes the arity runs ``f`` immediately. Arities 1-5 are fully
    type-checked; the runtime accepts any fixed arity. Variadic ``*args``
    callables and required keyword-only parameters are rejected at
    construction — the arity is unknowable or unreachable positionally.
    """
    arity = _positional_arity(f)

    def curried(*args: Any) -> Any:
        if len(args) >= arity:
            return f(*args)
        return curry(partial(f, *args))

    return curried


def lift[T, U, E](
    f: Callable[[T], U],
) -> Callable[[Result[T, E]], Result[U, E]]:
    """Lift a unary function into the ``Result`` domain.

    ``lift(f)(r)`` is ``r.map(f)`` as a reusable value — useful when the
    function must be passed somewhere instead of called on a receiver.
    """

    def lifted(result: Result[T, E]) -> Result[U, E]:
        if isinstance(result, Ok):
            return Ok(f(result.value))
        if isinstance(result, Err):
            return result
        raise Panic(f"lift expected a Result, got {type(result).__name__}")

    return lifted


def lift2[T, U, R, E](
    f: Callable[[T, U], R],
) -> Callable[[Result[T, E], Result[U, E]], Result[R, E]]:
    """Lift a binary function into the ``Result`` domain (applicative style).

    ``lift2(f)(r1, r2)`` applies ``f`` to both values, failing fast on the
    first ``Err``.
    """

    def lifted(first: Result[T, E], second: Result[U, E]) -> Result[R, E]:
        if isinstance(first, Ok) and isinstance(second, Ok):
            return Ok(f(first.value, second.value))
        if isinstance(first, Err):
            return first
        if isinstance(second, Err):
            return second
        raise Panic(
            f"lift2 expected Results, got {type(first).__name__} and "
            f"{type(second).__name__}"
        )

    return lifted


def lift3[T, U, V, R, E](
    f: Callable[[T, U, V], R],
) -> Callable[[Result[T, E], Result[U, E], Result[V, E]], Result[R, E]]:
    """Lift a ternary function into the ``Result`` domain (applicative style).

    ``lift3(f)(r1, r2, r3)`` applies ``f`` to all three values, failing
    fast on the first ``Err``.
    """

    def lifted(
        first: Result[T, E], second: Result[U, E], third: Result[V, E]
    ) -> Result[R, E]:
        if isinstance(first, Ok) and isinstance(second, Ok) and isinstance(third, Ok):
            return Ok(f(first.value, second.value, third.value))
        if isinstance(first, Err):
            return first
        if isinstance(second, Err):
            return second
        if isinstance(third, Err):
            return third
        raise Panic(
            f"lift3 expected Results, got {type(first).__name__}, "
            f"{type(second).__name__} and {type(third).__name__}"
        )

    return lifted
