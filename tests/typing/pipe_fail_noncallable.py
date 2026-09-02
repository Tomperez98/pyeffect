"""Typing fixture: a step that is not callable. Must fail `ty`."""

from pyeffect import pipe


def main() -> None:
    # 42 is not a Callable[[A], B]. Statically invalid — the intentional
    # error is suppressed for repo-wide checks; ty flags this ignore as
    # unused if the diagnostic ever changes or disappears.
    pipe(1, 42)  # ty: ignore[invalid-argument-type]
