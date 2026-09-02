"""Typing fixture: and_then given a non-Effect callback. Must fail `ty`.

The intentional error is suppressed for repo-wide checks; ty flags the
ignore as unused if the diagnostic ever changes or disappears.
"""

from pyeffect.effect import Effect


def main() -> None:
    # and_then expects a callback returning an Effect; x + 1 is a plain int.
    Effect.success(1).and_then(lambda x: x + 1)  # ty: ignore[invalid-argument-type]

    # zip expects an Effect; a plain value is not one.
    Effect.success(1).zip(1)  # ty: ignore[invalid-argument-type]
