"""Typing fixture: compose with incompatible types. Must fail `ty`.

The intentional error is suppressed for repo-wide checks; ty flags the
ignore as unused if the diagnostic ever changes or disappears.
"""

from __future__ import annotations

from pyeffect.compose import compose, curry


def add_one(x: int) -> int:
    return x + 1


def add(a: int, b: int) -> int:
    return a + b


def main() -> None:
    # compose(f, g) = f ∘ g; g's output must feed f's input. add_one
    # returns int, but len expects Sized. Statically invalid.
    compose(len, add_one)  # ty: ignore[invalid-argument-type]

    # curry(add)(1) is Callable[[int], int]; "a" is not an int.
    curry(add)(1)("a")  # ty: ignore[invalid-argument-type]
