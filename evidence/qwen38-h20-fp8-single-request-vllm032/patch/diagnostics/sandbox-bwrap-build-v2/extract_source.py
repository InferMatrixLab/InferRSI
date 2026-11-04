"""Extract the authenticated release with only its two local license symlinks."""
import argparse
import tarfile
from pathlib import Path


def extract(archive, destination, archive_root):
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            root = member.isdir() and member.name == archive_root
            license_link = archive_root == "bubblewrap-0.13.1" and member.issym() and member.name in (
                "bubblewrap-0.13.1/COPYING.LIB", "bubblewrap-0.13.1/LICENSE"
            ) and member.linkname == "COPYING"
            if not (member.isfile() or member.isdir() or license_link):
                raise ValueError("Unexpected archive member type")
            if not root and not member.name.startswith(archive_root + "/"):
                raise ValueError("Unexpected archive root")
        destination.mkdir(exist_ok=False)
        source.extractall(destination, filter="data")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--root", required=True, choices=("bubblewrap-0.13.1", "libcap-2.78"))
    args = parser.parse_args()
    extract(args.archive, args.destination, args.root)
