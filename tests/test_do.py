"""Runtime behavior tests for do-notation and do_effect."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyeffect.do import do
from pyeffect.effect import Effect, do_effect
from pyeffect.option import Nothing, Some
from pyeffect.panic import PanicError
from pyeffect.result import Err, Ok, Result

if TYPE_CHECKING:
    from collections.abc import Generator


def load_cart(cart_id: str) -> Result[dict[str, int], str]:
    return Ok({"items": 2})


def reserve_stock(items: dict[str, int]) -> Result[int, str]:
    return Ok(items["items"])


def test_do_result_binds_values() -> None:
    result = do(
        Ok(f"order:{stock}")
        for cart in load_cart("c1")
        for stock in reserve_stock(cart)
    )
    assert result == Ok("order:2")


def test_do_result_short_circuits_on_err() -> None:
    result = do(Ok(1) for _ in Err("boom"))
    assert result == Err("boom")


def test_do_result_short_circuit_skips_later_steps() -> None:
    calls: list[str] = []

    def fail() -> Result[int, str]:
        calls.append("fail")
        return Err("boom")

    def never() -> Result[int, str]:
        calls.append("never")
        return Ok(1)

    result = do(never() for _ in fail())
    assert result == Err("boom")
    assert calls == ["fail"]


def test_do_option_binds_values() -> None:
    result = do(
        Some(stock) for cart in Some({"items": 2}) for stock in Some(cart["items"])
    )
    assert result == Some(2)


def test_do_option_short_circuits_on_nothing() -> None:
    result = do(Some(1) for _ in Nothing())
    assert result == Nothing()


def test_do_rejects_zero_yields() -> None:
    with pytest.raises(PanicError):
        do(Ok(x) for x in Ok(1) if False)


def _two_results() -> Generator[Result[int, str], None, None]:
    yield Ok(1)
    yield Ok(2)


def test_do_rejects_multiple_yields() -> None:
    with pytest.raises(PanicError):
        do(_two_results())


def test_do_effect_is_lazy() -> None:
    calls: list[str] = []

    def step() -> Effect[int, str]:
        calls.append("ran")
        return Effect.success(1)

    effect = do_effect(lambda: (Effect.success(f"v={x}") for x in step()))
    assert calls == []
    assert effect.run() == "v=1"
    assert calls == ["ran"]


def test_do_effect_is_re_runnable() -> None:
    calls: list[str] = []

    def step() -> Effect[int, str]:
        calls.append("ran")
        return Effect.success(1)

    effect = do_effect(lambda: (Effect.success(f"v={x}") for x in step()))
    assert effect.run() == "v=1"
    assert effect.run() == "v=1"
    assert calls == ["ran", "ran"]


def test_do_effect_short_circuits() -> None:
    effect = do_effect(
        lambda: (Effect.success("never") for _ in Effect.failure("nope"))
    )
    assert effect.run_result() == Err("nope")


def _two_effects() -> Generator[Effect[int, str], None, None]:
    yield Effect.success(1)
    yield Effect.success(2)


def test_do_effect_rejects_multiple_yields() -> None:
    effect = do_effect(_two_effects)
    with pytest.raises(PanicError):
        effect.run()


def test_do_effect_rejects_zero_yields() -> None:
    effect = do_effect(lambda: (Effect.success(x) for x in Effect.success(1) if False))
    with pytest.raises(PanicError):
        effect.run()


def test_public_exports() -> None:
    from pyeffect import do, do_effect

    assert callable(do)
    assert callable(do_effect)
