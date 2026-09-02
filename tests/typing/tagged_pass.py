"""Typing fixture: TaggedError tags, isinstance narrowing, match dispatch."""

from typing import Any, assert_type

from pyeffect.tagged import TaggedError, match_error, match_error_partial


class UserNotFound(TaggedError, tag="UserNotFound"):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user {user_id} not found")


class PermissionDenied(TaggedError, tag="PermissionDenied"):
    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"missing {permission}")


def narrow(error: UserNotFound | PermissionDenied) -> str:
    # isinstance narrows the union; the else branch is PermissionDenied.
    if isinstance(error, UserNotFound):
        return error.user_id
    return error.permission


def main() -> None:
    assert_type(UserNotFound("u").tag, str)
    assert_type(UserNotFound("u").to_dict(), dict[str, Any])
    assert_type(narrow(UserNotFound("u")), str)

    # match_error returns the handler result type.
    status = match_error(
        UserNotFound("u"),
        {
            "UserNotFound": lambda e: 404,
            "PermissionDenied": lambda e: 403,
        },
    )
    assert_type(status, int)

    recovered: str = match_error_partial(
        UserNotFound("u"),
        {"UserNotFound": lambda e: "not-found"},
        lambda e: "other",
    )
    assert_type(recovered, str)
