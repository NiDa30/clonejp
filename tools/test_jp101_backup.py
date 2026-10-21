import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jp101_backup as backup


class BackupTests(unittest.TestCase):
    def test_learning_navigation_excludes_actions_and_normalizes(self):
        self.assertEqual(backup.learning_url("https://www.japanesepod101.com/lesson/example?page=2&utm_source=email#top"),
                         "https://www.japanesepod101.com/lesson/example?page=2")
        for url in ["https://www.japanesepod101.com/logout", "https://www.japanesepod101.com/wordbank/delete",
                    "https://www.japanesepod101.com/lesson/a?action=delete", "https://other.test/lesson/a"]:
            self.assertIsNone(backup.learning_url(url))

    def test_auto_discovers_pages_and_resumes_without_visiting_again(self):
        from types import SimpleNamespace
        dashboard = "https://www.japanesepod101.com/dashboard"
        lesson = "https://www.japanesepod101.com/lesson/example"
        class Page:
            url = dashboard
            visits = []
            def goto(self, url, **kwargs):
                self.url = url
                self.visits.append(url)
                return SimpleNamespace(status=200)
            def wait_for_timeout(self, *args):
                pass
            def locator(self, *args):
                return SimpleNamespace(count=lambda: 0)
            def evaluate(self, script):
                return {"height": 100, "links": [lesson, dashboard, "https://www.japanesepod101.com/logout"]}
            def close(self):
                pass
        page = Page()
        context = SimpleNamespace(pages=[SimpleNamespace(url=dashboard)], new_page=lambda: page)
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, "ROOT", Path(directory)), \
                patch.object(backup, "capture", return_value=[]), \
                patch.object(backup, "download_all") as downloads, patch.object(backup.time, "sleep"):
            manifest = {"pages": {}, "downloads": {}}
            backup.auto_backup(context, manifest)
            self.assertEqual(page.visits, [dashboard, lesson])
            backup.auto_backup(context, manifest)
            self.assertEqual(page.visits, [dashboard, lesson])
            self.assertEqual(downloads.call_count, 2)

    def test_site_boundary(self):
        self.assertTrue(backup.site_url("https://www.japanesepod101.com/dashboard"))
        self.assertFalse(backup.site_url("https://japanesepod101.com.evil.test/"))
        self.assertFalse(backup.site_url("http://www.japanesepod101.com/"))

    def test_download_candidates(self):
        self.assertTrue(backup.download_candidate({"url": "https://cdn.example/a.PDF?signature=x"}))
        self.assertTrue(backup.download_candidate({"url": "https://example.com/export", "text": "Download PDF"}))
        self.assertFalse(backup.download_candidate({"url": "javascript:download()", "download": True}))
        self.assertFalse(backup.download_candidate({"url": "https://example.com/lesson", "text": "Play"}))

    def test_windows_names(self):
        for name in ["CON", "aux.txt", "NUL", "COM1.mp3", "LPT9.pdf", "a/b:c?.pdf", "..."]:
            actual = backup.safe_name(name)
            self.assertTrue(actual)
            self.assertNotIn("/", actual)
            self.assertNotIn(":", actual)
        self.assertEqual(backup.safe_name("bai hoc.pdf"), "bai hoc.pdf")

    def test_resume_skips_existing_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.pdf").write_bytes(b"example")
            manifest = {"downloads": {"https://example.com/file.pdf": {"file": "existing.pdf"}}}
            class NoRequests:
                @property
                def request(self):
                    raise AssertionError("Must not request a completed download")
            with patch.object(backup, "ROOT", root):
                backup.download_all(NoRequests(), manifest)


if __name__ == "__main__":
    unittest.main()
