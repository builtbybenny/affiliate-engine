from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import config
from publishers import instagram

import publish as publish_script


class PublishGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "published_log.csv"
        self.patch = patch.object(config, "PUBLISHED_LOG", self.log)
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def test_stray_header_rows_are_dropped_and_one_header_is_written(self) -> None:
        header = publish_script._LOG_HEADER
        with open(self.log, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["2026-10-26", "reel", "framer", "1", "2", "", "u"])  # no header yet
            w.writerow(header)
            w.writerow(["2026-10-27", "reel", "gohighlevel", "3", "4", "", "u"])
            w.writerow(header)
            w.writerow(header)

        publish_script.log_published(date(2026, 10, 28), "reel", "systeme", "5", "6", ["u"])

        lines = self.log.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(lines[0], ",".join(header))
        self.assertEqual(sum(1 for line in lines if line.startswith("date,format")), 1)
        self.assertEqual(len(lines), 4)  # header + three posts

    def test_short_rows_are_padded_not_dropped(self) -> None:
        with open(self.log, "w", newline="", encoding="utf-8") as f:
            f.write("date,format,product_id,ig_media_id,fb_post_id,media_urls\n")
            f.write("2026-09-25,carousel,gohighlevel,11,22,u\n")

        publish_script.log_published(date(2026, 10, 28), "reel", "systeme", "5", "6", ["u"])
        with self.log.open(encoding="utf-8") as handle:
            rows = list(csv.reader(handle))[1:]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(len(row) == len(publish_script._LOG_HEADER) for row in rows))

    def test_already_published_is_scoped_to_date_and_format(self) -> None:
        publish_script.log_published(date(2026, 10, 28), "reel", "systeme", "5", "6", ["u"])
        self.assertTrue(publish_script.already_published(date(2026, 10, 28), "reel"))
        self.assertFalse(publish_script.already_published(date(2026, 10, 28), "carousel"))
        self.assertFalse(publish_script.already_published(date(2026, 10, 27), "reel"))

    def test_republishing_a_logged_slot_is_skipped_without_touching_media(self) -> None:
        publish_script.log_published(date(2026, 10, 28), "carousel", "beehiiv", "5", "6", ["u"])
        with patch.object(publish_script, "latest_render") as render:
            publish_script.publish("carousel", date(2026, 10, 28), dry_run=False, targets={"ig"})
        render.assert_not_called()

    def test_quota_errors_get_the_long_ladder(self) -> None:
        short = (15, 30, 60)
        quota = "403 OAuthException: Application request limit reached (code 4)"
        settling = "400 OAuthException: Only photo or video can be accepted as media type. (code 9004)"
        self.assertEqual(instagram._ladder(quota, short), instagram._QUOTA_LADDER)
        self.assertEqual(instagram._ladder(settling, short), short)
        self.assertEqual(instagram._CONTAINER_LADDER, short)
        self.assertGreater(sum(instagram._QUOTA_LADDER), 600)

    def test_quota_errors_are_retryable_but_permission_errors_are_not(self) -> None:
        self.assertTrue(instagram._retryable("403 OAuthException: Application request limit reached (code 4)"))
        self.assertTrue(instagram._retryable("400 OAuthException: ... (code 9004)"))
        self.assertFalse(instagram._retryable("403 OAuthException: API access blocked (code 200)"))
        self.assertFalse(instagram._retryable("401 Invalid OAuth access token (code 190)"))

    def test_preflight_fails_before_any_container_is_built(self) -> None:
        with patch.object(config, "ACCESS_TOKEN", ""):
            with self.assertRaises(instagram.IGError):
                instagram.ensure_available()


if __name__ == "__main__":
    unittest.main()
