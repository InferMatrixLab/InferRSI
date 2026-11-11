"""Canonical JSON bytes for v1 contracts."""

import json

_MAX_INTEGER = 2**53 - 1


def _check_value(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise ValueError("v1 JSON object keys must be ASCII strings")
            _check_value(item)
    elif type(value) is list:
        for item in value:
            _check_value(item)
    elif type(value) is int:
        if abs(value) > _MAX_INTEGER:
            raise ValueError("v1 JSON integer out of range")
    elif value is not None and type(value) not in (str, bool):
        raise ValueError("unsupported v1 JSON value")


def encode(value: object) -> bytes:
    _check_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _object_from_pairs(pairs: list[tuple[str, object]]) -> dict:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate v1 JSON object key")
    return value


def _reject_number(token: str) -> None:
    raise ValueError("unsupported v1 JSON number")


def decode(data: bytes) -> object:
    value = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_object_from_pairs,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    if encode(value) != data:
        raise ValueError("noncanonical v1 JSON bytes")
    return value
