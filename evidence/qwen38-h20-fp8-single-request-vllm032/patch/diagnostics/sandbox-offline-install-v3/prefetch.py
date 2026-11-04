"""Fetch locked wheels as data using recorded target tags; never install or import."""

import argparse
import hashlib
import json
import re
import signal
import urllib.parse
import urllib.request
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def parse_lock(raw):
    result, pending = {}, ""
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            if pending:
                raise ValueError("Interrupted lock continuation")
            continue
        pending += " " + line.removesuffix("\\").strip()
        if line.endswith("\\"):
            continue
        match = re.fullmatch(
            r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.!+_-]+)"
            r"((?:\s+--hash=sha256:[a-f0-9]{64})+)\s*", pending
        )
        if not match:
            raise ValueError("Unsupported lock grammar")
        name = canonicalize_name(match[1])
        version = str(Version(match[2]))
        hashes = set(re.findall(r"--hash=sha256:([a-f0-9]{64})", match[3]))
        if name in result:
            raise ValueError("Duplicate lock package")
        result[name] = (version, hashes)
        pending = ""
    if pending or not result:
        raise ValueError("Incomplete or empty lock")
    return result


def merged_locks(locks):
    result = {}
    for lock in locks:
        for name, (version, hashes) in lock.items():
            if name in result:
                previous, accepted = result[name]
                if previous != version or not accepted & hashes:
                    raise ValueError("Conflicting lock package")
                hashes = accepted & hashes
            result[name] = (version, hashes)
    return result


