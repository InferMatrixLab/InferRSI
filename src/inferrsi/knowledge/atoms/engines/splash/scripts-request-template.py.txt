#!/usr/bin/env python3
"""Prepare a small Splash Chat Completions body, without network activity.

Adapted from incoai/splash README.md and DEVELOPMENT.md request fields at the
source revision in this skill. Run with --model local-model --prompt 'Hello'.
No engine imports, credentials, external files, service or model downloads.
"""

import argparse
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--cache-salt")
    parser.add_argument("--max-tokens", type=int, default=64)
    args = parser.parse_args()
    if not args.model.strip() or not args.prompt.strip() or args.max_tokens <= 0:
        parser.error("model/prompt must be non-empty and max-tokens positive")
    if args.cache_salt is not None and not args.cache_salt.strip():
        parser.error("cache-salt must be non-empty when supplied")
    value = {"model": args.model, "messages": [{"role": "user", "content": args.prompt}],
             "max_tokens": args.max_tokens, "temperature": 0, "stream": False}
    if args.cache_salt is not None:
        value["cache_salt"] = args.cache_salt
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
