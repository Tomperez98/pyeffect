"""Typing fixture: and_then given a non-Result callback. Must fail `ty`.

The intentional error is suppressed for repo-wide checks; ty flags the
ignore as unused if the diagnostic ever changes or disappears.
"""

from pyeffect.result import Ok


def main() -> None:
    # and_then expects a callback returning Result; "a" is a plain str.
    Ok(1).and_then(lambda x: "a")  # ty: ignore[invalid-argument-type]

    # zip expects a Result; a plain value is not one.
    Ok(1).zip(1)  # ty: ignore[invalid-argument-type]
