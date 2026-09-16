import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import update_source_overlay as overlay  # noqa: E402

HASH_A = "sha256-LS9VEj4uUFs6F9NTnq2y8AMEXbuVLp9dpIExSTegt+4="
HASH_B = "sha256-yC2d31MkMeDaUexdGJmg4xWqu453/ORezOf61HM/yWo="
CURRENT = {
    "version": "1.4.200",
    "sourceHash": HASH_A,
    "pnpmDepsHash": HASH_B,
    "patches": ["linux-agent-bubblewrap-sandbox.patch"],
}


class NeedsUpdate(unittest.TestCase):
    def test_same_version_is_up_to_date(self):
        self.assertFalse(overlay.needs_update(CURRENT, "1.4.200"))

    def test_new_release_needs_update(self):
        self.assertTrue(overlay.needs_update(CURRENT, "1.4.201"))

    def test_force_repins_the_same_version(self):
        self.assertTrue(overlay.needs_update(CURRENT, "1.4.200", force=True))


class BuildOverlay(unittest.TestCase):
    def test_keeps_patches_and_replaces_hashes(self):
        self.assertEqual(
            overlay.build_overlay(CURRENT, "1.4.201", HASH_B, HASH_A),
            {
                "version": "1.4.201",
                "sourceHash": HASH_B,
                "pnpmDepsHash": HASH_A,
                "patches": ["linux-agent-bubblewrap-sandbox.patch"],
            },
        )

    def test_rejects_malformed_hashes(self):
        with self.assertRaises(ValueError):
            overlay.build_overlay(CURRENT, "1.4.201", "sha256-short", HASH_A)
        with self.assertRaises(ValueError):
            overlay.build_overlay(CURRENT, "1.4.201", HASH_A, "0" * 64)


class ParseGotHash(unittest.TestCase):
    def test_extracts_the_hash_nix_reports(self):
        output = (
            "error: hash mismatch in fixed-output derivation '/nix/store/x.drv':\n"
            f"         specified: {overlay.FAKE_HASH}\n"
            f"            got:    {HASH_A}\n"
        )
        self.assertEqual(overlay.parse_got_hash(output), HASH_A)

    def test_fails_without_a_reported_hash(self):
        with self.assertRaises(ValueError):
            overlay.parse_got_hash("error: patch does not apply")


class ShippedManifest(unittest.TestCase):
    def test_overlay_manifest_is_well_formed(self):
        manifest = json.loads((overlay.OVERLAY).read_text())
        self.assertEqual(set(manifest), {"version", "sourceHash", "pnpmDepsHash", "patches"})
        for patch in manifest["patches"]:
            self.assertTrue((overlay.ROOT / "nix" / "patches" / patch).is_file(), patch)


if __name__ == "__main__":
    unittest.main()
