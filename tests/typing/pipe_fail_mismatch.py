"""Typing fixture: a chain whose types do not line up. Must fail `ty`."""

from pyeffect import pipe


def add_one(x: int) -> int:
    return x + 1


def to_str(x: int) -> str:
    return str(x)


def main() -> None:
    # to_str returns str; add_one expects int. Statically invalid — the
    # intentional error is suppressed for repo-wide checks; ty flags this
    # ignore as unused if the diagnostic ever changes or disappears.
    pipe(1, to_str, add_one)  # ty: ignore[invalid-argument-type]
