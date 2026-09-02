"""Runtime behavior tests for Effect: laziness, composition, running."""

from __future__ import annotations

from typing import cast

import pytest

from pyeffect.effect import Effect, sequence
from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result, UnwrapError
from pyeffect.retry import Policy
from pyeffect.tagged import UnhandledException


def test_effect_is_lazy_until_run() -> None:
    runs: list[int] = []

    def thunk() -> Result[int, str]:
        runs.append(1)
        return Ok(42)

    effect = Effect(thunk)
    assert runs == []  # construction runs nothing

    composed = effect.map(lambda x: x + 1)
    assert runs == []  # composition runs nothing

    assert composed.run() == 43
    assert runs == [1]


def test_success_and_failure() -> None:
    assert Effect.success(5).run() == 5
    assert Effect.failure("boom").run_result() == Err("boom")


def test_map() -> None:
    assert Effect.success(2).map(add_one).run() == 3


def test_map_passes_failure_through() -> None:
    assert Effect.failure("boom").map(add_one).run_result() == Err("boom")


def test_and_then_chains() -> None:
    result = (
        Effect.success(2)
        .and_then(lambda x: Effect.success(x + 1))
        .and_then(lambda x: Effect.success(x * 10))
    )
    assert result.run() == 30


def test_and_then_short_circuits_on_failure() -> None:
    effect: Effect[int, str] = Effect.failure("boom")
    called = False

    def never(x: int) -> Effect[int, str]:
        nonlocal called
        called = True
        return Effect.success(x)

    assert effect.and_then(never).run_result() == Err("boom")
    assert called is False


def test_catch_recovers() -> None:
    effect: Effect[int, str] = Effect.failure("boom")
    recovered = effect.catch(lambda e: Effect.success(len(e)))
    assert recovered.run() == 4


def test_catch_passes_success_through() -> None:
    assert Effect.success(5).catch(lambda e: Effect.failure(e)).run() == 5


def test_map_err() -> None:
    assert Effect.failure(1).map_err(str).run_result() == Err("1")
    assert Effect.success(5).map_err(str).run() == 5


def test_retry_within_effect() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def flaky() -> Result[int, str]:
        attempts.append(1)
        if len(attempts) < 3:
            return Err("not yet")
        return Ok(len(attempts))

    effect = Effect(flaky).retry(Policy(max_attempts=5), sleep=sleeps.append)
    assert effect.run() == 3
    assert attempts == [1, 1, 1]
    assert sleeps == [0.0, 0.0]


def test_run_panics_on_failure() -> None:
    with pytest.raises(UnwrapError):
        Effect.failure("boom").run()


def test_run_result() -> None:
    assert Effect.success(1).run_result() == Ok(1)
    assert Effect.failure("x").run_result() == Err("x")


def test_effects_are_re_runnable() -> None:
    effect = Effect.success(1).map(add_one)
    assert effect.run() == 2
    assert effect.run() == 2


def test_sequence_all_ok() -> None:
    effects = [Effect.success(1), Effect.success(2), Effect.success(3)]
    assert sequence(effects).run() == [1, 2, 3]


def test_sequence_short_circuits_on_first_failure() -> None:
    runs: list[int] = []

    def record(x: int) -> Effect[int, str]:
        def thunk() -> Result[int, str]:
            runs.append(x)
            return Ok(x)

        return Effect(thunk)

    effects = [record(1), Effect.failure("boom"), record(3)]
    result = sequence(effects).run_result()

    assert result == Err("boom")
    assert runs == [1]  # the third effect never ran


def test_sequence_materializes_generators() -> None:
    effects = (Effect.success(x) for x in range(3))
    sequenced = sequence(effects)
    assert sequenced.run() == [0, 1, 2]
    assert sequenced.run() == [0, 1, 2]  # re-runnable even from a generator


def test_sequence_rejects_non_result_thunks() -> None:
    garbage: Effect[int, str] = Effect(lambda: cast(Result[int, str], 5))
    with pytest.raises(Panic):
        sequence([Effect.success(1), garbage]).run_result()


def add_one(x: int) -> int:
    return x + 1


def test_attempt_success() -> None:
    assert Effect.attempt(lambda: 5).run() == 5


def test_attempt_failure() -> None:
    result = Effect.attempt(lambda: 1 / 0).run_result()
    assert isinstance(result, Err)
    assert isinstance(result.error, UnhandledException)
    assert isinstance(result.error.cause, ZeroDivisionError)


def test_attempt_with_custom_catch() -> None:
    result = Effect.attempt(lambda: 1 / 0, catch=lambda e: str(e)).run_result()
    assert result == Err("division by zero")


def test_attempt_is_lazy_until_run() -> None:
    runs: list[int] = []

    def thunk() -> int:
        runs.append(1)
        return 42

    effect = Effect.attempt(thunk)
    assert runs == []
    assert effect.run() == 42
    assert runs == [1]


def test_attempt_lets_base_exceptions_propagate() -> None:
    with pytest.raises(SystemExit):
        Effect.attempt(lambda: (_ for _ in ()).throw(SystemExit("stop"))).run()


def test_effect_attempt_propagates_panics() -> None:
    # A defect inside the attempted thunk is a bug, not an expected
    # failure: it must propagate when the effect runs.
    effect = Effect.attempt(lambda: Err("boom").unwrap())
    with pytest.raises(UnwrapError):
        effect.run_result()


