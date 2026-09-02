"""Typing fixture: valid compose/combinator calls pinned with assert_type."""

from collections.abc import Callable
from typing import assert_type

from pyeffect.compose import (
    compose,
    constant,
    curry,
    flip,
    identity,
    lift,
    lift2,
    lift3,
    partial,
    tap,
    unpack,
)
from pyeffect.result import Ok, Result


def add_one(x: int) -> int:
    return x + 1


def to_str(x: int) -> str:
    return str(x)


def add(a: int, b: int) -> int:
    return a + b


def add3(a: int, b: int, c: int) -> int:
    return a + b + c


def forty_two() -> int:
    return 42


def main(n: int, s: str) -> None:

    # Empty compose is identity; arity 1 preserves the callable.
    assert_type(compose()(n), int)
    assert_type(compose(add_one)(n), int)

    # Right-to-left chaining: to_str ∘ add_one : int -> str.
    assert_type(compose(to_str, add_one)(n), str)
    assert_type(compose(len, to_str)(n), int)  # len ∘ to_str : int -> int

    # The full ten-function typed limit.
    assert_type(
        compose(
            str,
            len,
            str,
            len,
            str,
            len,
            str,
            len,
            str,
            len,
        )(s),
        str,
    )

    assert_type(tap(add_one)(n), int)
    assert_type(identity(n), int)
    assert_type(constant(n)(s), int)
    assert_type(flip(add)(1, 2), int)
    assert_type(unpack(add)((1, 2)), int)

    # curry: each step is a single-argument callable; the final step runs.
    assert_type(curry(forty_two)(), int)
    assert_type(curry(add)(1)(2), int)
    assert_type(curry(add)(1), Callable[[int], int])
    assert_type(curry(add3)(1)(2)(3), int)

    # partial re-exports functools.partial with its exact type.
    assert_type(partial(add, 1)(2), int)

    # lift: plain functions pushed into the Result domain, error type
    # fixed by the binding context.
    lifted: Callable[[Result[int, str]], Result[int, str]] = lift(add_one)
    assert_type(lifted(Ok(n)), Result[int, str])
    lifted2: Callable[[Result[int, str], Result[int, str]], Result[int, str]] = lift2(
        add
    )
    assert_type(lifted2(Ok(n), Ok(n)), Result[int, str])
    lifted3: Callable[
        [Result[int, str], Result[int, str], Result[int, str]],
        Result[int, str],
    ] = lift3(lambda a, b, c: a + b + c)
    assert_type(lifted3(Ok(n), Ok(n), Ok(n)), Result[int, str])
