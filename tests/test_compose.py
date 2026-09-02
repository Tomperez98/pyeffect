"""Runtime behavior tests for compose, tap, and the small combinators."""

from __future__ import annotations

import pytest

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
from pyeffect.panic import Panic
from pyeffect.pipe import pipe
from pyeffect.result import Err, Ok


def add_one(x: int) -> int:
    return x + 1


def double(x: int) -> int:
    return x * 2


def to_str(x: int) -> str:
    return str(x)


def test_compose_applies_right_to_left() -> None:
    assert compose(to_str, double, add_one)(3) == "8"  # to_str(double(add_one(3)))


def test_compose_matches_nested_calls() -> None:
    value = 3
    assert compose(to_str, double, add_one)(value) == to_str(double(add_one(value)))


def test_compose_empty_is_identity() -> None:
    assert compose()(5) == 5
    assert compose()("x") == "x"
    value = [1, 2]
    assert compose()(value) is value


def test_compose_single_function() -> None:
    assert compose(add_one)(5) == 6
    assert compose(to_str)(1) == "1"


def test_compose_ten_functions_is_the_typed_limit() -> None:
    assert (
        compose(
            add_one,
            add_one,
            add_one,
            add_one,
            add_one,
            add_one,
            add_one,
            add_one,
            add_one,
            add_one,
        )(0)
        == 10
    )


def test_compose_works_in_a_pipe() -> None:
    assert pipe(2, compose(add_one, double)) == 5  # add_one(double(2)) = 5


def test_tap_runs_side_effect_and_passes_value_through() -> None:
    seen: list[int] = []
    result = tap(seen.append)(5)
    assert result == 5
    assert seen == [5]


def test_tap_discards_side_effect_return() -> None:
    result = tap(lambda x: x * 100)(3)
    assert result == 3


def test_tap_in_a_pipe() -> None:
    seen: list[int] = []
    result = pipe(2, add_one, tap(seen.append), double)
    assert result == 6
    assert seen == [3]


def test_identity_returns_value() -> None:
    assert identity(5) == 5
    value = [1, 2]
    assert identity(value) is value


def test_constant_ignores_arguments() -> None:
    const = constant(42)
    assert const(1) == 42
    assert const("anything", key=1) == 42


def subtract(a: int, b: int) -> int:
    return a - b


def add(a: int, b: int) -> int:
    return a + b


def single(x: int) -> str:
    return str(x)


def test_flip_swaps_binary_arguments() -> None:
    assert flip(subtract)(3, 10) == 7  # subtract(10, 3)


def test_unpack_applies_function_to_tuple() -> None:
    assert unpack(add)((2, 3)) == 5
    assert unpack(single)((5,)) == "5"


def test_curry_applies_left_to_right() -> None:
    assert curry(lambda a, b: a + b)(2)(3) == 5


def test_curry_three_steps() -> None:
    assert curry(lambda a, b, c: a + b + c)(1)(2)(3) == 6


def test_curry_accepts_multiple_args_per_step() -> None:
    # The typed contract is one argument per step; the runtime also accepts
    # several at once. The splat form bypasses ty's arity check, keeping
    # this a pure runtime test (the typed limit is pinned by the fixtures).
    args = [1, 2]
    assert curry(lambda a, b, c: a + b + c)(*args)(3) == 6


def test_curry_unary() -> None:
    assert curry(lambda a: a * 2)(3) == 6


def test_curry_zero_arity() -> None:
    assert curry(lambda: 42)() == 42


def test_curry_rejects_variadic() -> None:
    with pytest.raises(Panic):
        curry(lambda *args: sum(args))


def test_curry_rejects_required_keyword_only() -> None:
    def needs_kw(a: int, *, b: int) -> int:
        return a + b

    with pytest.raises(Panic):
        curry(needs_kw)  # ty: ignore[no-matching-overload]


def test_lift_maps_over_result() -> None:
    assert lift(add_one)(Ok(5)) == Ok(6)
    assert lift(add_one)(Err("boom")) == Err("boom")


def test_lift2_applies_binary() -> None:
    add2 = lift2(lambda a, b: a + b)
    assert add2(Ok(1), Ok(2)) == Ok(3)
    assert add2(Err("boom"), Ok(2)) == Err("boom")
    assert add2(Ok(1), Err("boom")) == Err("boom")


def test_lift2_fails_fast_on_first_error() -> None:
    assert lift2(lambda a, b: a + b)(Err("first"), Err("second")) == Err("first")


def test_lift3_applies_ternary() -> None:
    add3 = lift3(lambda a, b, c: a + b + c)
    assert add3(Ok(1), Ok(2), Ok(3)) == Ok(6)
    assert add3(Ok(1), Err("boom"), Ok(3)) == Err("boom")


def test_partial_is_functools_partial() -> None:
    from functools import partial as stdlib_partial

    assert partial is stdlib_partial
    assert partial(add_one, 1)() == 2
