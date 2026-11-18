"""File-level (SHA-256) and invoice-level duplicate detection."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def find_duplicates(records: list[dict], threshold: float = 0.88) -> list[dict]:
    """records: dicts with id, sha256, supplier_name, invoice_number, total_amount, invoice_date.
    Returns [{a, b, kind, score}]. Exact hash => 'file'; same supplier+number(+total) => 'invoice';
    otherwise similar supplier+number+total/date => 'similar'."""
    out, _seen = [], set()
    for i, a in enumerate(records):
        for b in records[i + 1 :]:
            (a["id"], b["id"])
            if a.get("sha256") and a.get("sha256") == b.get("sha256"):
                out.append({"a": a["id"], "b": b["id"], "kind": "file", "score": 1.0})
                continue
            sn_a, sn_b = _norm(a.get("supplier_name")), _norm(b.get("supplier_name"))
            in_a, in_b = _norm(a.get("invoice_number")), _norm(b.get("invoice_number"))
            if not in_a or not in_b:
                continue
            sup = SequenceMatcher(None, sn_a, sn_b).ratio() if sn_a and sn_b else 0.0
            num = SequenceMatcher(None, in_a, in_b).ratio()
            same_total = a.get("total_amount") is not None and a.get("total_amount") == b.get("total_amount")
            if in_a == in_b and (sup >= 0.8 or not sn_a or not sn_b):
                out.append({"a": a["id"], "b": b["id"], "kind": "invoice", "score": round(max(sup, 0.9), 3)})
            elif num >= threshold and sup >= threshold and same_total:
                out.append({"a": a["id"], "b": b["id"], "kind": "similar", "score": round((num + sup) / 2, 3)})
    return out
