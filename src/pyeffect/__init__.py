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
from pyeffect.do import do
from pyeffect.effect import Effect, do_effect, sequence
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
    partition,
    traverse,
)
from pyeffect.retry import Backoff, Policy, retry
from pyeffect.tagged import MatchError, TaggedError, match_error, match_error_partial

__all__ = [
    "Backoff",
    "Effect",
    "Err",
    "ErrorContext",
    "MatchError",
    "Nothing",
    "Ok",
    "Option",
    "Policy",
    "Result",
    "Some",
    "TaggedError",
    "UnwrapError",
    "UnwrapNothingError",
    "attempt",
    "compose",
    "constant",
    "curry",
    "do",
    "do_effect",
    "flatten",
    "flip",
    "from_optional",
    "guard",
    "identity",
    "lift",
    "lift2",
    "lift3",
    "match_error",
    "match_error_partial",
    "partial",
    "partition",
    "pipe",
    "retry",
    "sequence",
    "tap",
    "traverse",
    "unpack",
]
