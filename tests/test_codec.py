"""Runtime behavior tests for the Result serialization codec."""

from __future__ import annotations

import pytest

from pyeffect.codec import (
    Codec,
    ResultDeserializationError,
    ResultSerializationError,
    from_dict,
)
from pyeffect.panic import Panic
from pyeffect.result import Err, Ok


def _make_codec(
    encode_ok: object,
    encode_err: object,
    decode_ok: object,
    decode_err: object,
) -> Codec[int, str]:
    """Construct a Codec[int, str] bypassing PEP 695 generic constructor inference."""
    return Codec(encode_ok, encode_err, decode_ok, decode_err)  # ty: ignore[invalid-argument-type]


def test_from_dict_ok_envelope() -> None:
    assert from_dict({"status": "ok", "value": 5}) == Ok(5)


def test_from_dict_err_envelope() -> None:
    assert from_dict({"status": "error", "error": "boom"}) == Err("boom")


def test_from_dict_rejects_non_dict() -> None:
    result = from_dict("nope")
    assert isinstance(result, Err)
    assert isinstance(result.error, ResultDeserializationError)


def test_from_dict_rejects_unknown_status() -> None:
    result = from_dict({"status": "weird"})
    assert isinstance(result, Err)
    assert isinstance(result.error, ResultDeserializationError)


def test_codec_roundtrip() -> None:
    codec = _make_codec(
        lambda n: str(n),
        lambda e: e,
        lambda w: Ok(int(str(w))),
        lambda w: Ok(w),
    )
    encoded = codec.serialize(Ok(5))
    assert encoded == Ok({"status": "ok", "value": "5"})
    assert codec.deserialize({"status": "ok", "value": "5"}) == Ok(5)
    assert codec.deserialize({"status": "error", "error": "boom"}) == Err("boom")


def test_codec_deserialize_rejects_missing_payload_keys() -> None:
    # A status without its payload key is a malformed envelope — an
    # expected wire failure that must not reach the payload decoders.
    codec = _make_codec(
        lambda n: str(n),
        lambda e: e,
        lambda w: Ok(int(str(w))),
        lambda w: Ok(w),
    )
    for malformed in ({"status": "ok"}, {"status": "error"}):
        result = codec.deserialize(malformed)
        assert isinstance(result, Err)
        assert isinstance(result.error, ResultDeserializationError)


def test_codec_serialize_catches_encoder_defects() -> None:
    def boom(x: int) -> object:
        raise ValueError("bad")

    codec = _make_codec(
        boom,
        lambda e: e,
        lambda w: Ok(int(str(w))),
        lambda w: Ok(w),
    )
    result = codec.serialize(Ok(5))
    assert isinstance(result, Err)
    assert isinstance(result.error, ResultSerializationError)


def test_codec_serialize_unsafe_panics() -> None:
    def boom(x: int) -> object:
        raise ValueError("bad")

    codec = _make_codec(
        boom,
        lambda e: e,
        lambda w: Ok(int(str(w))),
        lambda w: Ok(w),
    )
    with pytest.raises(Panic):
        codec.serialize_unsafe(Ok(5))


def test_codec_serialize_propagates_encoder_panics() -> None:
    # An encoder raising a Panic is a defect, not a wire failure: it must
    # propagate unchanged instead of becoming a ResultSerializationError.
    def boom(x: object) -> object:
        raise Panic("encoder defect")

    codec = _make_codec(
        boom,
        boom,
        lambda w: Ok(w),
        lambda w: Ok(w),
    )
    with pytest.raises(Panic, match="encoder defect"):
        codec.serialize(Ok(5))
    with pytest.raises(Panic, match="encoder defect"):
        codec.serialize(Err("boom"))


def test_codec_serialize_unsafe_propagates_encoder_panics() -> None:
    def boom(x: object) -> object:
        raise Panic("encoder defect")

    codec = _make_codec(
        boom,
        lambda e: e,
        lambda w: Ok(w),
        lambda w: Ok(w),
    )
    with pytest.raises(Panic, match="encoder defect"):
        codec.serialize_unsafe(Ok(5))


def test_codec_deserialize_unsafe_keeps_domain_err() -> None:
    codec = _make_codec(
        lambda n: str(n),
        lambda e: e,
        lambda w: Ok(int(str(w))),
        lambda w: Ok(w),
    )
    assert codec.deserialize_unsafe({"status": "error", "error": "boom"}) == Err("boom")


def test_codec_deserialize_unsafe_panics_on_bad_envelope() -> None:
    codec = _make_codec(
        lambda n: str(n),
        lambda e: e,
        lambda w: Ok(int(str(w))),
        lambda w: Ok(w),
    )
    with pytest.raises(Panic):
        codec.deserialize_unsafe("not-a-dict")
