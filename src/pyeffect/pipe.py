# ruff: noqa: UP047 -- PEP 695 type params on @overload are not checked by ty
# (ty 0.0.77 silently skips overload checking and falls back to the
# implementation signature). Classic TypeVar overloads are checked strictly.
"""Function composition helpers.

``pipe`` threads a value through a sequence of functions left to right::

    >>> from pyeffect.pipe import pipe
    >>> pipe(5, lambda x: x + 1, str, len)
    1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["pipe"]

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
def pipe(value: _A) -> _A: ...
@overload
def pipe(value: _A, f: Callable[[_A], _B]) -> _B: ...
@overload
def pipe(value: _A, f: Callable[[_A], _B], g: Callable[[_B], _C]) -> _C: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
) -> _D: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
    i: Callable[[_D], _E],
) -> _E: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
    i: Callable[[_D], _E],
    j: Callable[[_E], _F],
) -> _F: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
    i: Callable[[_D], _E],
    j: Callable[[_E], _F],
    k: Callable[[_F], _G],
) -> _G: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
    i: Callable[[_D], _E],
    j: Callable[[_E], _F],
    k: Callable[[_F], _G],
    l: Callable[[_G], _H],
) -> _H: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
    i: Callable[[_D], _E],
    j: Callable[[_E], _F],
    k: Callable[[_F], _G],
    l: Callable[[_G], _H],
    m: Callable[[_H], _I],
) -> _I: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
    i: Callable[[_D], _E],
    j: Callable[[_E], _F],
    k: Callable[[_F], _G],
    l: Callable[[_G], _H],
    m: Callable[[_H], _I],
    n: Callable[[_I], _J],
) -> _J: ...
@overload
def pipe(
    value: _A,
    f: Callable[[_A], _B],
    g: Callable[[_B], _C],
    h: Callable[[_C], _D],
    i: Callable[[_D], _E],
    j: Callable[[_E], _F],
    k: Callable[[_F], _G],
    l: Callable[[_G], _H],
    m: Callable[[_H], _I],
    n: Callable[[_I], _J],
    o: Callable[[_J], _K],
) -> _K: ...
def pipe(value: Any, *functions: Callable[[Any], Any]) -> Any:
    """Apply ``functions`` to ``value`` in sequence, left to right.

    ``pipe(value, f, g, h)`` is equivalent to ``h(g(f(value)))``.

    Each function's input type must match the previous function's output
    type; the result type is inferred exactly. Up to ten functions are
    fully type-checked. Type checkers reject calls with more than ten
    functions (no checker can express the dependent types), though the
    runtime implementation accepts any number.

    Args:
        value: The initial value.
        *functions: Functions applied in order. Each takes exactly one
            positional argument — the output of the previous step.

    Returns:
        The value after every function has been applied.

    Examples:
        >>> pipe(2, lambda x: x * 3, str)  # -> "6"
        '6'
        >>> pipe(2)  # identity with no functions
        2

    """
    for function in functions:
        value = function(value)
    return value
