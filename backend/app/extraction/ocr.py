"""PaddleOCR PP-OCRv6 Medium detection and Poppler-based PDF rendering."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path

from app.config import OcrSettings

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("GLOG_minloglevel", "3")

MODEL = "PP-OCRv6 Medium"
DET_MODEL = "PP-OCRv6_medium_det"
REC_MODEL = "PP-OCRv6_medium_rec"
SUPPORTED_LANGS = {"eng": "English", "deu": "German", "fra": "French", "spa": "Spanish"}
WINDOWS_POPPLER_GLOBS = [r"C:\poppler\Library\bin", r"C:\poppler\bin", r"C:\Program Files\poppler\Library\bin"]

_engine = None
_engine_key = None
_engine_lock = threading.Lock()
_predict_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="paddleocr")


class OcrError(Exception):
    pass


class OcrUnavailable(OcrError):
    pass


class OcrTimeout(OcrError):
    pass


@dataclass
class OcrStatus:
    package_found: bool
    version: str | None = None
    model: str = MODEL
    det_model_found: bool = False
    rec_model_found: bool = False
    model_dir: str | None = None
    device: str = "cpu"
    languages: list[str] = field(default_factory=list)
    poppler_found: bool = False
    poppler_path: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.package_found and self.det_model_found and self.rec_model_found and self.poppler_found


def default_model_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "InvoiceOps" / "paddle_models"
    return Path.home() / ".local" / "share" / "InvoiceOps" / "paddle_models"


def model_paths(settings: OcrSettings) -> tuple[Path | None, Path | None, str | None]:
    root = Path(settings.model_dir).expanduser() if settings.model_dir else default_model_dir()
    det, rec = root / DET_MODEL, root / REC_MODEL
    found = det.is_dir() and rec.is_dir()
    return (det, rec, str(root)) if found else (None, None, str(root))


def find_poppler(settings: OcrSettings) -> str | None:
    exe = "pdftoppm.exe" if os.name == "nt" else "pdftoppm"
    if settings.poppler_path and (Path(settings.poppler_path) / exe).is_file():
        return settings.poppler_path
    if shutil.which("pdftoppm"):
        return ""
    for d in WINDOWS_POPPLER_GLOBS:
        if (Path(d) / "pdftoppm.exe").is_file():
            return d
    return None


def check_ocr(settings: OcrSettings) -> OcrStatus:
    package_found = importlib.util.find_spec("paddleocr") is not None
    try:
        version = importlib.metadata.version("paddleocr")
    except importlib.metadata.PackageNotFoundError:
        version = None
    det, rec, root = model_paths(settings)
    pp = find_poppler(settings)
    st = OcrStatus(
        package_found=package_found,
        version=version,
        det_model_found=det is not None,
        rec_model_found=rec is not None,
        model_dir=root,
        device=settings.device,
        languages=list(settings.languages),
        poppler_found=pp is not None,
        poppler_path=pp,
    )
    if not package_found:
        st.problems.append("paddleocr is not installed. Run scripts\\setup.bat or pip install -r requirements.txt.")
    if det is None or rec is None:
        missing = [n for n, ok in ((DET_MODEL, det is not None), (REC_MODEL, rec is not None)) if not ok]
        st.problems.append(f"PP-OCRv6 Medium model folder(s) missing in {root}: {', '.join(missing)}. Run scripts\\download_models.bat.")
    if pp is None:
        st.problems.append("Poppler not found (needed to render PDF pages). Set POPPLER_PATH or install Poppler.")
    return st


def _get_engine(settings: OcrSettings):
    global _engine, _engine_key
    det, rec, _ = model_paths(settings)
    key = (str(det), str(rec), settings.device)
    with _engine_lock:
        if _engine is None or _engine_key != key:
            from paddleocr import PaddleOCR

            params = {
                "text_detection_model_name": DET_MODEL,
                "text_recognition_model_name": REC_MODEL,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "device": settings.device,
                "enable_mkldnn": False,
            }
            if det and rec:
                params["text_detection_model_dir"] = str(det)
                params["text_recognition_model_dir"] = str(rec)
            _engine = PaddleOCR(**params)
            _engine_key = key
        return _engine


def _predict(engine, image) -> str:
    with _predict_lock:
        results = list(engine.predict(image))
    lines: list[str] = []
    for result in results:
        data = getattr(result, "json", {}).get("res", {})
        lines.extend(str(t) for t in data.get("rec_texts", []))
    return "\n".join(lines)


def ocr_pdf_pages(path: str | Path, settings: OcrSettings, pages: list[int] | None = None) -> dict[int, str]:
    status = check_ocr(settings)
    if not status.package_found:
        raise OcrUnavailable("paddleocr is not installed")
    if not status.poppler_found:
        raise OcrUnavailable("Poppler not found")
    if not status.det_model_found or not status.rec_model_found:
        raise OcrUnavailable(f"PP-OCRv6 Medium models not found in {status.model_dir}")

    import numpy as np
    from pdf2image import convert_from_path

    kwargs = {"dpi": settings.dpi}
    if status.poppler_path:
        kwargs["poppler_path"] = status.poppler_path
    try:
        engine = _get_engine(settings)
        out: dict[int, str] = {}
        targets = pages
        if targets is None:
            count = len(convert_from_path(str(path), **kwargs))
            targets = list(range(1, count + 1))
        for n in targets:
            img = convert_from_path(str(path), first_page=n, last_page=n, **kwargs)[0]
            image = np.array(img.convert("RGB"))
            try:
                out[n] = _executor.submit(_predict, engine, image).result(timeout=settings.timeout_seconds)
            except FutureTimeout as e:
                raise OcrTimeout(f"OCR timed out on page {n} after {settings.timeout_seconds}s") from e
        return out
    except ImportError as e:
        raise OcrUnavailable(f"PaddleOCR dependency missing: {e}") from e
