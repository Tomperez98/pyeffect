"""Runtime behavior tests for PanicError: the unified defect type."""

from __future__ import annotations

import pytest

from pyeffect.panic import PanicError, is_panic, panic


def test_panic_is_an_exception() -> None:
    assert issubclass(PanicError, Exception)


def test_panic_carries_message_and_cause() -> None:
    err = PanicError("broken invariant", cause="the-cause")
    assert str(err) == "broken invariant"
    assert err.cause == "the-cause"
    assert err.tag == "Panic"


def test_panic_is_guard() -> None:
    assert PanicError.is_(PanicError("x"))
    assert is_panic(PanicError("x"))
    assert not is_panic(ValueError("x"))


def test_panic_to_dict() -> None:
    err = PanicError("broken", cause=ValueError("inner"))
    assert err.to_dict() == {
        "tag": "Panic",
        "message": "broken",
        "cause": "ValueError: inner",
    }


def test_panic_helper_raises() -> None:
    with pytest.raises(PanicError) as excinfo:
        panic("unreachable", cause=42)
    assert excinfo.value.cause == 42
