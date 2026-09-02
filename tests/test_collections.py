"""Runtime behavior tests for result.partition."""

from __future__ import annotations

from typing import cast

import pytest

from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result, partition


def test_partition_splits_ok_and_err() -> None:
    values, errors = partition([Ok(1), Err("a"), Ok(2), Err("b")])
    assert values == [1, 2]
    assert errors == ["a", "b"]


def test_partition_preserves_relative_order() -> None:
    values, errors = partition([Ok(1), Ok(2), Ok(3)])
    assert values == [1, 2, 3]
    assert errors == []


def test_partition_all_errors() -> None:
    values, errors = partition([Err("x"), Err("y")])
    assert values == []
    assert errors == ["x", "y"]


def test_partition_empty() -> None:
    values, errors = partition([])
    assert values == []
    assert errors == []


def test_partition_accepts_a_generator() -> None:
    def results():  # generator: yields Ok/Err
        yield Ok(1)
        yield Err("boom")
        yield Ok(2)

    values, errors = partition(results())
    assert values == [1, 2]
    assert errors == ["boom"]


def test_partition_rejects_non_result_elements() -> None:
    # A non-Result element is a caller bug: panic instead of silently
    # dropping it from both lists.
    with pytest.raises(Panic):
        partition([Ok(1), cast(Result[int, str], 5)])


def test_public_export() -> None:
    from pyeffect import partition

    assert partition([Ok(1), Err("a")]) == ([1], ["a"])