def test_zip_pairs_values() -> None:
    assert Effect.success(1).zip(Effect.success("a")).run() == (1, "a")


def test_zip_fails_on_first_error() -> None:
    assert Effect.failure("boom").zip(Effect.success(1)).run_result() == Err("boom")


def test_zip_fails_on_second_error() -> None:
    assert Effect.success(1).zip(Effect.failure("boom")).run_result() == Err("boom")


def test_zip_skips_second_thunk_when_first_fails() -> None:
    runs: list[int] = []

    def record() -> Result[int, str]:
        runs.append(1)
        return Ok(1)

    effect: Effect[int, str] = Effect.failure("boom")
    result = effect.zip(Effect(record)).run_result()
    assert result == Err("boom")
    assert runs == []  # the second thunk never runs


def test_zip_runs_both_thunks_in_order() -> None:
    order: list[str] = []

    def first() -> Result[int, str]:
        order.append("first")
        return Ok(1)

    def second() -> Result[str, str]:
        order.append("second")
        return Ok("a")

    assert Effect(first).zip(Effect(second)).run() == (1, "a")
    assert order == ["first", "second"]


def test_zip_rejects_non_result_thunks() -> None:
    good: Effect[int, str] = Effect.success(1)
    garbage: Effect[int, str] = Effect(lambda: cast(Result[int, str], 5))
    with pytest.raises(Panic):
        garbage.zip(good).run_result()
    with pytest.raises(Panic):
        good.zip(garbage).run_result()


def test_map2_applies_function() -> None:
    assert Effect.success(2).map2(Effect.success(3), lambda a, b: a * b).run() == 6


def test_map2_fails_on_first_error() -> None:
    result = Effect.failure("boom").map2(Effect.success(2), lambda a, b: a * b)
    assert result.run_result() == Err("boom")


def test_map2_fails_on_second_error() -> None:
    result = Effect.success(2).map2(Effect.failure("boom"), lambda a, b: a * b)
    assert result.run_result() == Err("boom")


def test_map2_rejects_non_result_thunks() -> None:
    good: Effect[int, str] = Effect.success(1)
    garbage: Effect[int, str] = Effect(lambda: cast(Result[int, str], 5))
    with pytest.raises(Panic):
        garbage.map2(good, lambda a, b: a + b).run_result()
    with pytest.raises(Panic):
        good.map2(garbage, lambda a, b: a + b).run_result()


def test_effect_context_wraps_failure() -> None:
    result = Effect.failure("boom").context("while parsing").run_result()
    assert isinstance(result, Err)
    assert result.error.message == "while parsing"
    assert result.error.source == "boom"


def test_effect_context_passes_success_through() -> None:
    assert Effect.success(5).context("while parsing").run() == 5


def test_inspect_runs_on_success() -> None:
    seen: list[int] = []
    assert Effect.success(2).inspect(seen.append).run() == 2
    assert seen == [2]


def test_inspect_skips_failure() -> None:
    seen: list[int] = []
    effect: Effect[int, str] = Effect.failure("boom")
    assert effect.inspect(seen.append).run_result() == Err("boom")
    assert seen == []


def test_inspect_err_runs_on_failure() -> None:
    seen: list[str] = []
    effect: Effect[int, str] = Effect.failure("boom")
    assert effect.inspect_err(seen.append).run_result() == Err("boom")
    assert seen == ["boom"]


def test_map_or_on_success_and_failure() -> None:
    assert Effect.success(2).map_or(0, lambda x: x + 1).run() == 3
    effect: Effect[int, str] = Effect.failure("boom")
    assert effect.map_or(0, lambda x: x + 1).run() == 0


def test_map_or_else_on_failure() -> None:
    effect: Effect[int, str] = Effect.failure("boom")
    assert effect.map_or_else(lambda e: len(e), lambda x: x + 1).run() == 4


def test_and_returns_other_effect_on_success() -> None:
    assert Effect.success(1).and_(Effect.success("a")).run() == "a"
    effect: Effect[int, str] = Effect.failure("boom")
    assert effect.and_(Effect.success("a")).run_result() == Err("boom")


def test_or_returns_other_effect_on_failure() -> None:
    effect: Effect[int, str] = Effect.failure("boom")
    assert effect.or_(Effect.success(42)).run() == 42
    assert Effect.success(1).or_(Effect.success(42)).run() == 1


def test_flatten_collapses_nested_effect() -> None:
    nested: Effect[Effect[int, str], str] = Effect(lambda: Ok(Effect.success(1)))
    assert nested.flatten().run() == 1
    nested_err: Effect[Effect[int, str], str] = Effect(
        lambda: Ok(Effect.failure("boom"))
    )
    assert nested_err.flatten().run_result() == Err("boom")
    outer_err: Effect[Effect[int, str], str] = Effect.failure("outer")
    assert outer_err.flatten().run_result() == Err("outer")


def test_flatten_rejects_non_result_thunks() -> None:
    garbage: Effect[Effect[int, str], str] = Effect(
        lambda: cast(Result[Effect[int, str], str], 5)
    )
    with pytest.raises(Panic):
        garbage.flatten().run_result()


def test_recover_widens_effect_success_type() -> None:
    effect: Effect[int, str] = Effect.failure("boom")
    recovered = effect.recover(lambda e: Effect.success(len(e)))
    assert recovered.run_result() == Ok(4)
