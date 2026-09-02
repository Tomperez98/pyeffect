"""Discriminated errors: a ``TaggedError`` with a literal ``tag``.

A ``TaggedError`` subclass declares a string tag that callers can switch on
without string-matching on the message::

    >>> from pyeffect.tagged import TaggedError, match_error
    >>> class NotFound(TaggedError, tag="NotFound"):
    ...     def __init__(self, key: str) -> None:
    ...         self.key = key
    ...         super().__init__(f"{key} not found")
    >>> match_error(NotFound("x"), {"NotFound": lambda e: 404})
    404

Narrowing is Python's native ``isinstance``/``match`` (``ty`` narrows the
branch); ``.is_`` is a convenience boolean guard that does not narrow.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

__all__ = ["MatchError", "TaggedError", "match_error", "match_error_partial"]


class TaggedError(Exception):
    """Base class for errors carrying a literal ``tag``.

    Subclasses declare the tag with a keyword argument
    (``class UserNotFound(TaggedError, tag="UserNotFound")``); when omitted
    it defaults to the class name. The tag lives on the class, so every
    instance of a subclass shares it.
    """

    tag: str

    def __init_subclass__(cls, *, tag: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.tag = tag if tag is not None else cls.__name__

    def __init__(self, message: str = "") -> None:
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """A minimal serializable form; subclasses override to add payload."""

        return {"tag": self.tag, "message": str(self)}

    @classmethod
    def is_(cls, value: object) -> bool:
        """Whether ``value`` is an instance of this class.

        A boolean convenience guard. For *type narrowing*, use
        ``isinstance(value, cls)`` or a ``match`` statement — ``ty``
        narrows those, but cannot narrow through a plain ``bool`` method.
        """

        return isinstance(value, cls)


class MatchError(KeyError):
    """Raised by :func:`match_error` when no handler covers the error's tag.

    A tag with no handler is a bug — the match was supposed to be
    exhaustive — so it fails fast instead of returning a wrong value.
    """

    def __init__(self, tag: object, error: object) -> None:
        self.tag = tag
        self.error = error
        super().__init__(f"no handler for tag {tag!r}")


def match_error[R](error: object, handlers: Mapping[str, Callable[[Any], R]]) -> R:
    """Dispatch on ``error.tag`` and return the selected handler's result.

    ``handlers`` maps tag strings to single-argument callables. The handler
    receives the error unchanged. A tag with no handler raises
    :class:`MatchError` (fail fast). Handlers are typed ``Callable[[Any],
    ...]`` — Python cannot narrow a handler's parameter per dict key, so
    narrow with ``isinstance``/``match`` inside the handler when you need a
    specific field.
    """

    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    if handler is None:
        raise MatchError(tag, error)
    return handler(error)


def match_error_partial[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]],
    fallback: Callable[[Any], R],
) -> R:
    """Like :func:`match_error`, but unhandled tags go to ``fallback``.

    Use this to transform a subset of variants while leaving the rest
    unchanged or mapped to a default.
    """

    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    return handler(error) if handler is not None else fallback(error)
