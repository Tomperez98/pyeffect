"""Serialization boundary for :data:`~pyeffect.result.Result`.

A ``Result`` in memory is not proof that JSON or stored data has the same
shape. A :class:`Codec` validates both the envelope and its payloads, while
allowing in-memory and wire representations to differ (e.g. ``date`` objects
vs ISO text). Zero dependencies: "schemas" are plain functions.

The wire envelope is one of::

    {"status": "ok", "value": <encoded value>}
    {"status": "error", "error": <encoded error>}
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pyeffect.panic import Panic
from pyeffect.result import Err, Ok, Result
from pyeffect.tagged import TaggedError

__all__ = [
    "Codec",
    "ResultDeserializationError",
    "ResultSerializationError",
    "from_dict",
]

# The wire discriminator is owned by the variants themselves
# (``Ok.status``/``Err.status``) — round-trips silently break if this
# copy drifts, so alias the class attributes instead of duplicating
# the literals.
_STATUS_OK = Ok.status
_STATUS_ERROR = Err.status


class ResultSerializationError(TaggedError, tag="ResultSerializationError"):
    """A payload failed to encode to its wire form."""

    def __init__(
        self, value: object, message: str = "could not serialize value"
    ) -> None:
        self.value = value
        super().__init__(message)


class ResultDeserializationError(TaggedError, tag="ResultDeserializationError"):
    """An envelope or payload failed to decode from its wire form."""

    def __init__(
        self, value: object, message: str = "could not deserialize value"
    ) -> None:
        self.value = value
        super().__init__(message)


def from_dict(data: object) -> Result[Any, ResultDeserializationError]:
    """Decode a bare envelope without payload validation.

    Use a :class:`Codec` when payloads need validation or mapping; this only
    checks the envelope shape and returns payloads as-is.
    """

    if not isinstance(data, dict):
        return Err(ResultDeserializationError(data))
    status = data.get("status")
    if status == _STATUS_OK and "value" in data:
        return Ok(data["value"])
    if status == _STATUS_ERROR and "error" in data:
        return Err(data["error"])
    return Err(ResultDeserializationError(data))


@dataclass(frozen=True, slots=True)
class Codec[T, E]:
    """Maps a ``Result[T, E]`` to and from a ``{"status", ...}`` envelope.

    Attributes:
        encode_ok: ``T -> wire`` for success payloads (may raise; caught as a
            serialization error).
        encode_err: ``E -> wire`` for error payloads.
        decode_ok: ``wire -> Result[T, Any]`` for success payloads.
        decode_err: ``wire -> Result[E, Any]`` for error payloads.
    """

    encode_ok: Callable[[T], object]
    encode_err: Callable[[E], object]
    decode_ok: Callable[[object], Result[T, Any]]
    decode_err: Callable[[object], Result[E, Any]]

    def serialize(
        self, result: Result[T, E]
    ) -> Result[dict[str, object], ResultSerializationError]:
        """Encode ``result`` into an envelope, or return a serialization error.

        An encoder that raises :class:`~pyeffect.panic.Panic` is a defect,
        not a wire failure — it propagates instead of becoming an ``Err``.
        """

        match result:
            case Ok(value):
                try:
                    return Ok({"status": _STATUS_OK, "value": self.encode_ok(value)})
                except Panic:
                    raise
                except Exception:  # noqa: BLE001
                    return Err(ResultSerializationError(value))
            case Err(error):
                try:
                    return Ok(
                        {"status": _STATUS_ERROR, "error": self.encode_err(error)}
                    )
                except Panic:
                    raise
                except Exception:  # noqa: BLE001
                    return Err(ResultSerializationError(error))

    def serialize_unsafe(self, result: Result[T, E]) -> dict[str, object]:
        """Encode ``result``; a serialization error is a defect (:class:`Panic`)."""

        match self.serialize(result):
            case Ok(envelope):
                return envelope
            case Err(error):
                raise Panic("serialization failed", cause=error)

    def deserialize(self, data: object) -> Result[T, E | ResultDeserializationError]:
        """Decode an envelope, returning the domain Result or a deserialization error.

        A malformed envelope — non-dict, unknown status, or a status whose
        payload key is missing — is an expected wire failure and returns an
        ``Err``; it never reaches the payload decoders.
        """

        if not isinstance(data, dict):
            return Err(ResultDeserializationError(data))
        status = data.get("status")
        if status == _STATUS_OK:
            if "value" not in data:
                return Err(ResultDeserializationError(data))
            return cast(
                Result[T, E | ResultDeserializationError],
                self.decode_ok(data.get("value")).map_err(ResultDeserializationError),
            )
        if status == _STATUS_ERROR:
            if "error" not in data:
                return Err(ResultDeserializationError(data))
            decoded = self.decode_err(data.get("error")).map_err(
                ResultDeserializationError
            )
            return decoded.fold(
                on_ok=lambda domain_error: cast(
                    Result[T, E | ResultDeserializationError], Err(domain_error)
                ),
                on_err=lambda issue: cast(
                    Result[T, E | ResultDeserializationError], Err(issue)
                ),
            )
        return Err(ResultDeserializationError(data))

    def deserialize_unsafe(self, data: object) -> Result[T, E]:
        """Decode an envelope; a deserialization error is a defect (:class:`Panic`).

        A valid serialized ``Err`` remains a domain ``Err`` -- only a malformed
        envelope or a payload that fails its decode schema panics.
        """

        result = self.deserialize(data)
        match result:
            case Ok(value):
                return Ok(value)
            case Err(error):
                if isinstance(error, ResultDeserializationError):
                    raise Panic("deserialization failed", cause=error)
                return Err(cast(E, error))
