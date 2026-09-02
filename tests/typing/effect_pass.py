"""Typing fixture: valid Effect calls pinned with assert_type."""

from typing import Any, assert_type

from pyeffect.effect import Effect, sequence
from pyeffect.result import ErrorContext, Ok, Result


def main(n: int, boom: str) -> None:
    # Constructors: the unbound slot is Any, which composes into typed chains.
    assert_type(Effect.success(n), Effect[int, Any])
    assert_type(Effect.failure(boom), Effect[Any, str])

    # map/map_err/and_then/catch preserve or transform the right slot.
    assert_type(Effect.success(n).map(str), Effect[str, Any])
    assert_type(Effect.success(n).map_err(str), Effect[int, str])
    assert_type(
        Effect.success(n).and_then(lambda x: Effect.success(x + 1)),
        Effect[int, Any],
    )
    failing: Effect[int, str] = Effect.failure(boom)
    assert_type(
        failing.catch(lambda e: Effect.success(len(e))),
        Effect[int, Any],
    )

    # Running: run_result keeps the Result; run unwraps to the value.
    assert_type(Effect.success(n).run_result(), Result[int, Any])
    assert_type(Effect.success(n).run(), int)

    # sequence: a list of effects becomes an effect over the list.
    assert_type(sequence([Effect.success(n)]).run_result(), Result[list[int], Any])

    # attempt: the exception boundary, deferred. The default error slot is
    # Exception — concrete, not Any — and catch narrows it exactly.
    assert_type(Effect.attempt(lambda: n).run_result(), Result[int, Exception])
    assert_type(Effect.attempt(lambda: n).run(), int)
    assert_type(
        Effect.attempt(lambda: n, catch=lambda e: str(e)).run_result(),
        Result[int, str],
    )

    # zip/map2 pair two effects that share the error type.
    zipped: Effect[tuple[int, str], str] = failing.zip(Effect.success("a"))
    assert_type(zipped, Effect[tuple[int, str], str])
    mapped2: Effect[str, str] = failing.map2(
        Effect.success("a"), lambda a, b: str(a) + b
    )
    assert_type(mapped2, Effect[str, str])

    # context attaches a message to the failure, preserving the source.
    ctx_effect: Effect[int, ErrorContext] = failing.context("while parsing")
    assert_type(ctx_effect, Effect[int, ErrorContext])
    ctx_lazy: Effect[int, ErrorContext] = failing.with_context(lambda e: f"failed: {e}")
    assert_type(ctx_lazy, Effect[int, ErrorContext])

    # ok/err: the unbound slot of success/failure is Any (documented); a
    # binding annotation anchors both slots with full precision.
    anchored: Effect[int, str] = Effect.success(n)
    assert_type(anchored, Effect[int, str])

    # inspect/inspect_err: lazy tap, preserving both slots.
    insp: Effect[int, str] = failing.inspect(lambda v: None)
    assert_type(insp, Effect[int, str])
    insp_err: Effect[int, str] = failing.inspect_err(lambda e: None)
    assert_type(insp_err, Effect[int, str])

    # map_or/map_or_else: lazy default on failure.
    assert_type(failing.map_or(0, lambda v: v + 1), Effect[int, str])
    assert_type(
        failing.map_or_else(lambda e: len(e), lambda v: v + 1), Effect[int, str]
    )

    # and_/or_: eager keep-other / keep-self combinators.
    and_effect: Effect[str, str] = failing.and_(Effect.success("a"))
    assert_type(and_effect, Effect[str, str])
    or_effect: Effect[int, str] = failing.or_(Effect.success(n))
    assert_type(or_effect, Effect[int, str])

    # flatten: collapse a nested effect; the inner effect runs when run.
    nested: Effect[Effect[int, str], str] = Effect(lambda: Ok(failing))
    flat_effect: Effect[int, str] = nested.flatten()
    assert_type(flat_effect, Effect[int, str])
