from __future__ import annotations

import json
import math
import re

# inferrsi-json-v1 (D002/D017): the only shared canonical encoder leaf (D001).
MAX_SAFE_INTEGER = 9007199254740991
_BOM = b"\xef\xbb\xbf"
_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}
_ESCAPED = re.compile(r'[\x00-\x1f"\\]')


class CanonicalError(ValueError):
    """A value or byte sequence outside inferrsi-json-v1; ``stage`` names the rule."""

    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage


def _escape(match: re.Match[str]) -> str:
    character = match.group()
    return _SHORT_ESCAPES.get(character) or f"\\u{ord(character):04x}"


def _string(value: str) -> str:
    return '"' + _ESCAPED.sub(_escape, value) + '"'


def _key(value: object) -> str:
    if not isinstance(value, str) or not value.isascii():
        raise CanonicalError("ascii_key", f"object keys must be ASCII strings: {value!r}")
    return value


def _parts(value: object, out: list[str]) -> None:
    # bool is checked before int because it is an int subclass.
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, int):
        if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            raise CanonicalError("integer_range", f"integer outside the safe range: {value}")
        out.append(str(value))
    elif isinstance(value, float):
        stage = "float_token" if math.isfinite(value) else "nonfinite_token"
        raise CanonicalError(stage, "non-integer numbers must be canonical Decimal strings")
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, list):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _parts(item, out)
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        for index, key in enumerate(sorted(value, key=_key)):
            if index:
                out.append(",")
            out.append(_string(key))
            out.append(":")
            _parts(value[key], out)
        out.append("}")
    else:
        raise CanonicalError("unsupported_type", f"unsupported value type {type(value).__name__}")


def encode(value: object) -> bytes:
    """Return the canonical inferrsi-json-v1 bytes of a JSON-shaped value."""
    out: list[str] = []
    _parts(value, out)
    try:
        return "".join(out).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonicalError("unicode_scalar", "lone surrogates are not Unicode scalars") from exc


def _reject_float(token: str) -> object:
    raise CanonicalError("float_token", f"floating-point token {token!r}")


def _reject_constant(token: str) -> object:
    raise CanonicalError("nonfinite_token", f"non-finite token {token!r}")


def _integer(token: str) -> int:
    # Bound the digit count before int() so huge tokens fail on range, not on CPython limits.
    if len(token.lstrip("-")) > 16 or abs(int(token)) > MAX_SAFE_INTEGER:
        raise CanonicalError("integer_range", f"integer outside the safe range: {token}")
    return int(token)


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise CanonicalError("duplicate_key", f"duplicate key {key!r}")
        result[key] = item
    return result


def _check_scalars(value: object) -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CanonicalError("unicode_scalar", "lone surrogate escape") from exc
    elif isinstance(value, list):
        for item in value:
            _check_scalars(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_scalars(key)
            _key(key)
            _check_scalars(item)


def decode(data: bytes) -> object:
    """Strictly parse fixed bytes; anything but the canonical encoding is rejected."""
    if data.startswith(_BOM):
        raise CanonicalError("no_bom", "fixed bytes must not start with a BOM")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CanonicalError("strict_utf8", "invalid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            parse_int=_integer,
        )
    except json.JSONDecodeError as exc:
        raise CanonicalError("json_syntax", str(exc)) from exc
    _check_scalars(value)
    if encode(value) != data:
        raise CanonicalError("canonical_bytes", "bytes differ from their canonical re-encoding")
    return value
