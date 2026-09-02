"""Typing fixture: TaggedError tags, isinstance narrowing, match dispatch."""

from __future__ import annotations

from typing import Any, assert_type

from pyeffect.tagged import TaggedError, match_error, match_error_partial


class UserNotFoundError(TaggedError, tag="UserNotFound"):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user {user_id} not found")


class PermissionDeniedError(TaggedError, tag="PermissionDenied"):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"missing {permission}")


def narrow(error: UserNotFoundError | PermissionDeniedError) -> str:
    # isinstance narrows the union; the else branch is PermissionDenied.
    if isinstance(error, UserNotFoundError):
        return error.user_id
    return error.permission


def main() -> None:
    assert_type(UserNotFoundError("u").tag, str)
    assert_type(UserNotFoundError("u").to_dict(), dict[str, Any])
    assert_type(narrow(UserNotFoundError("u")), str)

    # match_error returns the handler result type.
    status = match_error(
        UserNotFoundError("u"),
        {
            "UserNotFound": lambda _: 404,
            "PermissionDenied": lambda _: 403,
        },
    )
    assert_type(status, int)

    recovered: str = match_error_partial(
        UserNotFoundError("u"),
        {"UserNotFound": lambda _: "not-found"},
        lambda _: "other",
    )
    assert_type(recovered, str)
