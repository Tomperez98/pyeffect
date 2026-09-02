"""pyeffect: a fully typed functional core for Python."""

from pyeffect.compose import (
    compose,
    constant,
    curry,
    flip,
    identity,
    lift,
    lift2,
    lift3,
    partial,
    tap,
    unpack,
)
from pyeffect.effect import Effect, sequence
from pyeffect.option import (
    Nothing,
    Option,
    Some,
    UnwrapNothingError,
    flatten,
    from_optional,
)
from pyeffect.pipe import pipe
from pyeffect.result import (
    Err,
    ErrorContext,
    Ok,
    Result,
    UnwrapError,
    attempt,
    guard,
    traverse,
)
from pyeffect.retry import Policy, retry

__all__ = [
    "Effect",
    "Err",
    "ErrorContext",
    "Nothing",
    "Ok",
    "Option",
    "Policy",
    "Result",
    "Some",
    "UnwrapError",
    "UnwrapNothingError",
    "attempt",
    "compose",
    "constant",
    "curry",
    "flatten",
    "flip",
    "from_optional",
    "guard",
    "identity",
    "lift",
    "lift2",
    "lift3",
    "partial",
    "pipe",
    "retry",
    "sequence",
    "tap",
    "traverse",
    "unpack",
]