def checked_url(url, host):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != host
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Unexpected public artifact URL")
    return url


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        checked_url(newurl, urllib.parse.urlsplit(request.full_url).netloc)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch(url, host, maximum):
    checked_url(url, host)
    opener = urllib.request.build_opener(SameHostRedirect())
    request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})

    def timeout(_signum, _frame):
        raise TimeoutError("Artifact read deadline")

    # Main-thread sequential downloads: SIGALRM interrupts a blocked read, unlike
    # a deadline checked only between reads or the socket's inactivity timeout.
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ValueError("An existing alarm would be overwritten")
    previous = signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, 120)
    try:
        with opener.open(request, timeout=30) as response:
            checked_url(response.geturl(), host)
            if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                raise ValueError("Unexpected HTTP response")
            chunks, count = [], 0
            while True:
                chunk = response.read(min(262144, maximum + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                if count > maximum:
                    raise ValueError("Oversized artifact")
        return b"".join(chunks)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def choose_wheel(name, version, hashes, metadata, ranks, python_version):
    if (canonicalize_name(metadata["info"]["name"]) != name
            or Version(metadata["info"]["version"]) != Version(version)):
        raise ValueError("Metadata package identity mismatch")
    candidates = []
    for entry in metadata["urls"]:
        if entry["packagetype"] != "bdist_wheel" or entry.get("yanked"):
            continue
        filename = entry["filename"]
        if Path(filename).name != filename or "\\" in filename:
            raise ValueError("Invalid wheel filename")
        package, release, _, tags = parse_wheel_filename(filename)
        if package != name or release != Version(version):
            continue
        matching = [ranks[str(tag)] for tag in tags if str(tag) in ranks]
        if not matching or entry["digests"]["sha256"] not in hashes:
            continue
        requires = entry.get("requires_python")
        if requires and not SpecifierSet(requires).contains(python_version, prereleases=True):
            continue
        url = checked_url(entry["url"], "files.pythonhosted.org")
        if urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]) != filename:
            raise ValueError("URL filename mismatch")
        if type(entry["size"]) is not int or not 0 < entry["size"] <= 200 * 1024 * 1024:
            raise ValueError("Unexpected wheel size")
        candidates.append((min(matching), filename, entry))
    if not candidates:
        raise ValueError("No compatible locked wheel")
    rank, _, entry = min(candidates, key=lambda item: item[:2])
    return entry, rank


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--platform", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy_raw = args.policy.read_bytes()
    policy = strict_json(policy_raw)
    platform_raw = args.platform.read_bytes()
    if sha(platform_raw) != policy["platform_sha256"]:
        raise ValueError("Platform digest mismatch")
    observed = strict_json(platform_raw)
    target = observed["platform"]
    if (observed["completed"] is not True or target["completed"] is not True
            or target["system"] != "Linux" or target["machine"] != "x86_64"
            or target["implementation"] != "cpython" or target["python"] != "3.12.13"):
        raise ValueError("Unexpected target platform")
    tags = target["supported_tags"]
    if not tags or len(set(tags)) != len(tags):
        raise ValueError("Empty or duplicate target tags")
    ranks = {tag: index for index, tag in enumerate(tags)}
    locks = []
    for filename in ("build.lock", "dependencies.lock"):
        raw = (args.inputs / filename).read_bytes()
        if sha(raw) != policy["locks"][filename]:
            raise ValueError("Lock digest mismatch")
        locks.append(parse_lock(raw))
    packages = merged_locks(locks)
    if [len(lock) for lock in locks] != [5, 92] or len(packages) != 96:
        raise ValueError("Unexpected locked closure")
    args.output.mkdir(mode=0o700, exist_ok=False)
    wheelhouse = args.output / "wheelhouse"
    wheelhouse.mkdir()
    metadata_dir = args.output / "metadata"
    metadata_dir.mkdir()
    report = {"scope": "local_offline_wheel_prefetch", "verdict": "INCONCLUSIVE",
              "completed": False, "installed": False, "executed_downloads": False,
              "policy_sha256": sha(policy_raw), "platform_sha256": sha(platform_raw),
              "script_sha256": sha(Path(__file__).read_bytes()), "files": [], "errors": []}

    def package_task(name, version, hashes):
        if name in ("wget", "tempdir"):
            filename = f"{name}-{version}-py3-none-any.whl"
            raw = (args.inputs / "wheelhouse" / filename).read_bytes()
            digest = sha(raw)
            if digest not in hashes or "py3-none-any" not in ranks:
                raise ValueError("Reviewed local wheel mismatch")
            record = {"name": name, "version": version, "filename": filename,
                      "sha256": digest, "size": len(raw),
                      "source": "reviewed_cpu1986_build", "tag_rank": ranks["py3-none-any"]}
        else:
            url = f"https://pypi.org/pypi/{name}/{version}/json"
            metadata_raw = fetch(url, "pypi.org", 8 * 1024 * 1024)
            (metadata_dir / f"{name}.json").write_bytes(metadata_raw)
            entry, rank = choose_wheel(name, version, hashes, strict_json(metadata_raw),
                                       ranks, target["python"])
            raw = fetch(entry["url"], "files.pythonhosted.org", entry["size"])
            digest = sha(raw)
            if len(raw) != entry["size"] or digest != entry["digests"]["sha256"]:
                raise ValueError("Wheel size or digest mismatch")
            filename = entry["filename"]
            record = {"name": name, "version": version, "filename": filename,
                      "sha256": digest, "size": len(raw), "source": entry["url"],
                      "metadata_url": url, "metadata_sha256": sha(metadata_raw),
                      "requires_python": entry.get("requires_python"), "tag_rank": rank}
        (wheelhouse / filename).write_bytes(raw)
        if sha((wheelhouse / filename).read_bytes()) != digest:
            raise ValueError("Written wheel differs")
        return record

    for name, (version, hashes) in sorted(packages.items()):
        try:
            record = package_task(name, version, hashes)
            report["files"].append(record)
            print(json.dumps({"downloaded": record["name"], "size": record["size"]}), flush=True)
        except (OSError, ValueError, KeyError, TypeError) as error:
            report["errors"].append({"name": name, "error_type": type(error).__name__})
        (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        if report["errors"]:
            break
    report["completed"] = not report["errors"] and len(report["files"]) == len(packages)
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
