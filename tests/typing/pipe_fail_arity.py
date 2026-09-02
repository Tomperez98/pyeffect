"""Typing fixture: more than ten steps. Must fail `ty`.

The intentional error is suppressed for repo-wide checks; ty flags the
ignore as unused if the diagnostic ever changes or disappears.
"""

from __future__ import annotations

from pyeffect import pipe


def add_one(x: int) -> int:
    return x + 1


def main() -> None:
    # Eleven steps exceed the typed overloads; no checker can express
    # dependent variadic types. Statically invalid by design.
    pipe(
        1,
        add_one,
        add_one,
        add_one,
        add_one,
        add_one,
        add_one,
        add_one,
        add_one,
        add_one,
        add_one,
        add_one,
    )  # ty: ignore[no-matching-overload]
