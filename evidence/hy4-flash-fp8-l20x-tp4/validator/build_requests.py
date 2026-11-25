"""Reconstruct and check the 20 frozen input token arrays."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from tokenizers import Tokenizer


def verify(path, expected):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"Input digest mismatch for {path.name}")


def fixed_tokens(tokenizer, template, item, expected_length):
    prefix, suffix = template.split("$DOC$")
    suffix = suffix.replace("$Q$", item["question"].strip())
    for choice in "ABCD":
        suffix = suffix.replace(f"$C_{choice}$", item[f"choice_{choice}"].strip())
    document = item["context"].strip()
    encoded = tokenizer.encode(prefix + document + suffix, add_special_tokens=False)
    if len(encoded.ids) != expected_length:
        raise ValueError(f"Original token count mismatch for {item['_id']}")
    inside = [
        i
        for i, (left, right) in enumerate(encoded.offsets)
        if left >= len(prefix) and right <= len(prefix) + len(document)
    ]
    if not inside:
        raise ValueError("Document has no interior tokens to repeat")
    start, end = inside[0], inside[-1] + 1
    doc_ids = encoded.ids[start:end]
    fixed = 130048 - start - len(encoded.ids[end:])
    if fixed < 0:
        raise ValueError("Template and question exceed the frozen input length")
    repetitions = (fixed + len(doc_ids) - 1) // len(doc_ids)
    return encoded.ids[:start] + (doc_ids * repetitions)[:fixed] + encoded.ids[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "template", "tokenizer", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("inputs.json").read_text())["performance"]
    verify(args.data, manifest["source_json_sha256"])
    verify(args.template, manifest["template_sha256"])
    verify(args.tokenizer, manifest["tokenizer_sha256"])
    tokenizer = Tokenizer.from_file(str(args.tokenizer))
    template = args.template.read_text()
    wanted = {row["id"] for row in manifest["requests"]}
    items = {r["_id"]: r for r in json.loads(args.data.read_bytes()) if r["_id"] in wanted}
    if len(items) != len(wanted) or len(wanted) != 20:
        raise ValueError("The ordered set must contain 20 distinct source items")
    with tempfile.NamedTemporaryFile(dir=args.out.parent, delete=False, mode="w") as stream:
        temporary = Path(stream.name)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for row in manifest["requests"]:
                tokens = fixed_tokens(tokenizer, template, items[row["id"]], row["original_tokens"])
                packed = json.dumps(tokens, separators=(",", ":")).encode()
                if (
                    len(tokens) != 130048
                    or hashlib.sha256(packed).hexdigest() != row["token_ids_sha256"]
                ):
                    raise ValueError(f"Token IDs differ for {row['id']}")
                stream.write(json.dumps({"id": row["id"], "prompt": tokens}, separators=(",", ":")))
                stream.write("\n")
        verify(temporary, manifest["ordered_jsonl_sha256"])
        temporary.replace(args.out)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
