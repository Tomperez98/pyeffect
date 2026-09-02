"""Runtime behavior tests for :func:`pyeffect.pipe`.

The pipe contract: value flows through the steps left to right, each step
receives exactly one positional argument, and misuse is a defect that must
crash (TypeError), never a silently wrong result.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

import pytest

from pyeffect import pipe


def add_one(x: int) -> int:
    return x + 1


def double(x: int) -> int:
    return x * 2


def to_str(x: int) -> str:
    return str(x)


def scale(x: int, factor: int = 2) -> int:
    return x * factor


class Counter:
    """Callable object usable as a pipe step; records every input."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[int] = []

    def __call__(self, x: int) -> int:
        self.calls.append(x)
        return x + 1


def record(label: str) -> Callable[[int], int]:
    """A step that appends its label to a shared list, then passes through."""

    def step(x: int) -> int:
        calls.append(label)
        return x

    return step


calls: list[str] = []


def test_identity_with_no_functions() -> None:
    assert pipe(5) == 5
    assert pipe("x") == "x"
    assert pipe(None) is None


def test_identity_returns_the_same_object() -> None:
    value = [1, 2, 3]
    assert pipe(value) is value


def test_single_function() -> None:
    assert pipe(2, double) == 4


def test_chain_equals_nested_calls() -> None:
    value = 3
    assert pipe(value, double, add_one, to_str) == to_str(add_one(double(value)))


def test_steps_run_left_to_right() -> None:
    assert pipe(1, add_one, double) == 4  # (1 + 1) * 2
    assert pipe(1, double, add_one) == 3  # (1 * 2) + 1


def test_steps_run_in_given_order() -> None:
    calls.clear()
    pipe(0, record("a"), record("b"), record("c"))
    assert calls == ["a", "b", "c"]


def test_each_step_receives_the_previous_output() -> None:
    counter = Counter("c")
    pipe(1, counter, counter, counter)
    assert counter.calls == [1, 2, 3]


def test_ten_functions_is_the_typed_limit() -> None:
    # Ten is the deepest arity the overloads type-check; it must work.
    assert (
        pipe(
            0,
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
        )
        == 10
    )


def test_runtime_accepts_more_than_ten_steps() -> None:
    # Static checkers reject >10 explicit steps (no dependent variadic types);
    # the runtime contract accepts any count. The splat form bypasses ty's
    # arity check, keeping this a pure runtime test — the static limit is
    # pinned by tests/typing/pipe_fail_arity.py.
    steps = [add_one] * 11
    assert pipe(0, *steps) == 11


def test_accepts_bound_methods() -> None:
    assert pipe("hello", "hello".count) == 1


def test_accepts_callable_objects() -> None:
    assert pipe(2, Counter("c"), to_str) == "3"


def test_accepts_functools_partial() -> None:
    assert pipe(4, partial(scale, factor=3), to_str) == "12"


def test_accepts_builtins() -> None:
    assert pipe([3, 1, 2], sorted, len) == 3


def test_accepts_any_value_type() -> None:
    assert pipe({"a": 1}, len) == 1
    assert pipe(3.5, int) == 3


def test_does_not_mutate_the_input() -> None:
    data = [3, 1, 2]
    assert pipe(data, sorted, list) == [1, 2, 3]
    assert data == [3, 1, 2]


def test_step_exception_propagates_unchanged() -> None:
    marker = ValueError("boom")

    def failing(_: int) -> int:
        raise marker

    with pytest.raises(ValueError) as excinfo:
        pipe(1, add_one, failing, double)
    assert excinfo.value is marker


def test_later_steps_do_not_run_after_a_step_fails() -> None:
    calls.clear()

    def failing(_: int) -> int:
        calls.append("failing")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        pipe(0, record("a"), failing, record("b"))

    assert calls == ["a", "failing"]


@pytest.mark.parametrize(
    "steps",
    [
        (42,),
        (add_one, 42),
        (add_one, 42, double),
        (42, add_one),
    ],
)
def test_non_callable_step_is_a_defect_and_crashes(steps: tuple[object, ...]) -> None:
    with pytest.raises(TypeError):
        pipe(1, *steps)
