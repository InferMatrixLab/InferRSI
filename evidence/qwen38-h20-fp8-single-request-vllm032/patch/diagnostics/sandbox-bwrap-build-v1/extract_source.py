"""Extract the authenticated release with only its two local license symlinks."""
import argparse
import tarfile
from pathlib import Path


def extract(archive, destination):
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            root = member.isdir() and member.name == "bubblewrap-0.13.1"
            license_link = member.issym() and member.name in (
                "bubblewrap-0.13.1/COPYING.LIB", "bubblewrap-0.13.1/LICENSE"
            ) and member.linkname == "COPYING"
            if not (member.isfile() or member.isdir() or license_link):
                raise ValueError("Unexpected archive member type")
            if not root and not member.name.startswith("bubblewrap-0.13.1/"):
                raise ValueError("Unexpected archive root")
        destination.mkdir(exist_ok=False)
        source.extractall(destination, filter="data")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    extract(args.archive, args.destination)
