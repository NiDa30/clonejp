"""Local document OCR. Each document runs in its own subprocess, one page at a time."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

import psutil

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".ocr-local"
MAX_DOWNLOAD = 1024 * 1024 * 1024


def engine_environment() -> dict:
    task_env = os.environ.copy()
    models = STORE / "tessdata"
    if all((models / (lang + ".traineddata")).is_file() for lang in ("jpn", "vie", "eng")):
        task_env["TESSDATA_PREFIX"] = str(models)
    task_env["OMP_THREAD_LIMIT"] = "1"
    task_env["OMP_NUM_THREADS"] = "1"
    return task_env


def safe_filename(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    stem, suffix = os.path.splitext(name)
    if stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                         *(f"LPT{i}" for i in range(1, 10))}:
        stem = "_" + stem
    return (stem[:85] or "tai-lieu") + suffix[:12]


def atomic_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows may briefly deny replacing a file being read by the UI.
    for attempt in range(10):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def find_tesseract() -> str | None:
    configured = os.environ.get("TESSERACT_CMD")
    if configured and Path(configured).is_file():
        return configured
    command = shutil.which("tesseract")
    if command:
        return command
    for parent in [os.environ.get("ProgramFiles", "C:/Program Files"),
                   os.environ.get("LOCALAPPDATA", "")]:
        candidate = Path(parent) / "Tesseract-OCR" / "tesseract.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def engine_status() -> dict:
    executable = find_tesseract()
    if not executable:
        return {"ready": False, "message": "Chưa tìm thấy Tesseract OCR. Xem hướng dẫn cài đặt bên dưới."}
    try:
        result = subprocess.run([executable, "--list-langs"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20,
                                env=engine_environment(),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        languages = set(result.stdout.splitlines()[1:])
        missing = sorted({"jpn", "vie", "eng"} - languages)
        if result.returncode or missing:
            return {"ready": False, "message": "Thiếu bộ nhận dạng: " + ", ".join(missing or ["không đọc được danh sách"]),
                    "executable": executable}
        return {"ready": True, "message": "Sẵn sàng · Nhật + Việt + Anh · OCR local", "executable": executable}
    except (OSError, subprocess.TimeoutExpired):
        return {"ready": False, "message": "Không chạy được Tesseract. Kiểm tra cài đặt hoặc TESSERACT_CMD."}


def resource_plan() -> dict:
    cpus = os.cpu_count() or 1
    # Account for container CPU quotas and affinity as well as desktop CPUs.
    try:
        cpus = min(cpus, len(psutil.Process().cpu_affinity()))
    except (AttributeError, psutil.Error):
        pass
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            cpus = min(cpus, max(1, math.floor(int(quota) / int(period))))
    except (OSError, ValueError):
        pass
    available = psutil.virtual_memory().available
    try:
        limit = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        used = int(Path("/sys/fs/cgroup/memory.current").read_text())
        if limit != "max":
            available = min(available, max(0, int(limit) - used))
    except (OSError, ValueError):
        pass
    reserve = 1024 ** 3
    per_document = 768 * 1024 ** 2
    workers = max(1, min(8, cpus - 1 if cpus > 1 else 1,
                         max(1, (available - reserve) // per_document)))
    return {"workers": int(workers), "cpu": cpus, "available_gb": round(available / 1024 ** 3, 1),
            "ocr_threads": 1, "dpi": 300}


def fetch_document(url: str, folder: Path) -> Path:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Link phải là HTTP/HTTPS, không chứa thông tin đăng nhập.")
    request = Request(url, headers={"User-Agent": "LocalScanOCR/1.0"})
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        if content_type in {"text/html", "application/xhtml+xml"}:
            raise ValueError("Link trả về trang web. Hãy dùng link tải PDF/ảnh trực tiếp hoặc chọn file từ máy.")
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD:
            raise ValueError("Tệp vượt giới hạn tải 1 GB.")
        disposition = Message()
        disposition["content-disposition"] = response.headers.get("Content-Disposition", "")
        name = disposition.get_filename() or unquote(Path(parsed.path).name) or "tai-lieu.pdf"
        incoming = folder / "input"
        incoming.mkdir(exist_ok=True)
        target = incoming / safe_filename(name)
        temporary = incoming / "download.part"
        total = 0
        try:
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise ValueError("Tệp vượt giới hạn tải 1 GB.")
                    output.write(chunk)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


class JobManager:
    def __init__(self, store: Path = STORE):
        self.store = store
        self.store.mkdir(parents=True, exist_ok=True)
        self.plan = resource_plan()
        self.pool = ThreadPoolExecutor(max_workers=self.plan["workers"], thread_name_prefix="ocr")
        self.lock = threading.Lock()
        self.active: dict[str, object] = {}

    def refresh_plan(self) -> None:
        # Re-evaluate after uploads, before scheduling a new batch.
        with self.lock:
            if any(not future.done() for future in self.active.values()):
                return
            plan = resource_plan()
            if plan["workers"] != self.plan["workers"]:
                self.pool.shutdown(wait=False)
                self.pool = ThreadPoolExecutor(max_workers=plan["workers"], thread_name_prefix="ocr")
            self.plan = plan

    @staticmethod
    def worker_alive(folder: Path, status: dict) -> bool:
        pid = status.get("worker_pid")
        if not pid:
            return False
        try:
            command = psutil.Process(pid).cmdline()
            return "scan_tool.worker" in command and str(folder) in command
        except psutil.Error:
            return False

    def create(self, name: str, source: str, *, path: str | None = None, url: str | None = None,
               searchable: bool = False) -> str:
        job_id = uuid.uuid4().hex
        folder = self.store / job_id
        folder.mkdir()
        atomic_json(folder / "job.json", {"id": job_id, "name": name, "source": source,
                    "input_path": path, "url": url, "searchable": searchable, "created": time.time()})
        self.start(job_id)
        return job_id

    def start(self, job_id: str) -> None:
        folder = self.store / job_id
        with self.lock:
            if self.worker_alive(folder, load_json(folder / "status.json")):
                return
            previous = self.active.get(job_id)
            if previous is not None and not previous.done():
                return
            (folder / "cancel").unlink(missing_ok=True)
            atomic_json(folder / "status.json", {"state": "queued", "page": 0, "total": 0,
                                                  "message": "Đang chờ lượt"})
            self.active[job_id] = self.pool.submit(self._run, folder)

    def _run(self, folder: Path) -> None:
        if (folder / "cancel").exists():
            atomic_json(folder / "status.json", {"state": "cancelled", "message": "Đã dừng"})
            return
        task_env = engine_environment()
        with (folder / "worker.log").open("ab") as log:
            result = subprocess.run([sys.executable, "-m", "scan_tool.worker", str(folder)],
                                    cwd=ROOT, env=task_env, stdout=log, stderr=log,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        status = load_json(folder / "status.json")
        if result.returncode and status.get("state") not in {"failed", "cancelled"}:
            atomic_json(folder / "status.json", {**status, "state": "failed",
                                                  "message": "Tiến trình OCR bị dừng. Có thể thử tiếp tục."})

    def cancel(self, job_id: str) -> None:
        folder = self.store / job_id
        (folder / "cancel").touch()
        with self.lock:
            future = self.active.get(job_id)
            if future is not None and future.cancel():
                atomic_json(folder / "status.json", {"state": "cancelled", "message": "Đã bỏ khỏi hàng đợi"})

    def jobs(self) -> list[dict]:
        result = []
        for folder in self.store.iterdir():
            if not folder.is_dir() or not (folder / "job.json").exists():
                continue
            job = load_json(folder / "job.json")
            status = load_json(folder / "status.json")
            with self.lock:
                future = self.active.get(folder.name)
                alive = (future is not None and not future.done()) or self.worker_alive(folder, status)
            if status.get("state") in {"running", "queued", "downloading"} and not alive:
                status = {**status, "state": "interrupted", "message": "Lượt trước bị ngắt; có thể tiếp tục."}
            result.append({**job, **status, "folder": str(folder)})
        return sorted(result, key=lambda job: job.get("created", 0), reverse=True)
