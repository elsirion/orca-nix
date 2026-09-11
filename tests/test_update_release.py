import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from scripts.update_release import ASSETS, build_manifest, update_manifest

HASH = "sha256-" + base64.b64encode(bytes(32)).decode()


class ReleaseUpdateTests(unittest.TestCase):
    def setUp(self):
        self.current = {"version": "1.4.197", "sources": {}}
        self.release = {
            "tag_name": "v1.4.199",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": name, "digest": "sha256:" + "00" * 32}
                for name in ASSETS.values()
            ],
        }
        self.prefetch = Mock(return_value=HASH)

    def test_updates_both_architectures(self):
        updated = build_manifest(self.release, self.current, self.prefetch)
        self.assertEqual(updated["version"], "1.4.199")
        self.assertEqual(set(updated["sources"]), set(ASSETS))
        for system, filename in ASSETS.items():
            self.assertEqual(
                updated["sources"][system], {"file": filename, "hash": HASH}
            )
            self.prefetch.assert_any_call(
                f"https://github.com/stablyai/orca/releases/download/v1.4.199/{filename}"
            )

    def test_unchanged_release_does_not_download(self):
        self.release["tag_name"] = "v1.4.197"
        self.assertEqual(
            build_manifest(self.release, self.current, self.prefetch), self.current
        )
        self.prefetch.assert_not_called()

    def test_refuses_unstable_invalid_and_older_releases(self):
        for change in [
            {"draft": True},
            {"prerelease": True},
            {"tag_name": "v1.4.198-rc.1"},
            {"tag_name": "1.4.199"},
            {"tag_name": "v1.4.196"},
            {"tag_name": "v1.4.199;echo unsafe"},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_manifest(self.release | change, self.current, self.prefetch)
        self.prefetch.assert_not_called()

    def test_compares_versions_numerically(self):
        self.release["tag_name"] = "v1.4.1000"
        self.assertEqual(
            build_manifest(self.release, self.current, self.prefetch)["version"],
            "1.4.1000",
        )

    def test_requires_both_assets_before_downloading(self):
        self.release["assets"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            build_manifest(self.release, self.current, self.prefetch)
        self.prefetch.assert_not_called()

    def test_verifies_github_digest(self):
        self.release["assets"][0]["digest"] = "sha256:" + "ff" * 32
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            build_manifest(self.release, self.current, self.prefetch)

    def test_can_hash_assets_without_github_digest(self):
        for asset in self.release["assets"]:
            asset.pop("digest")
        self.assertEqual(
            build_manifest(self.release, self.current, self.prefetch)["version"],
            "1.4.199",
        )

    def test_invalid_nix_hash_is_rejected(self):
        self.prefetch.return_value = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "Invalid SHA-256"):
            build_manifest(self.release, self.current, self.prefetch)

    def test_failure_leaves_manifest_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            original = json.dumps(self.current) + "\n"
            path.write_text(original)
            self.prefetch.side_effect = [HASH, RuntimeError("download failed")]
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                update_manifest(path, self.release, self.prefetch)
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_success_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(self.current))
            update_manifest(path, self.release, self.prefetch)
            written = path.read_text()
            timestamp = path.stat().st_mtime_ns
            update_manifest(path, self.release, self.prefetch)
            self.assertEqual(path.read_text(), written)
            self.assertEqual(path.stat().st_mtime_ns, timestamp)
            self.assertEqual(self.prefetch.call_count, 2)
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
