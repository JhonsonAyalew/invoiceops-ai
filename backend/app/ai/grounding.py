"""Anti-hallucination: an AI value is accepted only if it is literally supported by the document text."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.extraction.numbers import AMOUNT_RE, DATE_TOKEN_RE, parse_amount, parse_date
from app.extraction.parser import CURRENCY_CODES, SYMBOLS


def _norm(s: str) -> str:
    return re.sub(r"[^\w]+", "", s.casefold())


def parse_json_object(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    if not s.startswith("{"):
        i, j = s.find("{"), s.rfind("}")
        if i < 0 or j <= i:
            raise ValueError("no JSON object")
        s = s[i : j + 1]
    # parse_float=Decimal: JSON numbers never pass through binary floats
    d = json.loads(s, parse_float=Decimal)
    if not isinstance(d, dict):
        raise ValueError("not an object")
    return d


class Grounder:
    def __init__(self, text: str, decimal_sep: str | None, dayfirst: bool | None):
        self.text, self.ntext = text, _norm(text)
        self.amounts: set[Decimal] = set()
        for m in AMOUNT_RE.finditer(text):
            v = parse_amount(m.group(0), decimal_sep)
            if v is not None:
                self.amounts.add(v)
                alt = parse_amount(m.group(0), "." if decimal_sep == "," else ",")  # tolerate separator ambiguity
                if alt is not None and "%" not in text[m.end() : m.end() + 2]:
                    self.amounts.add(alt)
        self.dates: set[date] = set()
        for m in DATE_TOKEN_RE.finditer(text):
            for df in {dayfirst, True, False} if dayfirst is None else {dayfirst}:
                d, _ = parse_date(m.group(0), df)
                if d:
                    self.dates.add(d)

    def money(self, v) -> Decimal | None:
        try:
            d = v if isinstance(v, Decimal) else Decimal(str(v).strip())
        except (InvalidOperation, ValueError):
            d = parse_amount(str(v)) if isinstance(v, str) else None
        if d is None or not d.is_finite():
            return None
        return d if d in self.amounts else None

    def date_(self, v) -> date | None:
        try:
            d = date.fromisoformat(str(v).strip())
        except ValueError:
            return None
        return d if d in self.dates else None

    def text_(self, v) -> str | None:
        if not isinstance(v, str) or not v.strip():
            return None
        s = " ".join(v.split())
        return s if len(_norm(s)) >= 2 and _norm(s) in self.ntext else None

    def currency(self, v) -> str | None:
        c = str(v).strip().upper() if v else ""
        if c not in CURRENCY_CODES:
            return None
        if re.search(rf"\b{c}\b", self.text) or any(sym in self.text for sym, code in SYMBOLS.items() if code == c):
            return c
        return None
