"""Download Stockfish 18 binaries into engines/ (one-time setup).

Usage:
    python download_stockfish.py            # download for both platforms
    python download_stockfish.py --current  # only for the current OS

The app itself is fully offline; this script is only needed once after
cloning, because the engine binaries (~110 MB each) are too large for git.
"""

import argparse
import io
import os
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

RELEASE = "sf_18"
BASE = f"https://github.com/official-stockfish/Stockfish/releases/download/{RELEASE}"

TARGETS = {
    "linux": {
        "url": f"{BASE}/stockfish-ubuntu-x86-64.tar",
        "member_suffix": "stockfish-ubuntu-x86-64",
        "dest": Path("engines/linux/stockfish"),
    },
    "windows": {
        "url": f"{BASE}/stockfish-windows-x86-64.zip",
        "member_suffix": "stockfish-windows-x86-64.exe",
        "dest": Path("engines/windows/stockfish.exe"),
    },
}


def download(name: str, spec: dict):
    dest = spec["dest"]
    if dest.is_file():
        print(f"[skip] {dest} already exists")
        return
    print(f"[get ] {spec['url']}")
    with urllib.request.urlopen(spec["url"]) as response:
        payload = response.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if spec["url"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            member = next(m for m in archive.namelist()
                          if m.endswith(spec["member_suffix"]))
            dest.write_bytes(archive.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            member = next(m for m in archive.getnames()
                          if m.endswith(spec["member_suffix"]))
            extracted = archive.extractfile(member)
            dest.write_bytes(extracted.read())
    if name == "linux":
        dest.chmod(0o755)
    print(f"[ok  ] {dest} ({dest.stat().st_size // (1024 * 1024)} MB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", action="store_true",
                        help="download only for the current OS")
    args = parser.parse_args()

    os.chdir(Path(__file__).resolve().parent)
    if args.current:
        names = ["windows"] if os.name == "nt" else ["linux"]
    else:
        names = list(TARGETS)
    for name in names:
        download(name, TARGETS[name])
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
