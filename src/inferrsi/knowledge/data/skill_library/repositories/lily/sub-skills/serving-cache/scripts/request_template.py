#!/usr/bin/env python3
"""Construct or structurally screen Lily Chat JSON without network/model use.

Adapted from lily/src/serve.rs and lily/src/chat.rs in perplexityai/pplx-garden
at 1ed972ed3f0bd5616c997c9507c25616c63394fc (Apache-2.0 source; root notices
retain attribution). This is not native Rust, tokenizer or backend validation.

Example: python request_template.py --prompt 'Hello' --max-tokens 32
Example: python request_template.py --request request.json
"""

import argparse
import json
import sys
from pathlib import Path

MODEL_ID = "Qwen3.6-35B-A3B"
MAX_BODY_BYTES = 1 << 20
MAX_USIZE = (1 << 64) - 1  # Supported 64-bit Apple runtime, not arbitrary targets.
FIELDS = {"model", "messages", "max_tokens", "stream", "prompt_cache_key"}
ROLES = {"system", "user", "assistant"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def validate(body):
    """Return a structurally screened body; do not infer native token capacity."""
    if not isinstance(body, dict) or set(body) - FIELDS:
        raise ValueError("request must be an object containing only supported Lily fields")
    if body.get("model") != MODEL_ID:
        raise ValueError("model must be Qwen3.6-35B-A3B")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ValueError("each message must contain only role and content")
        if not isinstance(message["role"], str) or message["role"] not in ROLES:
            raise ValueError("message role must be system, user or assistant")
        if not isinstance(message["content"], str):
            raise ValueError("message content must be a string")
    if messages[-1]["role"] != "user":
        raise ValueError("the final message must have role=user")
    maximum = body.get("max_tokens", 128)
    if type(maximum) is not int or not 0 < maximum <= MAX_USIZE:
        raise ValueError("max_tokens must be a positive 64-bit unsigned integer")
    stream = body.get("stream", False)
    if type(stream) is not bool or stream:
        raise ValueError("stream must be false or omitted")
    key = body.get("prompt_cache_key")
    if key is not None and not isinstance(key, str):
        raise ValueError("prompt_cache_key must be a string or null")
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_BODY_BYTES:
        raise ValueError("request body exceeds 1 MiB")
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="one text user message")
    source.add_argument("--request", type=Path, help="existing JSON body to screen")
    parser.add_argument("--max-tokens", type=int, help="constructor output limit, default 128")
    parser.add_argument("--cache-key", help="preference only, not authentication/isolation")
    args = parser.parse_args()
    try:
        if args.request is not None:
            if args.max_tokens is not None or args.cache_key is not None:
                raise ValueError("--request cannot be combined with constructor options")
            raw = args.request.read_bytes()
            if len(raw) > MAX_BODY_BYTES:
                raise ValueError("request body exceeds 1 MiB")
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        else:
            body = {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": args.prompt}],
                "max_tokens": 128 if args.max_tokens is None else args.max_tokens,
                "stream": False,
            }
            if args.cache_key is not None:
                body["prompt_cache_key"] = args.cache_key
        validate(body)
        # Compact output preserves the checked byte limit even near 1 MiB.
        print(json.dumps(body, ensure_ascii=False, allow_nan=False), end="")
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
