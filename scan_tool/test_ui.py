import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import streamlit as st
from streamlit.testing.v1 import AppTest


class InputTests(unittest.TestCase):
    def check_upload(self, ready):
        upload = io.BytesIO(b"%PDF fixture")
        upload.name = "Giáo trình.pdf"
        upload.file_id = "test-upload"
        jobs = Mock()
        jobs.plan = {"workers": 2}
        jobs.jobs.return_value = []
        st.cache_resource.clear()
        with tempfile.TemporaryDirectory() as directory, \
                patch("scan_tool.core.STORE", Path(directory)), \
                patch("scan_tool.core.JobManager", return_value=jobs), \
                patch("scan_tool.core.engine_status", return_value={
                    "ready": ready, "message": "Sẵn sàng" if ready else "Thiếu bộ nhận dạng: jpn, vie"}), \
                patch("streamlit.file_uploader", return_value=[upload]):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=15).run()
            self.assertFalse(app.exception)
            start = next(button for button in app.button if button.label == "Bắt đầu xử lý")
            self.assertEqual(start.disabled, not ready)
            self.assertEqual(len(app.session_state["inputs"]), 1)
            app.run()
            self.assertEqual(len(app.session_state["inputs"]), 1, "Rerender must not duplicate uploads")
            if ready:
                next(button for button in app.button if button.label == "✕").click().run()
                self.assertEqual(len(app.session_state["inputs"]), 0)
                self.assertTrue(next(b for b in app.button if b.label == "Bắt đầu xử lý").disabled)
            else:
                self.assertTrue(any("Chưa thể bắt đầu" in item.value for item in app.info))
        st.cache_resource.clear()

    def test_file_selection_enables_start_without_second_add_button(self):
        self.check_upload(True)

    def test_missing_language_keeps_start_disabled_and_explains_why(self):
        self.check_upload(False)


if __name__ == "__main__":
    unittest.main()
