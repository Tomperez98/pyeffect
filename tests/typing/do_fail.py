"""Typing fixture: do rejects non-generators and bare-value yields.

The intentional errors are suppressed for repo-wide checks; ty flags the
ignores as unused if the diagnostics ever change or disappear.
"""

from pyeffect import Ok, do


def main() -> None:
    # do requires a generator expression; a bare Result is not one.
    do(Ok(1))  # ty: ignore[no-matching-overload]

    # The generator must yield a Result/Option, not a bare value.
    do(42 for _ in [1])  # ty: ignore[no-matching-overload]
