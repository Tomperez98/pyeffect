# ruff: noqa: UP047 -- PEP 695 type params on @overload are not checked by ty;
# classic TypeVars required (ty 0.0.77 silently skips overload checking).
"""Do-notation: linear composition of ``Result``/``Option``.

``do`` runs a generator expression in which each ``for ... in result``
clause unwraps a ``Result``/``Option`` and the first expression is the
final value. An ``Err``/``Nothing`` short-circuits the whole block::

    >>> from pyeffect.do import do
    >>> from pyeffect.result import Ok, Err
    >>> do(Ok(x * 2) for x in Ok(21))
    Ok(value=42)
    >>> do(Ok(x) for x in Err("boom"))
    Err(error='boom')

The success variants (``Ok``/``Some``) implement ``__iter__`` to yield
their value, so ``for x in result`` binds ``x`` precisely. The failure
variants (``Err``/``Nothing``) raise :class:`_ShortCircuit`, a private
``BaseException`` that ``do`` catches to short-circuit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, overload

from pyeffect.panic import PanicError

if TYPE_CHECKING:
    from collections.abc import Generator

    from pyeffect.option import Option
    from pyeffect.result import Result

__all__ = ["do"]

_T = TypeVar("_T")
_E = TypeVar("_E")


class _ShortCircuit(BaseException):
    """Control-flow signal raised when a failure variant is iterated.

    Subclasses ``BaseException`` (not ``Exception``) so user ``except
    Exception`` blocks cannot swallow the short-circuit — it is control
    flow, like ``StopIteration``. Carries the failure variant
    (``Err``/``Nothing``) back to :func:`do`.
    """

    __slots__ = ("result",)

    def __init__(self, result: Any) -> None:
        self.result = result
        super().__init__()


@overload
def do(gen: Generator[Result[_T, _E]]) -> Result[_T, _E]: ...
@overload
def do(gen: Generator[Option[_T]]) -> Option[_T]: ...
def do(gen: Generator[Any, None, Any]) -> Any:
    """Run a do-notation block expressed as a generator expression.

    Each ``for ... in result`` clause unwraps one ``Result``/``Option``:
    an ``Ok``/``Some`` binds its value to the loop variable, an
    ``Err``/``Nothing`` short-circuits the whole expression to that
    failure. The first (and only) yielded expression is the final
    ``Result``/``Option``.

    The generator must yield exactly one value — the generator-expression
    form always does; yielding none or more than one is a bug and panics.
    Yielding a bare non-``Result`` value is a bug the type checker rejects.
    """
    try:
        result = next(gen)
    except _ShortCircuit as short:
        return short.result
    except StopIteration:
        msg = "do: the generator yielded no value"
        raise PanicError(msg) from None
    try:
        next(gen)
    except StopIteration:
        return result
    except _ShortCircuit:
        msg = "do: the generator must yield exactly one value"
        raise PanicError(msg) from None
    msg = "do: the generator must yield exactly one value"
    raise PanicError(msg)
