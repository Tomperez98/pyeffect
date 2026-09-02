"""Typing fixture: valid pipe calls pinned with assert_type.

Must type-check clean under `ty check`. Each assert_type pins the exact
inferred type at that arity so the typing contract cannot drift silently.
"""

from functools import partial
from typing import Literal, assert_type

from pyeffect import pipe


def add_one(x: int) -> int:
    return x + 1


def to_str(x: int) -> str:
    return str(x)


def split(x: str) -> list[str]:
    return x.split(",")


def scale(x: int, factor: int = 2) -> int:
    return x * factor


class Double:
    def __call__(self, x: int) -> int:
        return x * 2


def main() -> None:
    # Identity: the value passes through with its exact type.
    # (ty's assert_type demands exact equivalence, so pin Literal, not int.)
    assert_type(pipe(1), Literal[1])

    # One step: input and output types are chained.
    assert_type(pipe(1, add_one), int)

    # Two steps: str flows out of int->str.
    assert_type(pipe(1, add_one, to_str), str)

    # Three steps: list[str] flows out of str->list[str].
    assert_type(pipe(1, add_one, to_str, split), list[str])

    # Callable kinds that must satisfy Callable[[A], B].
    assert_type(pipe("a,b", split, len), int)
    assert_type(pipe(2, partial(scale, factor=3), to_str), str)
    assert_type(pipe(3, Double(), to_str), str)

    # The full ten-function typed limit.
    assert_type(
        pipe("a", split, len, str, len, str, len, str, len, str, len),
        int,
    )
