"""Typing fixture: do/do_effect pin the success type through every step."""

from typing import assert_type

from pyeffect import Effect, Err, Nothing, Ok, Option, Result, Some, do, do_effect


def load_cart(cart_id: str) -> Result[dict[str, int], str]:
    return Ok({"items": 2})


def reserve_stock(items: dict[str, int]) -> Result[int, str]:
    return Ok(items["items"])


def main() -> None:
    # Result: the success type flows precisely; the error slot is not
    # inferable from a generator expression (documented limitation).
    result = do(
        Ok(f"order:{stock}")
        for cart in load_cart("c1")
        for stock in reserve_stock(cart)
    )
    assert_type(result.unwrap(), str)

    # Option: fully precise — Option has no error slot to infer.
    option = do(
        Some(stock) for cart in Some({"items": 2}) for stock in Some(cart["items"])
    )
    assert_type(option, Option[int])

    # Effect: success type flows; the effect stays lazy and re-runnable.
    effect = do_effect(
        lambda: (Effect.success(f"order:{stock}") for stock in Effect.success(2))
    )
    assert_type(effect.run(), str)


def short_circuit() -> None:
    # Short-circuiting still type-checks: Err/Nothing flow as their variant.
    r = do(Ok(1) for _ in Err("boom"))
    assert_type(r.unwrap(), int)

    o = do(Some(1) for _ in Nothing())
    assert_type(o, Option[int])
