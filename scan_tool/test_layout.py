import tempfile
import unittest
from pathlib import Path

import fitz

from scan_tool.layout_ocr import has_japanese, latin_spans, parse_mosaic_tsv
from scan_tool.worker import write_layout_pdf


class LayoutTests(unittest.TestCase):
    def test_mixed_language_spans_preserve_japanese_boundaries(self):
        box = [[0, 0], [20, 0], [20, 10], [0, 10]]
        text = "青春 Tôi học 日本"
        words = [(token, .9, box) for token in ["青", "春", "Tôi", "học", "日", "本"]]
        runs = latin_spans(text, words)
        self.assertEqual(len(runs), 1)
        self.assertEqual(text[runs[0][0][0]:runs[0][-1][1]], "Tôi học")
        self.assertTrue(has_japanese(text))

    def test_ambiguous_character_alignment_does_not_guess(self):
        self.assertEqual(latin_spans("日本", [("missing", .9, [])]), [])

    def test_mosaic_words_go_back_to_their_own_lines(self):
        tsv = "level\tleft\ttop\theight\tconf\ttext\n5\t60\t12\t10\t80\tNhật\n5\t10\t12\t10\t90\tTiếng\n5\t10\t70\t10\t70\tViệt\n"
        result = parse_mosaic_tsv(tsv, [(0, 40), (60, 100)])
        self.assertEqual(result, [("Tiếng Nhật", 85), ("Việt", 70)])

    def test_pdf_text_layer_preserves_both_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with fitz.open() as source:
                page = source.new_page(width=400, height=200)
                page.get_pixmap().save(root / "page.png")
            text = "・日本語 Tôi học tiếng Việt ①"
            write_layout_pdf(root / "page.png", root / "page.pdf", fitz.Rect(0, 0, 400, 200),
                             [{"text": text, "box": [[10, 20], [390, 20], [390, 60], [10, 60]]}])
            with fitz.open(root / "page.pdf") as pdf:
                self.assertEqual(pdf[0].get_text().strip(), text)


if __name__ == "__main__":
    unittest.main()
