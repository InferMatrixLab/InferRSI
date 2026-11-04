#!/usr/bin/env python3
"""Build a small DwarfStar Chat Completions request without network activity.

Adapted from the request shape in antirez/ds4 docs/SERVER.md at the source
revision recorded by this skill. Prints JSON to stdout; never contacts a server.
Example: python request_template.py --model local-model --prompt 'Hello'
"""

import argparse
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="API alias, not a model file selector")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()
    if not args.model.strip() or not args.prompt.strip():
        parser.error("model and prompt must be non-empty")
    if args.max_tokens <= 0 or not 0 <= args.temperature <= 2:
        parser.error("max-tokens must be positive; helper temperature range is [0, 2]")
    request = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "stream": args.stream,
    }
    print(json.dumps(request, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
