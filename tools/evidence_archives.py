"""Shared offline manifest reader and bounded archive verification.

Accept the two original v1 pilot layouts without rewriting frozen evidence.
New publications use v2. Nothing in this module executes archive content or
adjudicates a campaign verdict.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path


class VerificationError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise VerificationError(code, message)


def safe_name(name):
    require(
        isinstance(name, str)
        and bool(name)
        and "\\" not in name
        and ":" not in name
        and not any(ord(char) < 32 for char in name)
        and all(part not in ("", ".", "..") for part in name.split("/")),
        "unsafe_path",
        "Expected a safe relative POSIX path",
    )
    return name


def parse_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "metadata", "Duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(payload, object_pairs_hook=pairs)
    except ValueError as exc:
        if isinstance(exc, VerificationError):
            raise
        raise VerificationError("metadata", "Unreadable or invalid JSON") from exc


def read_json(path):
    try:
        return parse_json(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VerificationError("missing_file", "JSON file is unavailable") from exc


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def digest(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
        "metadata",
        "Expected a lowercase SHA-256 digest",
    )
    return value


def positive_int(value):
    require(type(value) is int and value > 0, "metadata", "Expected a positive integer")
    return value


def text(value):
    require(isinstance(value, str) and bool(value.strip()), "metadata", "Expected nonempty text")
    return value


def alias(values, label):
    found = [value for value in values if value is not None]
    require(
        bool(found) and all(value == found[0] for value in found),
        "metadata",
        f"Missing or conflicting {label}",
    )
    return found[0]


def https_url(url):
    try:
        parsed = urllib.parse.urlsplit(text(url))
        require(
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and not parsed.query
            and not parsed.fragment,
            "metadata",
            "Expected a credential-free HTTPS URL without query or fragment",
        )
    except ValueError as exc:
        raise VerificationError("metadata", "Invalid HTTPS URL") from exc
    return parsed


def normalize_manifest(data):
    """Return one v2-shaped view; never mutate the authoritative source document."""
    try:
        require(
            isinstance(data, dict)
            and type(data.get("schema_version")) is int
            and data["schema_version"] in (1, 2),
            "metadata",
            "Unsupported manifest version",
        )
        version = data["schema_version"]
        source = data["archive"]
        require(isinstance(source, dict), "metadata", "Expected archive object")
        fmt = source["format"]
        require(fmt in ("tar.gz", "tar+gzip"), "metadata", "Unsupported archive format")
        revision = alias(
            [
                source.get("source_revision"),
                source.get("snapshot_revision"),
                data.get("source_revision"),
            ],
            "source revision",
        )
        require(
            isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40,64}", revision),
            "metadata",
            "Expected an immutable source revision",
        )
        files = positive_int(alias([source.get("files"), source.get("original_files")], "files"))
        size = positive_int(
            alias(
                [source.get("uncompressed_bytes"), source.get("original_bytes")],
                "uncompressed bytes",
            )
        )
        keys = alias([source.get("key_files"), data.get("key_files")], "key files")
        require(isinstance(keys, dict) and bool(keys), "metadata", "Expected named key files")
        # H3 v1 counts original files beneath its narrative directory; snapshot.json
        # sits outside that root and is independently listed as a key file.
        root = source.get("root")
        require(root is None or isinstance(root, str), "metadata", "Invalid archive root")
        if root is None and version == 1 and "original_files" in source:
            root = safe_name(keys["historical_narrative"]).rsplit("/", 1)[0]
        root = safe_name(root) if root else ""
        normalized_keys = {}
        for label, name in keys.items():
            text(label)
            if version == 1 and "key_files" in data:
                name = root + "/" + name if root else name
            directory = isinstance(name, str) and name.endswith("/")
            normalized_keys[label] = safe_name(name.rstrip("/") if directory else name)
            if directory:
                normalized_keys[label] += "/"
        filename = safe_name(source["file"])
        require("/" not in filename, "metadata", "Archive file must be a basename")
        url = text(source["url"])
        parsed = https_url(url)
        require(
            urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1]) == filename,
            "metadata",
            "URL and filename disagree",
        )
        archive = {
            "id": text(source.get("id", filename)),
            "file": filename,
            "url": url,
            "sha256": digest(source["sha256"]),
            "bytes": positive_int(source["bytes"]),
            "format": "tar+gzip",
            "retention_owner": text(source["retention_owner"]),
            "source_revision": revision,
            "root": root,
            "files": files,
            "uncompressed_bytes": size,
            "key_files": normalized_keys,
        }
        verification = data.get("verification") if version == 2 else None
        if version == 2:
            require(
                fmt == "tar+gzip" and all(key in source for key in archive),
                "metadata",
                "v2 requires canonical archive fields",
            )
            require(isinstance(verification, dict), "metadata", "v2 requires verification contract")
            for name in ("trials", "summary"):
                safe_name(verification[name])
            command = verification["command"]
            require(
                isinstance(command, list) and bool(command), "metadata", "Expected command argv"
            )
            for part in command:
                text(part)
            inputs = verification["inputs"]
            require(
                isinstance(inputs, list) and bool(inputs), "metadata", "Expected input identities"
            )
            require(
                {item["role"] for item in inputs} >= {"control", "configuration", "validator"},
                "metadata",
                "Pin control, configuration and validator inputs",
            )
            names = []
            for item in inputs:
                names.append(safe_name(item["path"]))
                digest(item["sha256"])
            require(len(names) == len(set(names)), "metadata", "Duplicate verification input")
            for name in ("absolute_tolerance", "relative_tolerance"):
                value = verification[name]
                require(
                    type(value) in (int, float) and math.isfinite(value) and value >= 0,
                    "metadata",
                    "Expected finite nonnegative comparison tolerance",
                )
        return {
            "schema_version": 2,
            "source_schema_version": version,
            "archive": archive,
            "verification": verification,
        }
    except (KeyError, TypeError, AttributeError) as exc:
        raise VerificationError("metadata", "Missing or malformed archive metadata") from exc


@dataclass(frozen=True)
class Limits:
    compressed_bytes: int = 256 * 1024 * 1024
    expanded_bytes: int = 512 * 1024 * 1024
    members: int = 10000
    seconds: float = 120


def deadline_check(deadline):
    require(time.monotonic() <= deadline, "resource_limit", "Verification time limit exceeded")


class LimitedStream:
    """Count tar headers, padding and PAX payloads as well as file contents."""

    def __init__(self, source, limit, deadline):
        self.source, self.limit, self.deadline, self.count = source, limit, deadline, 0

    def read(self, size):
        deadline_check(self.deadline)
        block = self.source.read(min(size, self.limit - self.count + 1))
        self.count += len(block)
        require(self.count <= self.limit, "resource_limit", "Expanded archive limit exceeded")
        deadline_check(self.deadline)
        return block


def verify_archive(path, manifest, limits=Limits()):
    """Hash before parsing; inspect member bytes without writing or executing them."""
    spec = manifest["archive"]
    require(spec["bytes"] <= limits.compressed_bytes, "resource_limit", "Compressed size limit")
    deadline = time.monotonic() + limits.seconds
    try:
        # One open handle prevents path replacement between authentication and parsing.
        with Path(path).open("rb") as stream:
            identity, size = hashlib.sha256(), 0
            while block := stream.read(1024 * 1024):
                size += len(block)
                require(size <= spec["bytes"], "bad_bytes", "Archive byte count mismatch")
                deadline_check(deadline)
                identity.update(block)
            require(size == spec["bytes"], "bad_bytes", "Archive byte count mismatch")
            require(identity.hexdigest() == spec["sha256"], "bad_hash", "Archive SHA-256 mismatch")
            stream.seek(0)
            names, identities, total, originals, original_bytes = set(), {}, 0, 0, 0
            with gzip.GzipFile(fileobj=stream) as uncompressed:
                bounded = LimitedStream(uncompressed, limits.expanded_bytes, deadline)
                with tarfile.open(fileobj=bounded, mode="r|") as archive:
                    for member in archive:
                        deadline_check(deadline)
                        name = safe_name(member.name)
                        require(
                            member.isfile() and not member.issparse(),
                            "unsafe_member",
                            "Only regular nonsparse files are supported",
                        )
                        require(name not in names, "unsafe_member", "Duplicate archive member")
                        names.add(name)
                        total += member.size
                        require(
                            member.size >= 0
                            and len(names) <= limits.members
                            and total <= limits.expanded_bytes,
                            "resource_limit",
                            "Member limit",
                        )
                        member_hash, received = hashlib.sha256(), 0
                        with archive.extractfile(member) as content:
                            while block := content.read(1024 * 1024):
                                deadline_check(deadline)
                                received += len(block)
                                member_hash.update(block)
                        require(received == member.size, "invalid_archive", "Truncated member")
                        identities[name] = member_hash.hexdigest()
                        if not spec["root"] or name.startswith(spec["root"] + "/"):
                            originals += 1
                            original_bytes += received
                # Validate gzip CRC and bound padding/trailing data after tar's end marker.
                while bounded.read(1024 * 1024):
                    pass
    except FileNotFoundError as exc:
        raise VerificationError("unavailable", "Local archive unavailable") from exc
    except (tarfile.TarError, EOFError, gzip.BadGzipFile, zlib.error) as exc:
        raise VerificationError("invalid_archive", "Malformed archive") from exc
    for name in spec["key_files"].values():
        present = (
            any(item.startswith(name) for item in names) if name.endswith("/") else name in names
        )
        require(present, "missing_file", "Archive is missing a declared key file")
    require(
        originals == spec["files"] and original_bytes == spec["uncompressed_bytes"],
        "bad_contents",
        "Original file count or expanded byte count mismatch",
    )
    if manifest["verification"]:
        for item in manifest["verification"]["inputs"]:
            require(item["path"] in identities, "missing_file", "Missing verification input")
            require(
                identities[item["path"]] == item["sha256"],
                "bad_hash",
                "Verification input SHA-256 mismatch",
            )
    return {
        "content": "verified",
        "members": len(names),
        "original_files": originals,
        "original_bytes": original_bytes,
        "sha256": spec["sha256"],
        "recomputation": "not_checked",
        "campaign_verdict": "unchanged",
    }


DOWNLOAD_HOSTS = {
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
}


def allowed_download(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in DOWNLOAD_HOSTS
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(allowed_download(newurl), "unsafe_redirect", "Unsupported archive redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_archive(manifest, destination, limits=Limits()):
    spec = manifest["archive"]
    require(
        re.fullmatch(r"https://github\.com/[^/]+/[^/]+/releases/download/[^/]+/[^/]+", spec["url"]),
        "restricted_access",
        "Use --archive for controlled storage; automatic download supports Releases",
    )
    require(spec["bytes"] <= limits.compressed_bytes, "resource_limit", "Compressed size limit")
    deadline = time.monotonic() + limits.seconds
    try:
        opener = urllib.request.build_opener(ReleaseRedirect())
        with opener.open(spec["url"], timeout=min(10, limits.seconds)) as response:
            require(
                allowed_download(response.url), "unsafe_redirect", "Unsupported download location"
            )
            with Path(destination).open("xb") as sink:
                received = 0
                while block := response.read(1024 * 1024):
                    deadline_check(deadline)
                    received += len(block)
                    require(
                        received <= spec["bytes"], "bad_bytes", "Download exceeds declared size"
                    )
                    sink.write(block)
    except urllib.error.HTTPError as exc:
        code = "restricted_access" if exc.code in (401, 403) else "unavailable"
        raise VerificationError(code, "Archive download failed") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise VerificationError("unavailable", "Archive download unavailable") from exc


def compare_values(left, right, absolute, relative):
    """Exact structure/integers; finite floats use the contract's declared tolerance."""
    if type(left) is float and type(right) is float:
        return (
            math.isfinite(left)
            and math.isfinite(right)
            and math.isclose(left, right, abs_tol=absolute, rel_tol=relative)
        )
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            compare_values(left[key], right[key], absolute, relative) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            compare_values(a, b, absolute, relative) for a, b in zip(left, right)
        )
    return left == right


