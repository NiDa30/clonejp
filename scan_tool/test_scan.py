import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from scan_tool.core import JobManager, atomic_json, engine_status, fetch_document, resource_plan, safe_filename
from scan_tool.worker import process_document


class CoreTests(unittest.TestCase):
    def test_link_download_keeps_input_name_without_overwriting_job_metadata(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="job.json"')
                self.end_headers()
                self.wfile.write(b"%PDF-test fixture")
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                atomic_json(folder / "job.json", {"keep": True})
                target = fetch_document(f"http://127.0.0.1:{server.server_port}/download", folder)
                self.assertEqual(target.name, "job.json")
                self.assertEqual(target.parent.name, "input")
                self.assertEqual(json.loads((folder / "job.json").read_text()), {"keep": True})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_names_and_output_stems(self):
        self.assertEqual(safe_filename("Giáo trình 日本語.pdf"), "Giáo trình 日本語.pdf")
        self.assertEqual(safe_filename("CON.pdf"), "_CON.pdf")
        self.assertNotIn("/", safe_filename("../outside.pdf"))

    def test_resource_budget_never_oversubscribes_low_memory(self):
        from types import SimpleNamespace
        with patch("scan_tool.core.psutil.virtual_memory", return_value=SimpleNamespace(available=400 * 1024 ** 2)):
            self.assertEqual(resource_plan()["workers"], 1)

    def test_one_document_failure_does_not_stop_another(self):
        if not engine_status()["ready"]:
            self.skipTest("Requires Tesseract with jpn/vie/eng")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            pdf = folder / "valid.pdf"
            with fitz.open() as doc:
                doc.new_page().insert_text((30, 50), "A document with enough native text to be extracted without raster OCR. " * 2)
                doc.save(pdf)
            manager = JobManager(folder / "jobs")
            good = manager.create(pdf.name, "file", path=str(pdf), searchable=True)
            bad = manager.create("missing.pdf", "file", path=str(folder / "missing.pdf"))
            manager.active[good].result(timeout=60)
            manager.active[bad].result(timeout=60)
            states = {job["id"]: job["state"] for job in manager.jobs()}
            self.assertEqual(states[good], "completed")
            self.assertEqual(states[bad], "failed")
            manager.pool.shutdown()

    def test_100_pages_resume_and_matching_output_names(self):
        if not engine_status()["ready"]:
            self.skipTest("Requires Tesseract with jpn/vie/eng")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "Giáo trình 100.pdf"
            with fitz.open() as pdf:
                for index in range(100):
                    pdf.new_page().insert_text((30, 50), f"Page {index + 1}: A hundred-page textbook fixture with native text and independent page processing.")
                pdf.save(source)
            atomic_json(folder / "job.json", {"input_path": str(source), "searchable": False})
            self.assertEqual(process_document(folder), 0)
            output = folder / "output/Giáo trình 100.md"
            text = output.read_text(encoding="utf-8")
            self.assertEqual(text.count("## Trang "), 100)
            markers = list((folder / "pages").glob("*/page-*.json"))
            previous = [path.stat().st_mtime_ns for path in markers]
            self.assertEqual(process_document(folder), 0)
            self.assertEqual(previous, [path.stat().st_mtime_ns for path in markers])
            report = json.loads((folder / "output/Giáo trình 100.json").read_text())
            self.assertEqual(len(report["pages"]), 100)


if __name__ == "__main__":
    unittest.main()
