"""Per-job file storage. Client-supplied names are display-only; files live under random ids."""

from __future__ import annotations

import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

CHUNK = 1 << 20


class StorageError(Exception):
    def __init__(self, code: str, msg: str = ""):
        super().__init__(msg or code)
        self.code = code


def safe_display_name(name: str | None) -> str:
    """Basename only, control chars removed, length-limited. Never used as a filesystem path."""
    n = (name or "file").replace("\\", "/").split("/")[-1]
    n = re.sub(r"[\x00-\x1f\x7f]", "", n).strip() or "file"
    return n[:200]


class Storage:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir).resolve() / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise StorageError("bad_job_id")
        d = (self.root / job_id).resolve()
        if self.root not in d.parents:
            raise StorageError("bad_job_id")
        (d / "docs").mkdir(parents=True, exist_ok=True)
        (d / "exports").mkdir(parents=True, exist_ok=True)
        return d

    def doc_path(self, job_id: str, stored_name: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}\.pdf", stored_name):
            raise StorageError("bad_stored_name")
        return self.job_dir(job_id) / "docs" / stored_name

    def export_path(self, job_id: str, stored_name: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}\.(xlsx|csv|pdf)", stored_name):
            raise StorageError("bad_stored_name")
        return self.job_dir(job_id) / "exports" / stored_name

    def save_stream(self, job_id: str, stream: BinaryIO, max_bytes: int) -> tuple[str, int]:
        """Write a stream to a new random file; enforce size cap. Returns (stored_name, size)."""
        name = uuid.uuid4().hex + ".pdf"
        path = self.doc_path(job_id, name)
        size = 0
        try:
            with open(path, "wb") as out:
                while chunk := stream.read(CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise StorageError("file_too_large")
                    out.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return name, size

    def delete_job(self, job_id: str) -> None:
        d = self.root / job_id
        if re.fullmatch(r"[0-9a-f]{32}", job_id) and d.exists():
            shutil.rmtree(d)


def iter_zip_pdfs(stream: BinaryIO, max_files: int, max_total_bytes: int, max_file_bytes: int):
    """Yield (display_name, file_object) for each .pdf in a ZIP, safely.

    Entry names are NEVER used as paths (so '../x', absolute paths and symlinks cannot escape): they only
    become display names. Limits on entry count and declared/actual uncompressed size defend against zip bombs.
    """
    try:
        zf = zipfile.ZipFile(stream)
    except zipfile.BadZipFile as e:
        raise StorageError("bad_zip") from e
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > max_files:
        raise StorageError("zip_too_many_files")
    if sum(i.file_size for i in infos) > max_total_bytes:
        raise StorageError("zip_too_large")
    for info in infos:
        if info.flag_bits & 0x1:
            yield safe_display_name(info.filename), None, "encrypted_zip_entry"
            continue
        if not info.filename.lower().endswith(".pdf"):
            continue
        if info.file_size > max_file_bytes:
            yield safe_display_name(info.filename), None, "file_too_large"
            continue
        yield safe_display_name(info.filename), zf.open(info), None
