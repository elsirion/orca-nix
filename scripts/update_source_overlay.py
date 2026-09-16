"""Re-pin the source overlay (nix/source-overlay.json) to the release in nix/release.json.

The overlay rebuilds Orca's JavaScript from the upstream tag plus nix/patches. Its two hashes
change with every release, so this runs right after update_release.py: it prefetches the source
tree, then lets Nix report the pnpm dependency hash. A patch that no longer applies surfaces as a
build failure here, which keeps CI from publishing a pin the overlay cannot build.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM = "stablyai/orca"
ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "nix" / "release.json"
OVERLAY = ROOT / "nix" / "source-overlay.json"
FAKE_HASH = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
SRI_RE = r"sha256-[A-Za-z0-9+/]{43}="
GOT_RE = re.compile(r"got:\s+(" + SRI_RE + ")")


def needs_update(overlay, version, force=False):
    return force or overlay["version"] != version


def build_overlay(current, version, source_hash, pnpm_deps_hash):
    for name, value in (("source", source_hash), ("pnpm dependency", pnpm_deps_hash)):
        if not re.fullmatch(SRI_RE, value):
            raise ValueError(f"Invalid {name} hash: {value!r}")
    return {
        "version": version,
        "sourceHash": source_hash,
        "pnpmDepsHash": pnpm_deps_hash,
        "patches": current["patches"],
    }


def parse_got_hash(output):
    """Extract the hash Nix reports for a fixed-output derivation built with a placeholder."""
    match = GOT_RE.search(output)
    if match is None:
        raise ValueError("Nix did not report a fixed-output hash; see the build output above")
    return match.group(1)


def write_json(path, data):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(data, file, indent=2)
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


def prefetch_source_hash(version):
    url = f"https://github.com/{UPSTREAM}/archive/refs/tags/v{version}.tar.gz"
    result = subprocess.run(
        ["nix", "store", "prefetch-file", "--json", "--unpack", "--hash-type", "sha256", url],
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    return json.loads(result.stdout)["hash"]


def build_pnpm_deps(expect_failure):
    result = subprocess.run(
        ["nix", "build", "--no-link", "-L", f"{ROOT}#orca-ide.appBundle.pnpmDeps"],
        capture_output=True,
        text=True,
        timeout=7200,
    )
    if expect_failure and result.returncode == 0:
        raise RuntimeError("Expected the placeholder hash to be rejected")
    if not expect_failure and result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise RuntimeError("Building the pnpm dependencies with the new hash failed")
    return result.stderr


def main(argv):
    force = "--force" in argv
    version = json.loads(RELEASE.read_text())["version"]
    current = json.loads(OVERLAY.read_text())
    if not needs_update(current, version, force):
        print(f"Source overlay already pinned to Orca {version}")
        return
    source_hash = prefetch_source_hash(version)
    # A placeholder makes Nix print the real dependency hash instead of silently accepting one.
    write_json(OVERLAY, build_overlay(current, version, source_hash, FAKE_HASH))
    output = build_pnpm_deps(expect_failure=True)
    try:
        pnpm_deps_hash = parse_got_hash(output)
    except ValueError:
        sys.stderr.write(output)
        raise
    write_json(OVERLAY, build_overlay(current, version, source_hash, pnpm_deps_hash))
    build_pnpm_deps(expect_failure=False)
    print(f"Updated source overlay {current['version']} -> {version}")


if __name__ == "__main__":
    main(sys.argv[1:])
