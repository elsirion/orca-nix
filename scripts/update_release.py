"""Pin the latest stable upstream release; publish only after CI validates it."""

import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

UPSTREAM = "stablyai/orca"
ASSETS = {
    "x86_64-linux": "orca-linux.AppImage",
    "aarch64-linux": "orca-linux-arm64.AppImage",
}
MANIFEST = Path(__file__).resolve().parents[1] / "nix" / "release.json"


def version_tuple(version):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError(f"Not a stable release version: {version!r}")
    return tuple(map(int, version.split(".")))


def prefetch_hash(url):
    result = subprocess.run(
        ["nix", "store", "prefetch-file", "--json", "--hash-type", "sha256", url],
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    return json.loads(result.stdout)["hash"]


def build_manifest(release, current, prefetch=prefetch_hash):
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Refusing a draft or prerelease")
    tag = release["tag_name"]
    if not tag.startswith("v"):
        raise ValueError(f"Unexpected release tag: {tag!r}")
    version = tag[1:]
    latest = version_tuple(version)
    previous = version_tuple(current["version"])
    if latest < previous:
        raise ValueError("Refusing to downgrade the pinned release")
    if latest == previous:
        return current

    assets = {asset["name"]: asset for asset in release["assets"]}
    missing = set(ASSETS.values()) - assets.keys()
    if missing:
        raise ValueError(f"Release is incomplete; missing assets: {sorted(missing)}")
    sources = {}
    for system, filename in ASSETS.items():
        url = f"https://github.com/{UPSTREAM}/releases/download/{tag}/{filename}"
        hash_ = prefetch(url)
        if not re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", hash_):
            raise ValueError(f"Invalid SHA-256 from Nix for {filename}")
        digest = assets[filename].get("digest")
        actual = "sha256:" + base64.b64decode(hash_[7:], validate=True).hex()
        if digest is not None and digest != actual:
            raise ValueError(f"GitHub digest mismatch for {filename}")
        sources[system] = {"file": filename, "hash": hash_}
    return {"version": version, "sources": sources}


def update_manifest(path, release, prefetch=prefetch_hash):
    current = json.loads(path.read_text())
    updated = build_manifest(release, current, prefetch)
    if updated == current:
        print(f"Already pinned to Orca {current['version']}")
        return
    # Never leave one architecture updated when the other download fails.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(updated, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            temporary.unlink()
            raise
    try:
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Updated Orca {current['version']} -> {updated['version']}")


def main():
    result = subprocess.run(
        ["gh", "api", f"repos/{UPSTREAM}/releases/latest"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    update_manifest(MANIFEST, json.loads(result.stdout))


if __name__ == "__main__":
    main()
