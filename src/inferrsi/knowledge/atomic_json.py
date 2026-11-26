"""Locate JSON members in the exact UTF-8 source used to build an atom."""

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    parent: str
    index: int
    start: int
    end: int


_TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}\[\],:]|[^{}\[\],:" \t\r\n]+')


def member_spans(source: bytes) -> dict[str, Member]:
    # The standard decoder validates syntax. Token positions retain the original
    # bytes, including escaped keys, UTF-8 text and the spacing between members.
    json.loads(source.decode("utf-8"))
    tokens = _TOKEN.finditer(source)
    members = {}

    def visit(pointer, token):
        opening = token.group()
        if opening not in (b"{", b"["):
            return token.end()
        closing = b"}" if opening == b"{" else b"]"
        token = next(tokens)
        index = 0
        while token.group() != closing:
            start = token.start()
            if opening == b"{":
                key = json.loads(token.group())
                segment = key.replace("~", "~0").replace("/", "~1")
                next(tokens)  # colon after the key
                token = next(tokens)
            else:
                segment = str(index)
            child = pointer + "/" + segment
            if child in members:
                raise ValueError(f"Duplicate JSON member at {child}")
            end = visit(child, token)
            members[child] = Member(pointer, index, start, end)
            index += 1
            token = next(tokens)
            if token.group() == b",":
                token = next(tokens)
        return token.end()

    visit("", next(tokens))
    return members


def matches_span(members: dict[str, Member], pointers: list[str], start: int, end: int) -> bool:
    """A part covers complete, consecutive siblings, from the first key/item to the last value."""
    if not pointers or any(pointer not in members for pointer in pointers):
        return False
    selected = [members[pointer] for pointer in pointers]
    first = selected[0]
    return (first.start == start and selected[-1].end == end
            and all(item.parent == first.parent and item.index == first.index + offset
                    for offset, item in enumerate(selected)))
