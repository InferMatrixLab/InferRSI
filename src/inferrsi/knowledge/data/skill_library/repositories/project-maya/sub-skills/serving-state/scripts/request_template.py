#!/usr/bin/env python3
"""Print a narrow text Responses request as JSON; never contact or import Maya.

Python standard library only. Original helper, not a copied upstream script.
Contracts inspected in Project Maya serve/responses.py at source snapshot
249f9a87d1a9d72bec2b684d704b0aa9296b1c9c. No history, authentication, model,
capacity, output-schema or backend verification is performed.

Example: python request_template.py --input "Synthetic note" --store --background
"""

import argparse
import json


def nonempty(value):
    """Preserve text exactly while rejecting an empty CLI argument."""
    if not value:
        raise argparse.ArgumentTypeError("must be nonempty")
    return value


def positive_integer(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def cache_hint(value):
    nonempty(value)
    if len(value) > 256:
        raise argparse.ArgumentTypeError("must contain at most 256 characters")
    return value


def parser():
    out = argparse.ArgumentParser(
        description="Print a small text-only Maya Responses JSON request offline."
    )
    out.add_argument("--input", required=True, type=nonempty, help="synthetic user text")
    out.add_argument("--model", type=nonempty, help="optional model label")
    out.add_argument("--store", action="store_true", help="opt in to process-memory history")
    out.add_argument("--background", action="store_true", help="requires --store")
    out.add_argument("--stream", action="store_true", help="request SSE projection")
    out.add_argument(
        "--previous-response-id", type=nonempty, help="must already exist under this owner"
    )
    out.add_argument("--prompt-cache-key", type=cache_hint, help="hint only, NOT tenant isolation")
    out.add_argument("--max-output-tokens", type=positive_integer)
    return out


def main():
    arg_parser = parser()
    args = arg_parser.parse_args()
    if args.background and not args.store:
        arg_parser.error("--background requires explicit --store")
    request = {
        "input": args.input,
        "store": args.store,
        "background": args.background,
        "stream": args.stream,
        "truncation": "disabled",
    }
    for key in ("model", "previous_response_id", "prompt_cache_key", "max_output_tokens"):
        value = getattr(args, key)
        if value is not None:
            request[key] = value
    print(json.dumps(request, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
