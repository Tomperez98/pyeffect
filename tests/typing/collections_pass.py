"""Typing fixture: partition returns typed (values, errors) lists."""

from __future__ import annotations

from typing import assert_type

from pyeffect.result import Err, Ok, Result, partition


def main() -> None:
    results: list[Result[int, str]] = [Ok(1), Err("a"), Ok(2), Err("b")]

    values, errors = partition(results)
    assert_type(values, list[int])
    assert_type(errors, list[str])

    # The success and error types follow from the input element type.
    mixed = partition([Ok(1.5), Err("x")])
    assert_type(mixed, tuple[list[float], list[str]])
