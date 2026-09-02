"""A fully typed ``Option``: ``Some``/``Nothing`` for expected absence.

``Option[T]`` is the union ``Some[T] | Nothing``. Where ``Result`` models
*expected failure*, ``Option`` models *expected absence* — a dict lookup or
``find`` that legitimately has nothing to return. The caller receives an
``Option`` and decides what to do with it::

    >>> from pyeffect.option import Some, Nothing, from_optional
    >>> from_optional({"a": 1}.get("a"))
    Some(value=1)
    >>> from_optional({"a": 1}.get("b"))
    Nothing()
    >>> Some(2).map(lambda x: x * 3).unwrap_or(0)
    6
    >>> Nothing().unwrap_or(0)
    0

Unwrapping is the fail-fast edge: ``unwrap()``/``expect()`` on ``Nothing``
raise :class:`UnwrapNothingError`, because treating absence as a value is a
bug, not an expected outcome.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn

from pyeffect.do import _ShortCircuit
from pyeffect.panic import Panic

if TYPE_CHECKING:
    from pyeffect.result import Result

__all__ = [
    "Nothing",
    "Option",
    "Some",
    "UnwrapNothingError",
    "flatten",
    "from_optional",
    "transpose",
]


class UnwrapNothingError(Panic):
    """Raised when ``unwrap()``/``expect()`` is called on ``Nothing``.

    Unwrapping an absence is a bug — the caller promised a value. Panic
    instead of silently returning a wrong value. A :class:`Panic` subtype,
    so ``except Panic`` catches it while ``pytest.raises(UnwrapNothingError)``
    stays precise.
    """

    def __init__(self, context: str = "unwrap() on Nothing") -> None:
        self.context = context
        super().__init__(context)


@dataclass(frozen=True, slots=True)
class Some[T]:
    """The present variant of :data:`Option`, carrying a ``value``."""

    value: T

    __match_args__ = ("value",)

    def __iter__(self) -> Iterator[T]:
        """Yield the value so ``for x in some`` binds ``x`` in do-notation."""

        yield self.value

    def map[U](self, f: Callable[[T], U]) -> Option[U]:
        return Some(f(self.value))

    def and_then[U](self, f: Callable[[T], Option[U]]) -> Option[U]:
        return f(self.value)

    def and_[U](self, other: Option[U]) -> Option[U]:
        """Return ``other``, discarding this value (the eager ``and``)."""

        return other

    def or_else(self, f: Callable[[], Option[T]]) -> Option[T]:
        return self

    def or_(self, other: Option[T]) -> Option[T]:
        """Return ``self`` unchanged (the eager ``or``)."""

        return self

    def filter(self, f: Callable[[T], bool]) -> Option[T]:
        return Some(self.value) if f(self.value) else Nothing()

    def inspect(self, f: Callable[[T], object]) -> Option[T]:
        f(self.value)
        return self

    def unwrap(self) -> T:
        return self.value

    def expect(self, message: str) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def unwrap_or_else(self, f: Callable[[], T]) -> T:
        return self.value

    def is_some(self) -> bool:
        return True

    def is_none(self) -> bool:
        return False

    def contains(self, value: object) -> bool:
        return self.value == value

    def ok_or[E](self, error: E) -> Result[T, E]:
        # Deferred import: pyeffect.result imports this module at load time,
        # so a top-level import here would be circular.
        from pyeffect.result import Ok

        return Ok(self.value)

    def ok_or_else[E](self, f: Callable[[], E]) -> Result[T, E]:
        from pyeffect.result import Ok

        return Ok(self.value)

    def optional(self) -> T:
        return self.value

    def xor(self, other: Option[T]) -> Option[T]:
        """Return ``Some`` if exactly one side is present, else ``Nothing``."""

        return Nothing() if other.is_some() else self


@dataclass(frozen=True, slots=True)
class Nothing:
    """The absent variant of :data:`Option`, carrying no value.

    ``Nothing`` carries no data, so it needs no type parameter — it matches
    ``Option[T]`` for every ``T``. ``unwrap()`` on it is a bug and panics.
    """

    def __iter__(self) -> Iterator[NoReturn]:
        """Raise :class:`_ShortCircuit` when advanced — never yields."""

        def _iter() -> Iterator[NoReturn]:
            raise _ShortCircuit(self)
            yield  # pragma: no cover -- unreachable, makes _iter a generato

        return _iter()

    def map[U](self, f: Callable[..., U]) -> Option[U]:
        return self

    def and_then[U](self, f: Callable[..., Option[U]]) -> Option[U]:
        return self

    def and_[U](self, other: Option[U]) -> Option[U]:
        """``Nothing`` short-circuits: return ``self`` unchanged."""

        return self

    def or_else[T](self, f: Callable[[], Option[T]]) -> Option[T]:
        return f()

    def or_[T](self, other: Option[T]) -> Option[T]:
        """Return ``other`` (the eager ``or``)."""

        return other

    def filter[T](self, f: Callable[..., bool]) -> Option[T]:
        return self

    def inspect[T](self, f: Callable[..., object]) -> Option[T]:
        return self

    def unwrap(self) -> NoReturn:
        raise UnwrapNothingError()

    def expect(self, message: str) -> NoReturn:
        raise UnwrapNothingError(message)

    def unwrap_or[T](self, default: T) -> T:
        return default

    def unwrap_or_else[T](self, f: Callable[[], T]) -> T:
        return f()

    def is_some(self) -> bool:
        return False

    def is_none(self) -> bool:
        return True

    def contains(self, value: object) -> bool:
        return False

    def ok_or[T, E](self, error: E) -> Result[T, E]:
        from pyeffect.result import Err

        return Err(error)

    def ok_or_else[T, E](self, f: Callable[[], E]) -> Result[T, E]:
        from pyeffect.result import Err

        return Err(f())

    def optional(self) -> None:
        return None

    def xor[T](self, other: Option[T]) -> Option[T]:
        """Return ``other`` if present, else ``self`` (which is ``Nothing``)."""

        return other if other.is_some() else self


# Note: ``Option`` is a typing union (Some[T] | Nothing), not a runtime
# class. ``isinstance(x, Option)`` raises TypeError — use ``match``,
# ``is_some()``, or ``isinstance(x, (Some, Nothing))`` instead.
type Option[T] = Some[T] | Nothing


def from_optional[T](value: T | None) -> Option[T]:
    """Lift a Python ``T | None`` into an :data:`Option`.

    This is the bridge from Python's implicit-absence convention (``None``)
    to an explicit ``Option``::

        >>> from pyeffect.option import from_optional
        >>> from_optional(5)
        Some(value=5)
        >>> from_optional(None)
        Nothing()
    """

    return Some(value) if value is not None else Nothing()


def flatten[T](opt: Option[Option[T]]) -> Option[T]:
    """Collapse a nested option: ``Some(Some(x))`` becomes ``Some(x)``.

    >>> from pyeffect.option import Some, Nothing, flatten
    >>> flatten(Some(Some(1)))
    Some(value=1)
    >>> flatten(Some(Nothing()))
    Nothing()
    >>> flatten(Nothing())
    Nothing()
    """

    match opt:
        case Some(inner):
            return inner
        case Nothing():
            return Nothing()
        case _:
            raise Panic(f"flatten expected an Option, got {type(opt).__name__}")


def transpose[T, E](opt: Option[Result[T, E]]) -> Result[Option[T], E]:
    """Swap the nesting: ``Option<Result<T, E>>`` to ``Result<Option<T>, E>``.

    ``Some(Ok(x))`` is ``Ok(Some(x))``, ``Some(Err(e))`` is ``Err(e)``,
    and ``Nothing()`` is ``Ok(Nothing())``.

    >>> from pyeffect.option import Some, Nothing, transpose
    >>> from pyeffect.result import Ok, Err
    >>> transpose(Some(Ok(1)))
    Ok(value=Some(value=1))
    >>> transpose(Some(Err("boom")))
    Err(error='boom')
    >>> transpose(Nothing())
    Ok(value=Nothing())
    """

    from pyeffect.result import Err, Ok

    if isinstance(opt, Nothing):
        return Ok(Nothing())
    if isinstance(opt, Some):
        inner = opt.value  # Result[T, E]
        if isinstance(inner, Ok):
            return Ok(Some(inner.value))
        if isinstance(inner, Err):
            return Err(inner.error)
        raise Panic(
            f"transpose expected a Some to carry a Result, got {type(inner).__name__}"
        )
    raise Panic(f"transpose expected an Option, got {type(opt).__name__}")
