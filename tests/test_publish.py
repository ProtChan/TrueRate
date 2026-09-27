import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from truerate.publish import write_sharded_site_payload


class ShardedSitePayloadTest(unittest.TestCase):
    def test_writes_manifest_and_multiple_chunks_without_losing_pairs(self):
        payload = {
            "metadata": {"unit": 10000},
            "brokers": [{"id": "a", "name": "A"}],
            "pairs": ["A/B", "C/D", "E/F"],
            "series": {
                "A/B": {"a": {"points": [{"date": "2026-01-01", "spot": 1.0}] * 6}},
                "C/D": {"a": {"points": [{"date": "2026-01-01", "spot": 2.0}] * 6}},
                "E/F": {"a": {"points": [{"date": "2026-01-01", "spot": 3.0}] * 6}},
            },
        }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / "site-series-999.json"
            stale.write_text("stale", encoding="utf-8")
            manifest_path = root / "site-data.json"

            chunks = write_sharded_site_payload(
                payload,
                manifest_path,
                target_bytes=260,
            )

            self.assertGreaterEqual(len(chunks), 2)
            self.assertFalse(stale.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["series"], {})
            self.assertEqual(manifest["pairs"], payload["pairs"])
            self.assertEqual(
                manifest["series_chunks"],
                [path.name for path in chunks],
            )

            merged = {}
            for path in chunks:
                part = json.loads(path.read_text(encoding="utf-8"))
                merged.update(part["series"])
            self.assertEqual(merged, payload["series"])

    def test_rejects_non_positive_target(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_sharded_site_payload(
                    {"series": {}},
                    Path(tmp) / "site-data.json",
                    target_bytes=0,
                )


if __name__ == "__main__":
    unittest.main()
