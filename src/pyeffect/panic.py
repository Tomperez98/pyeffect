"""The unified defect type: :class:`PanicError`.

``pyeffect`` has one rule — *bugs panic, expected failures return values*.
``PanicError`` is the throwable kind for bugs: an asserted invariant failed,
a callback broke a combinator contract, or a caller unwrapped a failure it
promised could not happen.

Catch ``PanicError`` only at a defect boundary (process entry point, request
crash reporter, worker supervisor, test assertion). Never convert a
``PanicError`` back into an ``Err`` — that hides the bug and corrupts the
typed error contract.
"""

from __future__ import annotations

from typing import Any, NoReturn

__all__ = ["PanicError", "is_panic", "panic"]


class PanicError(Exception):
    """A defect — a bug or broken invariant — thrown, never returned as ``Err``.

    Attributes:
        tag: The literal ``"Panic"`` discriminator, mirroring
            :class:`~pyeffect.tagged.TaggedError`.
        cause: The underlying value that triggered the defect, if any.

    """

    tag: str = "Panic"

    def __init__(self, message: str, cause: object | None = None) -> None:
        self.cause = cause
        super().__init__(message)

    @classmethod
    def is_(cls, value: object) -> bool:
        """Return whether ``value`` is a :class:`PanicError` (or a subclass)."""
        return isinstance(value, cls)

    def to_dict(self) -> dict[str, Any]:
        """Return a minimal serializable form of the defect."""
        return {
            "tag": self.tag,
            "message": str(self),
            "cause": _describe(self.cause),
        }


def _describe(value: object | None) -> str | None:
    """Return a safe string form of a cause: ``TypeName: message`` for exceptions."""
    if value is None:
        return None
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    return repr(value)


def panic(message: str, cause: object | None = None) -> NoReturn:
    """Raise a :class:`PanicError`; typed ``NoReturn`` so calls read as returns."""
    raise PanicError(message, cause)


def is_panic(value: object) -> bool:
    """Return whether ``value`` is a :class:`PanicError` (or a subclass)."""
    return isinstance(value, PanicError)
