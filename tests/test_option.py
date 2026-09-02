"""Runtime behavior tests for Option: Some/Nothing, from_optional, flatten."""

from __future__ import annotations

from typing import cast

import pytest

from pyeffect.option import (
    Nothing,
    Option,
    Some,
    UnwrapNothingError,
    flatten,
    from_optional,
    transpose,
)
from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result


def test_some_holds_value() -> None:
    assert Some(5).value == 5


def test_equality() -> None:
    assert Some(1) == Some(1)
    assert Some(1) != Some(2)
    assert Nothing() == Nothing()
    assert Some(1) != Nothing()


def test_pattern_matching() -> None:
    opt: Option[int] = Some(5)
    match opt:
        case Some(value):
            assert value == 5
        case Nothing():
            pytest.fail("expected Some")

    match Nothing():
        case Some(_):
            pytest.fail("expected Nothing")
        case Nothing():
            pass


def test_map() -> None:
    assert Some(2).map(lambda x: x + 1) == Some(3)


def test_map_passes_nothing_through() -> None:
    assert Nothing().map(lambda x: x + 1) == Nothing()


def test_and_then_chains() -> None:
    result = Some(2).and_then(lambda x: Some(x + 1)).and_then(lambda x: Some(x * 10))
    assert result == Some(30)


def test_and_then_short_circuits_on_nothing() -> None:
    called = False

    def never(x: int) -> Option[int]:
        nonlocal called
        called = True
        return Some(x)

    assert Nothing().and_then(never) == Nothing()
    assert called is False


def test_or_else_recovers() -> None:
    recovered: Option[int] = Nothing().or_else(lambda: Some(7))
    assert recovered == Some(7)


def test_or_else_passes_some_through() -> None:
    assert Some(5).or_else(lambda: Some(0)) == Some(5)


def test_filter_keeps_matching() -> None:
    assert Some(4).filter(lambda x: x % 2 == 0) == Some(4)


def test_filter_drops_non_matching() -> None:
    assert Some(3).filter(lambda x: x % 2 == 0) == Nothing()


def test_filter_on_nothing() -> None:
    assert Nothing().filter(lambda x: True) == Nothing()


def test_inspect_runs_on_some() -> None:
    seen: list[int] = []
    assert Some(2).inspect(seen.append) == Some(2)
    assert seen == [2]


def test_inspect_skips_nothing() -> None:
    seen: list[int] = []

    def record(x: int) -> None:
        seen.append(x)

    assert Nothing().inspect(record) == Nothing()
    assert seen == []


def test_unwrap_on_some() -> None:
    assert Some(5).unwrap() == 5


def test_unwrap_on_nothing_is_a_defect_and_panics() -> None:
    with pytest.raises(UnwrapNothingError) as excinfo:
        Nothing().unwrap()
    assert str(excinfo.value) == "unwrap() on Nothing"


def test_expect_on_some() -> None:
    assert Some(5).expect("five") == 5


def test_expect_on_nothing_panics_with_message() -> None:
    with pytest.raises(UnwrapNothingError) as excinfo:
        Nothing().expect("must be present")
    assert "must be present" in str(excinfo.value)


def test_unwrap_or() -> None:
    assert Some(5).unwrap_or(0) == 5
    assert Nothing().unwrap_or(0) == 0


def test_unwrap_or_else() -> None:
    assert Some(5).unwrap_or_else(lambda: 0) == 5
    assert Nothing().unwrap_or_else(lambda: 0) == 0


def test_is_some_is_none() -> None:
    assert Some(1).is_some() is True
    assert Some(1).is_none() is False
    assert Nothing().is_some() is False
    assert Nothing().is_none() is True


def test_contains() -> None:
    assert Some(2).contains(2) is True
    assert Some(2).contains(3) is False
    assert Nothing().contains(2) is False


def test_ok_or() -> None:
    assert Some(5).ok_or("missing") == Ok(5)
    assert Nothing().ok_or("missing") == Err("missing")


def test_ok_or_else() -> None:
    assert Some(5).ok_or_else(lambda: "missing") == Ok(5)
    assert Nothing().ok_or_else(lambda: "missing") == Err("missing")


def test_optional_roundtrip() -> None:
    assert Some(5).optional() == 5
    assert Nothing().optional() is None
    assert from_optional(5) == Some(5)
    assert from_optional(None) == Nothing()


def test_flatten() -> None:
    assert flatten(Some(Some(1))) == Some(1)
    empty: Option[Option[int]] = Some(Nothing())
    assert flatten(empty) == Nothing()
    assert flatten(Nothing()) == Nothing()


def test_flatten_rejects_non_options() -> None:
    with pytest.raises(Panic):
        flatten(cast(Option[Option[int]], 5))


def test_result_ok_err_conversions() -> None:
    assert Ok(5).ok() == Some(5)
    assert Ok(5).err() == Nothing()
    assert Err("boom").ok() == Nothing()
    assert Err("boom").err() == Some("boom")


def test_and_returns_other_on_some() -> None:
    assert Some(1).and_(Some("a")) == Some("a")
    assert Nothing().and_(Some("a")) == Nothing()


def test_or_keeps_some() -> None:
    assert Some(1).or_(Some(2)) == Some(1)
    assert Nothing().or_(Some(2)) == Some(2)


def test_xor_is_exclusive() -> None:
    assert Some(1).xor(Some(2)) == Nothing()
    assert Some(1).xor(Nothing()) == Some(1)
    assert Nothing().xor(Some(2)) == Some(2)
    assert Nothing().xor(Nothing()) == Nothing()


def test_transpose_swaps_layers() -> None:
    opt_ok: Option[Result[int, str]] = Some(Ok(1))
    assert transpose(opt_ok) == Ok(Some(1))
    opt_err: Option[Result[int, str]] = Some(Err("boom"))
    assert transpose(opt_err) == Err("boom")
    opt_none: Option[Result[int, str]] = Nothing()
    assert transpose(opt_none) == Ok(Nothing())


def test_transpose_rejects_non_options() -> None:
    with pytest.raises(Panic):
        transpose(cast(Option[Result[int, str]], 5))


def test_transpose_rejects_some_with_non_result_payload() -> None:
    with pytest.raises(Panic):
        transpose(cast(Option[Result[int, str]], Some(5)))


def test_unwrap_nothing_error_exposes_context() -> None:
    with pytest.raises(UnwrapNothingError) as excinfo:
        Nothing().expect("must be present")
    assert excinfo.value.context == "must be present"


def test_unwrap_nothing_error_is_a_panic() -> None:
    with pytest.raises(Panic) as excinfo:
        Nothing().unwrap()
    assert isinstance(excinfo.value, UnwrapNothingError)
