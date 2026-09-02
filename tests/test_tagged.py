"""Runtime behavior tests for TaggedError and match_error."""

from __future__ import annotations

import pytest

from pyeffect.panic import Panic
from pyeffect.tagged import (
    MatchError,
    TaggedError,
    UnhandledException,
    match_error,
    match_error_partial,
)


class UserNotFound(TaggedError, tag="UserNotFound"):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user {user_id} not found")


class PermissionDenied(TaggedError, tag="PermissionDenied"):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"missing {permission}")


class Unspecified(TaggedError):
    """No explicit tag: defaults to the class name."""


def test_explicit_tag() -> None:
    assert UserNotFound("u").tag == "UserNotFound"


def test_tag_defaults_to_class_name() -> None:
    assert Unspecified().tag == "Unspecified"


def test_base_tagged_error_has_a_default_tag() -> None:
    # The base class carries its own tag, so direct instances are usable.
    assert TaggedError("x").tag == "TaggedError"


def test_is_a_real_exception() -> None:
    err = UserNotFound("u")
    assert isinstance(err, Exception)
    assert str(err) == "user u not found"


def test_is_guard() -> None:
    assert UserNotFound.is_(UserNotFound("u"))
    assert not UserNotFound.is_(PermissionDenied("p"))
    assert TaggedError.is_(UserNotFound("u"))


def test_to_dict() -> None:
    assert UserNotFound("u").to_dict() == {
        "tag": "UserNotFound",
        "message": "user u not found",
    }


def test_match_error_dispatches() -> None:
    result = match_error(
        UserNotFound("u"),
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        },
    )
    assert result == 404


def test_match_error_receives_the_error() -> None:
    result = match_error(
        PermissionDenied("admin"),
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: e.permission,
        },
    )
    assert result == "admin"


def test_match_error_raises_on_unhandled_tag() -> None:
    with pytest.raises(MatchError):
        match_error(UserNotFound("u"), {"PermissionDenied": lambda e: 403})


def test_match_error_partial_falls_back() -> None:
    result = match_error_partial(
        UserNotFound("u"),
        {"PermissionDenied": lambda e: 403},
        lambda e: 500,
    )
    assert result == 500


def test_match_error_partial_handles_known_tag() -> None:
    result = match_error_partial(
        UserNotFound("u"),
        {"UserNotFound": lambda e: 404},
        lambda e: 500,
    )
    assert result == 404


def test_unhandled_exception_preserves_cause() -> None:
    cause = ValueError("boom")
    err = UnhandledException(cause)
    assert err.tag == "UnhandledException"
    assert err.cause is cause
    assert str(err) == "ValueError: boom"


def test_unhandled_exception_to_dict() -> None:
    err = UnhandledException(ValueError("boom"))
    assert err.to_dict() == {
        "tag": "UnhandledException",
        "message": "ValueError: boom",
        "cause": "ValueError: boom",
    }


def test_public_exports() -> None:
    from pyeffect import MatchError, TaggedError, match_error, match_error_partial

    assert TaggedError is not None
    assert MatchError is not None
    assert callable(match_error)
    assert callable(match_error_partial)


def test_match_error_is_a_panic() -> None:
    with pytest.raises(Panic) as excinfo:
        match_error(UserNotFound("u"), {"PermissionDenied": lambda e: 403})
    assert isinstance(excinfo.value, MatchError)
    assert excinfo.value.cause is not None


def test_tagged_error_match_instance_method() -> None:
    result = UserNotFound("u").match(
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        }
    )
    assert result == 404


def test_tagged_error_match_raises_on_missing_tag() -> None:
    with pytest.raises(MatchError):
        UserNotFound("u").match({"PermissionDenied": lambda e: 403})


def test_match_error_data_last() -> None:
    dispatch = match_error(
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        }
    )
    assert dispatch(UserNotFound("u")) == 404


def test_match_error_partial_without_fallback_passes_through() -> None:
    result = match_error_partial(
        UserNotFound("u"),
        {"PermissionDenied": lambda e: 403},
    )
    assert isinstance(result, UserNotFound)
