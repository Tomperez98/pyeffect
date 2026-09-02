"""Typing fixture: valid Result/attempt/guard calls pinned with assert_type."""

from typing import Literal, assert_type

from pyeffect.option import Nothing, Option, Some
from pyeffect.result import (
    Err,
    ErrorContext,
    Ok,
    Result,
    attempt,
    flatten,
    guard,
    transpose,
    traverse,
)


def add_one(x: int) -> int:
    return x + 1


def to_str(x: int) -> str:
    return str(x)


def handle(r: Result[int, str]) -> int:
    match r:
        case Ok(value):
            return value
        case Err(error):
            return len(error)


def main(n: int, boom: str) -> None:
    # Construction and value access.
    assert_type(Ok(n).value, int)
    assert_type(Err(boom).error, str)

    # Chaining over a fully-typed Result keeps every step concrete.
    r: Result[int, str] = Ok(n)
    assert_type(r.map(to_str).unwrap(), str)
    assert_type(r.and_then(lambda x: Ok(x + 1)).unwrap(), int)
    assert_type(r.unwrap_or_else(lambda e: len(e)), int)

    # Err branch: recovery types are exact.
    assert_type(Err(boom).unwrap_or(0), Literal[0])
    assert_type(Err(boom).unwrap_or_else(lambda e: len(e)), int)

    # attempt: failure becomes a value, typed exactly.
    assert_type(attempt(lambda: n).unwrap(), int)
    assert_type(attempt(lambda: n, catch=lambda e: str(e)), Result[int, str])

    # guard: the decorated signature is preserved.
    assert_type(guard(add_one)(n), Result[int, Exception])
    assert_type(guard(add_one, catch=lambda e: str(e))(n), Result[int, str])

    # Pattern matching narrows the union to each variant.
    assert_type(handle(Ok(n)), int)

    # Catamorphism and inspection: both branches in one typed expression.
    assert_type(r.fold(lambda v: v + 1, lambda e: len(e)), int)
    assert_type(r.contains(1), bool)
    assert_type(r.map_or(0, lambda v: v + 1), int)
    assert_type(r.map_or_else(lambda e: len(e), lambda v: v + 1), int)

    # inspect/inspect_err keep the exact Result type (via binding context).
    inspected: Result[int, str] = r.inspect(lambda v: None)
    assert_type(inspected, Result[int, str])
    inspected_err: Result[int, str] = r.inspect_err(lambda e: None)
    assert_type(inspected_err, Result[int, str])

    # Applicative zip/map2 pair two Results; the first error wins.
    zipped: Result[tuple[int, str], str] = r.zip(Ok("a"))
    assert_type(zipped, Result[tuple[int, str], str])
    mapped2: Result[str, str] = r.map2(Ok("a"), lambda a, b: str(a) + b)
    assert_type(mapped2, Result[str, str])

    # traverse: a typed fallible function over a sequence.
    def ok_result(x: int) -> Result[int, str]:
        return Ok(x)

    assert_type(traverse(ok_result, [n]), Result[list[int], str])

    # context/with_context swap the error slot for an ErrorContext; the
    # success slot is untouched (pinned via binding for the Err variant).
    ctx: Result[int, ErrorContext] = r.context("while parsing")
    assert_type(ctx, Result[int, ErrorContext])
    ctx_lazy: Result[int, ErrorContext] = r.with_context(lambda e: f"failed: {e}")
    assert_type(ctx_lazy, Result[int, ErrorContext])
    assert_type(Ok(n).context("while parsing"), Result[int, ErrorContext])

    # and_/or_: eager keep-other / keep-self combinators.
    and_ok: Result[str, str] = r.and_(Ok("a"))
    assert_type(and_ok, Result[str, str])
    and_err: Result[str, str] = Err(boom).and_(Ok("a"))
    assert_type(and_err, Result[str, str])
    or_ok: Result[int, str] = r.or_(Err("other"))
    assert_type(or_ok, Result[int, str])

    # flatten: collapse a nested Result; unbound slots are pinned by binding.
    flat_ok: Result[int, str] = flatten(Ok(Ok(n)))
    assert_type(flat_ok, Result[int, str])
    flat_inner_err: Result[int, str] = flatten(Ok(Err(boom)))
    assert_type(flat_inner_err, Result[int, str])
    flat_pass: Result[int, str] = flatten(Err(boom))
    assert_type(flat_pass, Result[int, str])

    # transpose: swap the Result and Option layers.
    t_ok: Option[Result[int, str]] = transpose(Ok(Some(n)))
    assert_type(t_ok, Option[Result[int, str]])
    t_none: Option[Result[int, str]] = transpose(Ok(Nothing()))
    assert_type(t_none, Option[Result[int, str]])
    t_err: Option[Result[int, str]] = transpose(Err(boom))
    assert_type(t_err, Option[Result[int, str]])
