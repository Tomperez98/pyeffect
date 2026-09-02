"""Runtime behavior tests for Result: Ok/Err, attempt, guard."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest

from pyeffect.option import Nothing, Option, Some
from pyeffect.panic import Panic
from pyeffect.result import (
    Err,
    ErrorContext,
    Ok,
    Result,
    UnwrapError,
    attempt,
    flatten,
    guard,
    recover,
    transpose,
    traverse,
)
from pyeffect.tagged import UnhandledException


def add_one(x: int) -> int:
    return x + 1


def test_ok_holds_value() -> None:
    assert Ok(5).value == 5


def test_err_holds_error() -> None:
    assert Err("boom").error == "boom"


def test_equality() -> None:
    assert Ok(1) == Ok(1)
    assert Ok(1) != Ok(2)
    assert Err("x") == Err("x")
    assert Ok(1) != Err(1)


def test_pattern_matching() -> None:
    result: Result[int, str] = Ok(5)
    match result:
        case Ok(value):
            assert value == 5
        case Err(_):
            pytest.fail("expected Ok")

    match Err("boom"):
        case Ok(_):
            pytest.fail("expected Err")
        case Err(error):
            assert error == "boom"


def test_map_on_ok() -> None:
    assert Ok(2).map(add_one) == Ok(3)


def test_map_passes_err_through() -> None:
    assert Err("boom").map(add_one) == Err("boom")


def test_and_then_chains() -> None:
    result = Ok(2).and_then(lambda x: Ok(x + 1)).and_then(lambda x: Ok(x * 10))
    assert result == Ok(30)


def test_and_then_short_circuits_on_err() -> None:
    called = False

    def never(x: int) -> Result[int, str]:
        nonlocal called
        called = True
        return Ok(x)

    assert Err("boom").and_then(never) == Err("boom")
    assert called is False


def test_map_err() -> None:
    assert Err(1).map_err(str) == Err("1")
    assert Ok(5).map_err(str) == Ok(5)


def test_or_else_recovers() -> None:
    recovered = Err("boom").or_else(lambda e: Ok(len(e)))
    assert recovered == Ok(4)


def test_or_else_passes_ok_through() -> None:
    assert Ok(5).or_else(lambda e: Err(e)) == Ok(5)


def test_unwrap_on_ok() -> None:
    assert Ok(5).unwrap() == 5


def test_unwrap_on_err_is_a_defect_and_panics() -> None:
    with pytest.raises(UnwrapError) as excinfo:
        Err("boom").unwrap()
    assert excinfo.value.error == "boom"


def test_expect_on_ok() -> None:
    assert Ok(5).expect("five") == 5


def test_expect_on_err_panics_with_message() -> None:
    with pytest.raises(UnwrapError) as excinfo:
        Err("boom").expect("must succeed")
    assert "must succeed" in str(excinfo.value)


def test_unwrap_or() -> None:
    assert Ok(5).unwrap_or(0) == 5
    assert Err("boom").unwrap_or(0) == 0


def test_unwrap_or_else() -> None:
    assert Ok(5).unwrap_or_else(lambda e: len(e)) == 5
    assert Err("boom").unwrap_or_else(lambda e: len(e)) == 4


def test_is_ok_is_err() -> None:
    assert Ok(1).is_ok() is True
    assert Ok(1).is_err() is False
    assert Err("x").is_ok() is False
    assert Err("x").is_err() is True


def test_attempt_success() -> None:
    assert attempt(lambda: 5) == Ok(5)


def test_attempt_failure() -> None:
    result = attempt(lambda: 1 / 0)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnhandledException)
    assert isinstance(result.error.cause, ZeroDivisionError)


def test_attempt_with_custom_catch() -> None:
    result = attempt(lambda: 1 / 0, catch=lambda e: str(e))
    assert result == Err("division by zero")


def test_attempt_lets_base_exceptions_propagate() -> None:
    # attempt catches Exception only; SystemExit is a control-flow signal,
    # not an expected failure — it must propagate (fail fast).
    with pytest.raises(SystemExit):
        attempt(lambda: (_ for _ in ()).throw(SystemExit("stop")))


def test_attempt_propagates_panics() -> None:
    # A defect is a bug, not an expected failure: attempt must never fold
    # a Panic (such as unwrap() on an Err) into an Err.
    with pytest.raises(UnwrapError):
        attempt(lambda: Err("boom").unwrap())


def test_attempt_propagates_panics_with_custom_catch() -> None:
    with pytest.raises(Panic):
        attempt(lambda: Err("boom").unwrap(), catch=lambda e: "caught")


def test_guard_propagates_panics() -> None:
    def buggy() -> int:
        return Err("boom").unwrap()

    guarded = guard(buggy)
    with pytest.raises(UnwrapError):
        guarded()


def test_guard_decorated_success() -> None:
    guarded = guard(add_one)
    assert guarded(5) == Ok(6)


def test_guard_decorated_failure() -> None:
    def raiser(x: int) -> int:
        raise ValueError(f"bad {x}")

    result = guard(raiser)(1)
    assert isinstance(result, Err)
    assert isinstance(result.error, UnhandledException)
    assert isinstance(result.error.cause, ValueError)


def test_guard_with_custom_catch() -> None:
    def raiser(x: int) -> int:
        raise ValueError(f"bad {x}")

    guarded: Callable[[int], Result[int, str]] = guard(raiser, catch=lambda e: str(e))
    assert guarded(1) == Err("bad 1")


def test_guard_preserves_name_and_docs() -> None:
    @guard
    def documented(x: int) -> int:
        """Adds one."""

        return x + 1

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Adds one."
    assert documented(1) == Ok(2)


def test_fold() -> None:
    assert Ok(5).fold(lambda v: v + 1, lambda e: -1) == 6
    assert Err("boom").fold(lambda v: v + 1, lambda e: -1) == -1


def test_inspect_runs_on_ok() -> None:
    seen: list[int] = []
    result = Ok(2).inspect(seen.append)
    assert result == Ok(2)
    assert seen == [2]


def test_inspect_skips_err() -> None:
    seen: list[int] = []

    def record(x: int) -> None:
        seen.append(x)

    result = Err("boom").inspect(record)
    assert result == Err("boom")
    assert seen == []


def test_inspect_err_runs_on_err() -> None:
    seen: list[str] = []
    result = Err("boom").inspect_err(seen.append)
    assert result == Err("boom")
    assert seen == ["boom"]


def test_inspect_err_skips_ok() -> None:
    seen: list[str] = []
    result = Ok(2).inspect_err(seen.append)
    assert result == Ok(2)
    assert seen == []


def test_contains() -> None:
    assert Ok(2).contains(2) is True
    assert Ok(2).contains(3) is False
    assert Err("boom").contains(2) is False


def test_map_or() -> None:
    assert Ok(5).map_or(0, lambda v: v * 2) == 10
    assert Err("boom").map_or(0, lambda v: v * 2) == 0


def test_map_or_else() -> None:
    assert Ok(5).map_or_else(lambda e: len(e), lambda v: v * 2) == 10
    assert Err("boom").map_or_else(lambda e: len(e), lambda v: v * 2) == 4


def test_zip() -> None:
    assert Ok(1).zip(Ok("a")) == Ok((1, "a"))
    assert Ok(1).zip(Err("boom")) == Err("boom")
    assert Err("boom").zip(Ok(1)) == Err("boom")
    assert Err("boom").zip(Err("first")) == Err("boom")


def test_map2() -> None:
    assert Ok(2).map2(Ok(3), lambda a, b: a * b) == Ok(6)
    assert Ok(2).map2(Err("boom"), lambda a, b: a * b) == Err("boom")
    assert Err("boom").map2(Ok(2), lambda a, b: a * b) == Err("boom")


def test_traverse_all_ok() -> None:
    assert traverse(lambda x: Ok(x * 2), [1, 2, 3]) == Ok([2, 4, 6])


def test_traverse_short_circuits_on_first_err() -> None:
    called: list[int] = []

    def f(x: int) -> Result[int, str]:
        called.append(x)
        return Ok(x) if x != 2 else Err("stop")

    assert traverse(f, [1, 2, 3]) == Err("stop")
    assert called == [1, 2]  # element 3 is never evaluated


def test_traverse_empty_is_ok_empty() -> None:
    assert traverse(lambda x: Ok(x), []) == Ok([])


def test_traverse_accepts_generators() -> None:
    assert traverse(lambda x: Ok(x), (x for x in [1, 2])) == Ok([1, 2])


def test_traverse_rejects_non_result_callback_returns() -> None:
    def broken(x: int) -> Result[int, str]:
        return cast(Result[int, str], 5)

    with pytest.raises(Panic):
        traverse(broken, [1])


def test_context_passes_ok_through() -> None:
    assert Ok(5).context("while parsing") == Ok(5)


def test_context_wraps_error() -> None:
    result = Err("boom").context("while parsing")
    assert isinstance(result, Err)
    assert result.error.message == "while parsing"
    assert result.error.source == "boom"


def test_with_context_is_lazy_on_ok() -> None:
    called = False

    def message(e: object) -> str:
        nonlocal called
        called = True
        return "never"

    assert Ok(5).with_context(message) == Ok(5)
    assert called is False


def test_with_context_runs_on_error() -> None:
    result = Err(3).with_context(lambda e: f"failed with {e}")
    assert isinstance(result, Err)
    assert result.error.message == "failed with 3"
    assert result.error.source == 3


def test_context_chains_nest() -> None:
    result = Err("boom").context("inner").context("outer")
    assert isinstance(result, Err)
    outer = result.error
    assert outer.message == "outer"
    inner = outer.source
    assert isinstance(inner, ErrorContext)
    assert inner.message == "inner"
    assert inner.source == "boom"


def test_and_returns_other_on_ok() -> None:
    assert Ok(1).and_(Ok("a")) == Ok("a")


def test_and_short_circuits_on_err() -> None:
    assert Err("boom").and_(Ok("a")) == Err("boom")


def test_or_keeps_ok() -> None:
    assert Ok(1).or_(Err("other")) == Ok(1)


def test_or_returns_other_on_err() -> None:
    assert Err("boom").or_(Ok(42)) == Ok(42)


def test_flatten_collapses_nested_result() -> None:
    nested_ok: Result[Result[int, str], str] = Ok(Ok(1))
    assert flatten(nested_ok) == Ok(1)
    nested_err: Result[Result[int, str], str] = Ok(Err("boom"))
    assert flatten(nested_err) == Err("boom")
    passthrough: Result[Result[int, str], str] = Err("boom")
    assert flatten(passthrough) == Err("boom")


def test_flatten_rejects_non_results() -> None:
    with pytest.raises(Panic):
        flatten(cast(Result[Result[int, str], str], 5))


def test_transpose_swaps_layers() -> None:
    result_ok: Result[Option[int], str] = Ok(Some(1))
    assert transpose(result_ok) == Some(Ok(1))
    result_none: Result[Option[int], str] = Ok(Nothing())
    assert transpose(result_none) == Nothing()
    result_err: Result[Option[int], str] = Err("boom")
    assert transpose(result_err) == Some(Err("boom"))


def test_transpose_rejects_non_results() -> None:
    with pytest.raises(Panic):
        transpose(cast(Result[Option[int], str], 5))


def test_transpose_rejects_ok_with_non_option_payload() -> None:
    with pytest.raises(Panic):
        transpose(cast(Result[Option[int], str], Ok(5)))


def test_unwrap_error_exposes_context() -> None:
    with pytest.raises(UnwrapError) as excinfo:
        Err("boom").expect("must succeed")
    assert excinfo.value.context == "must succeed"


def test_unwrap_error_is_a_panic() -> None:
    with pytest.raises(Panic) as excinfo:
        Err("boom").unwrap()
    assert isinstance(excinfo.value, UnwrapError)
    assert excinfo.value.cause == "boom"


def test_recover_widens_success_type() -> None:
    result: Result[int, str] = Err("boom")
    recovered = recover(result, lambda e: Ok(len(e)))
    assert recovered == Ok(4)


def test_recover_passes_ok_through() -> None:
    result: Result[int, str] = Ok(5)
    recovered = recover(result, lambda e: Ok("guest"))
    assert recovered == Ok(5)


def test_recover_keeps_error_on_err_recovery() -> None:
    result: Result[int, str] = Err("boom")
    recovered = recover(result, lambda e: Err(e.upper()))
    assert recovered == Err("BOOM")


def test_recover_rejects_non_results() -> None:
    with pytest.raises(Panic):
        recover(cast(Result[int, str], 5), lambda e: Ok(0))


def test_status_discriminant() -> None:
    assert Ok(1).status == "ok"
    assert Err("boom").status == "error"


def test_inspect_both_runs_ok_branch() -> None:
    seen: list[int] = []
    result = Ok(2).inspect_both(seen.append, lambda e: None)
    assert result == Ok(2)
    assert seen == [2]


def test_inspect_both_runs_err_branch() -> None:
    seen: list[str] = []
    result = Err("boom").inspect_both(lambda v: None, seen.append)
    assert result == Err("boom")
    assert seen == ["boom"]


def test_to_dict_envelope() -> None:
    assert Ok(5).to_dict() == {"status": "ok", "value": 5}
    assert Err("boom").to_dict() == {"status": "error", "error": "boom"}
