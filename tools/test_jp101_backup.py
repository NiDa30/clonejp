import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import jp101_backup as backup


class BackupTests(unittest.TestCase):
    def test_error_report_does_not_copy_sensitive_exception_text(self):
        report = backup.error_summary(RuntimeError(
            'Page.goto: net::ERR_CONNECTION_RESET at https://example.com/?token=secret'), "navigation")
        self.assertEqual(report["code"], "ERR_CONNECTION_RESET")
        self.assertNotIn("secret", str(report))
        self.assertEqual(backup.error_summary(RuntimeError("Execution context was destroyed"), "capture")["code"],
                         "navigation_context_destroyed")

    def test_discovery_counts_distinguish_rejected_lesson_links(self):
        links = [{"url": "https://www.japanesepod101.com/lesson/a"},
                 {"url": "https://www.japanesepod101.com/lesson/b?unknown=value"},
                 {"url": "https://www.japanesepod101.com/lesson-library"}]
        self.assertEqual(backup.discovery_counts(links), {"lesson_links_seen": 2, "lesson_links_accepted": 1})

    def test_lesson_folders_use_breadcrumb_course_and_unique_identity(self):
        data = {"heading": "Lesson 1: Greetings", "course_links": [
            {"url": "https://www.japanesepod101.com/lesson-library/beginner", "text": "Beginner"}]}
        first = backup.page_folder("https://www.japanesepod101.com/lesson/first", data)
        second = backup.page_folder("https://www.japanesepod101.com/lesson/second", data)
        self.assertEqual(first.parts[0], "lessons")
        self.assertTrue(first.parts[1].startswith("Beginner--"))
        self.assertNotEqual(first, second)
        unknown = backup.page_folder("https://www.japanesepod101.com/lesson/first", {})
        self.assertEqual(unknown.parts[1], "Chua-xac-dinh-khoa")

    def test_shared_asset_is_placed_in_each_lesson_and_can_be_repeated(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, "ROOT", Path(directory)):
            root = Path(directory)
            (root / "downloads").mkdir()
            (root / "downloads/audio.mp3").write_bytes(b"audio data")
            item = {"file": "downloads/audio.mp3", "sources": ["lesson-one", "lesson-two"]}
            manifest = {"pages": {"lesson-one": {"folder": "lessons/course/one"},
                                  "lesson-two": {"folder": "lessons/course/two"}}}
            backup.organize_download(item, manifest)
            backup.organize_download(item, manifest)
            self.assertEqual(len(item["lesson_files"]), 2)
            for path in item["lesson_files"]:
                self.assertEqual((root / path).read_bytes(), b"audio data")

    def test_existing_page_moves_to_organized_index_without_deleting_original(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, "ROOT", Path(directory)):
            root = Path(directory)
            old = root / "pages/old"
            old.mkdir(parents=True)
            backup.write_json(old / "page.json", {"title": "A lesson"})
            (old / "content.txt").write_text("Lesson text")
            url = "https://www.japanesepod101.com/lesson/example"
            manifest = {"pages": {url: {"folder": "pages/old"}}}
            backup.organize_saved_pages(manifest)
            target = root / manifest["pages"][url]["folder"]
            self.assertEqual((target / "content.txt").read_text(), "Lesson text")
            self.assertTrue((old / "content.txt").exists())

    def test_tab_menu_does_not_read_title_during_navigation(self):
        page = Mock()
        page.url = "https://www.japanesepod101.com/dashboard?private=value"
        page.is_closed.return_value = False
        page.title.side_effect = RuntimeError("Execution context was destroyed")
        with patch("builtins.print") as output:
            self.assertEqual(backup.list_site_tabs(Mock(pages=[page])), [page])
            self.assertNotIn("private", str(output.call_args_list))
        page.title.assert_not_called()

    def test_structure_retries_navigation_then_succeeds(self):
        page = Mock(url="https://www.japanesepod101.com/dashboard")
        page.is_closed.return_value = False
        action = Mock(side_effect=[RuntimeError("Execution context was destroyed, most likely because of a navigation"), None])
        self.assertTrue(backup.read_selected_page(page, action, RuntimeError))
        self.assertEqual(action.call_count, 2)

    def test_structure_stops_retrying_without_raising(self):
        page = Mock(url="https://www.japanesepod101.com/dashboard")
        page.is_closed.return_value = False
        action = Mock(side_effect=RuntimeError("Execution context was destroyed"))
        self.assertFalse(backup.read_selected_page(page, action, RuntimeError))
        self.assertEqual(action.call_count, 3)

    def test_structure_does_not_read_closed_or_redirected_tab(self):
        action = Mock()
        page = Mock(url="https://other.example/login")
        page.is_closed.return_value = True
        self.assertFalse(backup.read_selected_page(page, action, RuntimeError))
        page.is_closed.return_value = False
        self.assertFalse(backup.read_selected_page(page, action, RuntimeError))
        action.assert_not_called()

    def test_terminal_wait_keeps_browser_events_running(self):
        import threading
        from types import SimpleNamespace
        pumped = threading.Event()
        page = SimpleNamespace(is_closed=lambda: False,
                               wait_for_timeout=lambda _: pumped.set())
        def reply(prompt):
            if not pumped.wait(2):
                raise AssertionError("Browser events were blocked while waiting for input")
            return "auto"
        with patch("builtins.input", side_effect=reply):
            self.assertEqual(backup.browser_input(SimpleNamespace(pages=[page]), "> "), "auto")

    def test_terminal_eof_propagates(self):
        from types import SimpleNamespace
        with patch("builtins.input", side_effect=EOFError):
            with self.assertRaises(EOFError):
                backup.browser_input(SimpleNamespace(pages=[]), "> ")

    def test_learning_navigation_excludes_actions_and_normalizes(self):
        self.assertEqual(backup.learning_url("https://www.japanesepod101.com/lesson/example?page=2&utm_source=email#top"),
                         "https://www.japanesepod101.com/lesson/example?page=2")
        for url in ["https://www.japanesepod101.com/logout", "https://www.japanesepod101.com/wordbank/delete",
                    "https://www.japanesepod101.com/lesson/a?action=delete", "https://other.test/lesson/a"]:
            self.assertIsNone(backup.learning_url(url))

    def test_auto_refreshes_entry_pages_but_resumes_completed_lessons(self):
        from types import SimpleNamespace
        dashboard = "https://www.japanesepod101.com/dashboard"
        library = "https://www.japanesepod101.com/lesson-library"
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
            self.assertEqual(page.visits, [dashboard, lesson, library])
            backup.auto_backup(context, manifest)
            self.assertEqual(page.visits, [dashboard, lesson, library, dashboard, library])
            self.assertEqual(downloads.call_count, 2)

    def test_coverage_distinguishes_pages_download_links_and_files(self):
        import json
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, "ROOT", Path(directory)):
            root = Path(directory)
            (root / "saved.mp3").write_bytes(b"example")
            manifest = {"pages": {"https://www.japanesepod101.com/dashboard": {}},
                        "downloads": {"one": {"file": "saved.mp3"}, "two": {"error": "HTTP_403"}}}
            backup.update_coverage(manifest)
            report = json.loads((root / "coverage.json").read_text())
            self.assertEqual(report["saved_lesson_pages"], 0)
            self.assertEqual(report["download_links_found"], 2)
            self.assertEqual(report["downloaded_files"], 1)
            self.assertEqual(report["failed_downloads"], 1)
            self.assertIn("discovery_warning", report)
            self.assertNotIn("https://", (root / "coverage.json").read_text())

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
