"""Typing fixture: Codec/from_dict pinned with assert_type."""

from __future__ import annotations

from typing import Any, assert_type

from pyeffect.codec import (
    Codec,
    ResultDeserializationError,
    ResultSerializationError,
    from_dict,
)
from pyeffect.result import Ok, Result


def _make_codec(
    encode_ok: object,
    encode_err: object,
    decode_ok: object,
    decode_err: object,
) -> Codec[int, str]:
    """Construct a Codec[int, str] bypassing PEP 695 generic constructor inference."""
    return Codec(encode_ok, encode_err, decode_ok, decode_err)  # ty: ignore[invalid-argument-type]


def main(n: int, boom: str) -> None:
    codec = _make_codec(
        str,
        lambda e: e,
        lambda w: Ok(int(str(w))),
        Ok,
    )

    # serialize returns a Result over the wire envelope.
    assert_type(
        codec.serialize(Ok(n)),
        Result[dict[str, object], ResultSerializationError],
    )

    # deserialize: success stays T; the error widens to E | DeserializationError.
    assert_type(
        codec.deserialize({"status": "ok", "value": "1"}),
        Result[int, str | ResultDeserializationError],
    )

    # unsafe deserialize narrows the error back to E.
    assert_type(
        codec.deserialize_unsafe({"status": "error", "error": boom}),
        Result[int, str],
    )

    # from_dict returns a loosely-typed Result.
    assert_type(
        from_dict({"status": "ok", "value": 1}),
        Result[Any, ResultDeserializationError],
    )
