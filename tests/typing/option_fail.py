"""Typing fixture: and_then given a non-Option callback. Must fail `ty`.

The intentional error is suppressed for repo-wide checks; ty flags the
ignore as unused if the diagnostic ever changes or disappears.
"""

from pyeffect.option import Some


def main() -> None:
    # and_then expects a callback returning Option; "a" is a plain str.
    Some(1).and_then(lambda x: "a")  # ty: ignore[invalid-argument-type]
