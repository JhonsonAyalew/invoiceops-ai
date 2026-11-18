"""Operator-editable, NON-secret settings stored in the DB (API keys stay in the environment)."""

from __future__ import annotations

import dataclasses

from sqlalchemy.orm import Session

from app.config import AiSettings, OcrSettings
from app.extraction.ocr import SUPPORTED_LANGS
from app.models import AppSetting

AI_PROVIDERS = {"none", "ollama", "groq"}


def _get(s: Session, key: str) -> dict:
    row = s.get(AppSetting, key)
    return dict(row.value) if row else {}


def _put(s: Session, key: str, value: dict) -> None:
    row = s.get(AppSetting, key)
    if row:
        row.value = value
    else:
        s.add(AppSetting(key=key, value=value))
    s.commit()


def load_ocr(s: Session) -> OcrSettings:
    o = _get(s, "ocr")
    base = OcrSettings.from_env()
    kw = {k: v for k, v in o.items() if v not in (None, "") and k in {f.name for f in dataclasses.fields(OcrSettings)}}
    if "languages" in kw:
        kw["languages"] = tuple(kw["languages"])
    return dataclasses.replace(base, **kw)


def load_ai(s: Session) -> AiSettings:
    a = _get(s, "ai")
    base = AiSettings.from_env()
    # API keys are deliberately excluded: they stay in the environment, never in the DB.
    allowed = {"provider", "ollama_url", "ollama_model", "groq_base_url", "groq_model"}
    return dataclasses.replace(base, **{k: v for k, v in a.items() if k in allowed and v})


def save_ocr(s: Session, data: dict) -> None:
    out = {}
    if "languages" in data:
        langs = [l for l in data["languages"]]
        if not langs or any(l not in SUPPORTED_LANGS for l in langs):
            raise ValueError(f"languages must be a non-empty subset of {sorted(SUPPORTED_LANGS)}")
        out["languages"] = langs
    for k in ("model_dir", "poppler_path"):
        if k in data:
            out[k] = (data[k] or "").strip() or None
    if "device" in data:
        device = (data["device"] or "").strip().lower()
        if device not in {"cpu", "gpu"}:
            raise ValueError("device must be cpu or gpu")
        out["device"] = device
    for k, lo, hi in (("timeout_seconds", 5, 1800), ("dpi", 100, 600)):
        if k in data:
            if not isinstance(data[k], int) or not lo <= data[k] <= hi:
                raise ValueError(f"{k} must be an integer between {lo} and {hi}")
            out[k] = data[k]
    _put(s, "ocr", {**_get(s, "ocr"), **out})


def save_ai(s: Session, data: dict) -> None:
    out = {}
    if "provider" in data:
        if data["provider"] not in AI_PROVIDERS:
            raise ValueError(f"provider must be one of {sorted(AI_PROVIDERS)}")
        out["provider"] = data["provider"]
    for k in ("ollama_url", "ollama_model", "groq_base_url", "groq_model"):
        if k in data:
            v = (data[k] or "").strip()
            if k == "ollama_url" and v and not v.startswith(("http://", "https://")):
                raise ValueError("ollama_url must start with http:// or https://")
            if k == "groq_base_url" and v and not v.startswith("https://"):
                raise ValueError("groq_base_url must start with https://")
            out[k] = v or None
    _put(s, "ai", {**_get(s, "ai"), **out})
