"""Typing fixture: valid Option calls pinned with assert_type."""

from __future__ import annotations

from typing import Literal, assert_type

from pyeffect.option import Nothing, Option, Some, flatten, from_optional, transpose
from pyeffect.result import Err, Ok, Result


def to_str(x: int) -> str:
    return str(x)


def main(n: int, boom: str) -> None:
    # Construction and value access.
    assert_type(Some(n).value, int)

    # Chaining over a fully-typed Option keeps every step concrete.
    o: Option[int] = Some(n)
    assert_type(o.map(to_str).unwrap(), str)
    assert_type(o.and_then(lambda x: Some(x + 1)).unwrap(), int)
    assert_type(o.unwrap_or(0), int)
    assert_type(o.unwrap_or_else(lambda: 0), int)

    # Nothing branch: fallbacks and conversions are exact.
    assert_type(Nothing().unwrap_or(0), Literal[0])
    assert_type(Nothing().or_else(lambda: Some(n)).unwrap(), int)

    # filter and inspect keep the value type.
    assert_type(Some(n).filter(lambda x: x > 0).unwrap(), int)
    assert_type(Some(n).inspect(lambda _: None).unwrap(), int)

    # Option -> Result conversions. Method-scoped typevars on Nothing need
    # binding context, so those are pinned via annotated assignments.
    assert_type(Some(n).ok_or("missing"), Result[int, str])
    assert_type(Some(n).ok_or_else(lambda: boom), Result[int, str])
    recovered: Result[int, str] = Nothing().ok_or(boom)
    assert_type(recovered, Result[int, str])

    # Result -> Option conversions; same binding-context rule for r.err().
    r: Result[int, str] = Ok(n)
    assert_type(r.ok(), Option[int])
    error: Option[str] = r.err()
    assert_type(error, Option[str])

    # The Python-optional bridge and nested collapse.
    assert_type(from_optional(n), Option[int])
    flat: Option[int] = flatten(Some(Some(n)))
    assert_type(flat, Option[int])
    flat_empty: Option[int] = flatten(Some(Nothing()))
    assert_type(flat_empty, Option[int])

    # and_/or_/xor: eager combinators.
    and_some: Option[str] = Some(n).and_(Some("a"))
    assert_type(and_some, Option[str])
    and_none: Option[str] = Nothing().and_(Some("a"))
    assert_type(and_none, Option[str])
    or_some: Option[int] = Some(n).or_(Some(2))
    assert_type(or_some, Option[int])
    or_none: Option[int] = Nothing().or_(Some(2))
    assert_type(or_none, Option[int])
    xor1: Option[int] = Some(n).xor(Nothing())
    assert_type(xor1, Option[int])
    xor2: Option[int] = Nothing().xor(Some(n))
    assert_type(xor2, Option[int])

    # transpose: swap the Option and Result layers.
    ot_ok: Result[Option[int], str] = transpose(Some(Ok(n)))
    assert_type(ot_ok, Result[Option[int], str])
    ot_err: Result[Option[int], str] = transpose(Some(Err(boom)))
    assert_type(ot_err, Result[Option[int], str])
    ot_none: Result[Option[int], str] = transpose(Nothing())
    assert_type(ot_none, Result[Option[int], str])
