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

from typing import TYPE_CHECKING, Any, cast, overload

from pyeffect.panic import PanicError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "MatchError",
    "TaggedError",
    "UnhandledError",
    "match_error",
    "match_error_partial",
]


class TaggedError(Exception):
    """Base class for errors carrying a literal ``tag``.

    Subclasses declare the tag with a keyword argument
    (``class UserNotFoundError(TaggedError, tag="UserNotFound")``); when
    omitted it defaults to the class name. The tag lives on the class, so
    every instance of a subclass shares it; the base class itself carries
    ``"TaggedError"`` so direct instances are usable.
    """

    tag: str = "TaggedError"

    def __init_subclass__(cls, *, tag: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.tag = tag if tag is not None else cls.__name__

    def __init__(self, message: str = "") -> None:
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Return a minimal serializable form; subclasses override to add payload."""
        return {"tag": self.tag, "message": str(self)}

    def match[R](self, handlers: Mapping[str, Callable[[Any], R]]) -> R:
        """Exhaustively dispatch on this error's tag.

        ``error.match(handlers)`` is :func:`match_error` as a method. The
        handler map must cover the tag; a missing tag raises :class:`MatchError`.
        """
        return match_error(self, handlers)

    @classmethod
    def is_(cls, value: object) -> bool:
        """Whether ``value`` is an instance of this class.

        A boolean convenience guard. For *type narrowing*, use
        ``isinstance(value, cls)`` or a ``match`` statement — ``ty``
        narrows those, but cannot narrow through a plain ``bool`` method.
        """
        return isinstance(value, cls)


class UnhandledError(TaggedError, tag="UnhandledException"):
    """The default error when a boundary captures an exception without translating it.

    ``attempt``/``guard`` wrap an unknown exception in this tagged error so
    every ``Err`` stays uniformly matchable by tag. The original exception
    is preserved as :attr:`cause`.
    """

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(f"{type(cause).__name__}: {cause}")

    def to_dict(self) -> dict[str, Any]:
        """Include the preserved cause alongside tag and message."""
        return {
            "tag": self.tag,
            "message": str(self),
            "cause": f"{type(self.cause).__name__}: {self.cause}",
        }


class MatchError(PanicError):
    """Raised by :func:`match_error` when no handler covers the error's tag.

    A tag with no handler is a bug — the match was supposed to be
    exhaustive — so it fails fast instead of returning a wrong value.

    Attributes:
        missing_tag: The tag that had no handler.
        error: The error value that was being matched.

    """

    tag: str = "MatchError"

    def __init__(self, tag: object, error: object) -> None:
        self.missing_tag = tag
        self.error = error
        super().__init__(f"no handler for tag {tag!r}", cause=error)


@overload
def match_error[R](error: object, handlers: Mapping[str, Callable[[Any], R]]) -> R: ...
@overload
def match_error[R](
    handlers: Mapping[str, Callable[[Any], R]],
) -> Callable[[object], R]: ...
def match_error[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]] | None = None,
) -> Any:
    """Dispatch on ``error.tag`` and return the selected handler's result.

    ``match_error(error, handlers)`` is data-first; ``match_error(handlers)``
    is data-last and returns a curried function. A tag with no handler raises
    :class:`MatchError` (fail fast). Handlers are typed ``Callable[[Any],
    ...]`` — Python cannot narrow a handler's parameter per dict key, so
    narrow with ``isinstance``/``match`` inside the handler when you need a
    specific field.
    """
    if handlers is None:
        # Data-last form: the first argument is actually the handlers map.
        def dispatch(value: object) -> R:
            return match_error(value, cast("Mapping[str, Callable[[Any], R]]", error))

        return dispatch

    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    if handler is None:
        raise MatchError(tag, error)
    return handler(error)


@overload
def match_error_partial[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]],
    fallback: Callable[[Any], R],
) -> R: ...
@overload
def match_error_partial[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]],
) -> R | Any: ...
def match_error_partial[R](
    error: object,
    handlers: Mapping[str, Callable[[Any], R]],
    fallback: Callable[[Any], Any] | None = None,
) -> Any:
    """Like :func:`match_error`, but unhandled tags do not fail.

    With a ``fallback``, unhandled tags are passed to it. Without one, the
    unhandled error passes through unchanged (identity fallback).
    """
    tag = getattr(error, "tag", None)
    handler = handlers.get(tag)
    if handler is not None:
        return handler(error)
    return error if fallback is None else fallback(error)