def compare_results(manifest, retained, regenerated):
    """Compare outputs of an explicitly reviewed, separately run replay command."""
    contract = manifest["verification"]
    require(contract is not None, "not_supported", "Use the frozen v1 campaign replay checker")

    def local(root, name):
        path = Path(root).joinpath(safe_name(name)).resolve()
        require(
            path.is_relative_to(Path(root).resolve()), "unsafe_path", "Result path escapes root"
        )
        return path

    def trials(path):
        try:
            rows = [parse_json(line) for line in path.read_text(encoding="utf-8").splitlines()]
            ids = [text(row["id"]) for row in rows]
            require(len(ids) == len(set(ids)), "trial_mismatch", "Duplicate trial ID")
            for row in rows:
                for key in ("status", "conclusion", "artifact_id", "source_record"):
                    text(row[key])
                require(
                    isinstance(row["configuration"], dict), "trial_mismatch", "Trial configuration"
                )
                require(
                    row["artifact_id"] == manifest["archive"]["id"],
                    "trial_mismatch",
                    "Trial references a different archive",
                )
            return dict(zip(ids, rows))
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, VerificationError):
                raise
            raise VerificationError("trial_mismatch", "Invalid trial index") from exc

    for key, reader, code in (
        ("trials", trials, "trial_mismatch"),
        ("summary", read_json, "recompute_mismatch"),
    ):
        try:
            expected = reader(local(retained, contract[key]))
            actual = reader(local(regenerated, contract[key]))
        except FileNotFoundError as exc:
            raise VerificationError("missing_file", "Missing replay output") from exc
        require(
            compare_values(
                expected, actual, contract["absolute_tolerance"], contract["relative_tolerance"]
            ),
            code,
            f"Regenerated {key} differs",
        )
    return {
        "recomputation": "outputs_match",
        "trials": len(trials(local(retained, contract["trials"]))),
    }
