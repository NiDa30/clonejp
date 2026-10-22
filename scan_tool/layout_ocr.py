"""Local line detection/Japanese recognition plus batched Vietnamese OCR.

Models ship inside the pinned RapidOCR wheel. No model-host downloads at runtime.
"""
import csv
import io
import re
import unicodedata
from pathlib import Path

import cv2
import numpy as np


def has_japanese(text):
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))


def has_latin(text):
    return any("LATIN" in unicodedata.name(char, "") for char in text)


def latin_spans(text, words):
    """Locate Latin runs in mixed lines using CTC-aligned character boxes."""
    cursor = 0
    run = []
    spans = []
    for token, confidence, box in words:
        token = str(token)
        start = text.find(token, cursor)
        if start < 0:
            return []  # Leave the original result intact when alignment is ambiguous.
        cursor = start + len(token)
        if has_japanese(token):
            if run:
                spans.append(run)
                run = []
        elif has_latin(token) or run:
            run.append((start, cursor, token, box))
    if run:
        spans.append(run)
    return [run for run in spans if sum(has_latin(char) for item in run for char in item[2]) >= 3]


def parse_mosaic_tsv(text, slots):
    groups = [[] for _ in slots]
    for row in csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE):
        word = (row.get("text") or "").strip()
        if not word:
            continue
        try:
            confidence = float(row["conf"])
            center = int(row["top"]) + int(row["height"]) / 2
            left = int(row["left"])
        except (KeyError, ValueError):
            continue
        if confidence < 0:
            continue
        for index, (top, bottom) in enumerate(slots):
            if top <= center < bottom:
                groups[index].append((left, word, confidence))
                break
    return [(" ".join(item[1] for item in sorted(words)),
             sum(item[2] for item in words) / len(words) if words else None) for words in groups]


class LayoutOCR:
    def __init__(self):
        cv2.setNumThreads(1)
        import rapidocr
        from rapidocr import RapidOCR
        models = Path(rapidocr.__file__).parent / "models"
        self.engine = RapidOCR(params={
            "Global.use_cls": False, "Global.log_level": "warning",
            "Global.max_side_len": 2600, "Global.return_word_box": True,
            "Det.limit_side_len": 1600,
            "Det.model_path": str(models / "PP-OCRv6_det_small.onnx"),
            "Rec.model_path": str(models / "PP-OCRv6_rec_small.onnx"),
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })

    def read(self, image_path, base, executable, run_command):
        image = cv2.imread(str(image_path))
        if image is None:
            raise RuntimeError("Không mở được ảnh trang để nhận dạng.")
        result = self.engine(image)
        if not result.txts:
            return "", {"regions": [], "review_regions": 0}
        regions = [{"text": text, "score": float(score), "box": box.tolist(),
                    "engine": "rapidocr_ppocrv6"}
                   for text, score, box in zip(result.txts, result.scores, result.boxes)]
        requests = []
        for index, region in enumerate(regions):
            text = region["text"]
            if not has_latin(text):
                continue
            if not has_japanese(text):
                requests.append((index, 0, len(text), region["box"]))
            else:
                words = result.word_results[index] if index < len(result.word_results) else []
                for run in latin_spans(text, words):
                    points = np.concatenate([np.asarray(item[3]) for item in run], axis=0)
                    x1, y1 = points.min(axis=0)
                    x2, y2 = points.max(axis=0)
                    requests.append((index, run[0][0], run[-1][1], [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]))
        crops = []
        valid = []
        height, width = image.shape[:2]
        for request in requests:
            points = np.asarray(request[3], dtype=np.float32)
            points[:, 0] = np.clip(points[:, 0], 0, width - 1)
            points[:, 1] = np.clip(points[:, 1], 0, height - 1)
            crop_width = max(1, round(max(np.linalg.norm(points[1] - points[0]), np.linalg.norm(points[2] - points[3]))))
            crop_height = max(1, round(max(np.linalg.norm(points[3] - points[0]), np.linalg.norm(points[2] - points[1]))))
            target = np.asarray([[0, 0], [crop_width, 0], [crop_width, crop_height], [0, crop_height]], dtype=np.float32)
            transform = cv2.getPerspectiveTransform(points, target)
            crop = cv2.warpPerspective(image, transform, (crop_width, crop_height), borderMode=cv2.BORDER_REPLICATE)
            if not crop.size:
                continue
            factor = min(2.0, 64 / crop.shape[0])
            crop = cv2.resize(crop, (max(1, round(crop.shape[1] * factor)), max(1, round(crop.shape[0] * factor))))
            crops.append(crop)
            valid.append(request)
        replacements = {}
        # Bounded batches prevent very tall images on dense pages.
        for offset in range(0, len(crops), 24):
            batch = crops[offset:offset + 24]
            canvas_width = max(crop.shape[1] for crop in batch) + 32
            canvas_height = sum(crop.shape[0] + 32 for crop in batch) + 16
            canvas = np.full((canvas_height, canvas_width, 3), 255, dtype=np.uint8)
            slots = []
            top = 16
            for crop in batch:
                bottom = top + crop.shape[0]
                canvas[top:bottom, 16:16 + crop.shape[1]] = crop
                slots.append((top - 8, bottom + 8))
                top = bottom + 32
            mosaic = base.with_name(base.name + f"-latin-{offset}")
            png = mosaic.with_suffix(".png")
            tsv = mosaic.with_suffix(".tsv")
            cv2.imwrite(str(png), canvas)
            try:
                run_command([executable, str(png), str(mosaic), "-l", "vie+eng", "--psm", "6",
                             "-c", "tessedit_create_tsv=1"])
                results = parse_mosaic_tsv(tsv.read_text(encoding="utf-8"), slots)
                for j, (text, confidence) in enumerate(results):
                    index, start, end, _ = valid[offset + j]
                    if text and confidence is not None and confidence >= 30:
                        replacements.setdefault(index, []).append((start, end, text, confidence))
            finally:
                png.unlink(missing_ok=True)
                tsv.unlink(missing_ok=True)
        for index, changes in replacements.items():
            region = regions[index]
            region["raw_text"] = region["text"]
            for start, end, text, confidence in sorted(changes, reverse=True):
                region["text"] = region["text"][:start] + text + region["text"][end:]
            region["engine"] += "+tesseract_vie"
            region["latin_score"] = min(change[3] for change in changes)
        review = sum(region["score"] < .8 or region.get("latin_score", 100) < 65 for region in regions)
        text = "\n".join(region["text"] for region in regions)
        return text, {"regions": regions, "review_regions": review}
