"""Typing fixture: retry given a non-Result operation. Must fail `ty`.

The intentional error is suppressed for repo-wide checks; ty flags the
ignore as unused if the diagnostic ever changes or disappears.
"""

from pyeffect.retry import Policy, retry


def main() -> None:
    # The operation must return a Result; 42 is a plain int.
    retry(lambda n: 42, Policy(max_attempts=3))  # ty: ignore[invalid-argument-type]
