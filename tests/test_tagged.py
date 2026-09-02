"""Runtime behavior tests for TaggedError and match_error."""

from __future__ import annotations

import pytest

from pyeffect.panic import PanicError
from pyeffect.tagged import (
    MatchError,
    TaggedError,
    UnhandledError,
    match_error,
    match_error_partial,
)


class UserNotFoundError(TaggedError, tag="UserNotFound"):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user {user_id} not found")


class PermissionDeniedError(TaggedError, tag="PermissionDenied"):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"missing {permission}")


class UnspecifiedError(TaggedError):
    """No explicit tag: defaults to the class name."""


def test_explicit_tag() -> None:
    assert UserNotFoundError("u").tag == "UserNotFound"


def test_tag_defaults_to_class_name() -> None:
    assert UnspecifiedError().tag == "UnspecifiedError"


def test_base_tagged_error_has_a_default_tag() -> None:
    # The base class carries its own tag, so direct instances are usable.
    assert TaggedError("x").tag == "TaggedError"


def test_is_a_real_exception() -> None:
    err = UserNotFoundError("u")
    assert isinstance(err, Exception)
    assert str(err) == "user u not found"


def test_is_guard() -> None:
    assert UserNotFoundError.is_(UserNotFoundError("u"))
    assert not UserNotFoundError.is_(PermissionDeniedError("p"))
    assert TaggedError.is_(UserNotFoundError("u"))


def test_to_dict() -> None:
    assert UserNotFoundError("u").to_dict() == {
        "tag": "UserNotFound",
        "message": "user u not found",
    }


def test_match_error_dispatches() -> None:
    result = match_error(
        UserNotFoundError("u"),
        {
            "UserNotFound": lambda _: 404,
            "PermissionDenied": lambda _: 403,
        },
    )
    assert result == 404


def test_match_error_receives_the_error() -> None:
    result = match_error(
        PermissionDeniedError("admin"),
        {
            "UserNotFound": lambda _: 404,
            "PermissionDenied": lambda e: e.permission,
        },
    )
    assert result == "admin"


def test_match_error_raises_on_unhandled_tag() -> None:
    with pytest.raises(MatchError):
        match_error(UserNotFoundError("u"), {"PermissionDenied": lambda _: 403})


def test_match_error_partial_falls_back() -> None:
    result = match_error_partial(
        UserNotFoundError("u"),
        {"PermissionDenied": lambda _: 403},
        lambda _: 500,
    )
    assert result == 500


def test_match_error_partial_handles_known_tag() -> None:
    result = match_error_partial(
        UserNotFoundError("u"),
        {"UserNotFound": lambda _: 404},
        lambda _: 500,
    )
    assert result == 404


def test_unhandled_exception_preserves_cause() -> None:
    cause = ValueError("boom")
    err = UnhandledError(cause)
    assert err.tag == "UnhandledException"
    assert err.cause is cause
    assert str(err) == "ValueError: boom"


def test_unhandled_exception_to_dict() -> None:
    err = UnhandledError(ValueError("boom"))
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
    with pytest.raises(PanicError) as excinfo:
        match_error(UserNotFoundError("u"), {"PermissionDenied": lambda _: 403})
    assert isinstance(excinfo.value, MatchError)
    assert excinfo.value.cause is not None


def test_tagged_error_match_instance_method() -> None:
    result = UserNotFoundError("u").match(
        {
            "UserNotFound": lambda _: 404,
            "PermissionDenied": lambda _: 403,
        }
    )
    assert result == 404


def test_tagged_error_match_raises_on_missing_tag() -> None:
    with pytest.raises(MatchError):
        UserNotFoundError("u").match({"PermissionDenied": lambda _: 403})


def test_match_error_data_last() -> None:
    dispatch = match_error(
        {
            "UserNotFound": lambda _: 404,
            "PermissionDenied": lambda _: 403,
        }
    )
    assert dispatch(UserNotFoundError("u")) == 404


def test_match_error_partial_without_fallback_passes_through() -> None:
    result = match_error_partial(
        UserNotFoundError("u"),
        {"PermissionDenied": lambda _: 403},
    )
    assert isinstance(result, UserNotFoundError)
