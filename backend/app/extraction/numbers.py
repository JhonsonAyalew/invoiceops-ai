"""Locale-aware, Decimal-only number and date parsing. Never uses float."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

AMOUNT_RE = re.compile(
    r"(?<![\w.,])\(?-?\d{1,3}(?:[ .,'\u00a0\u202f]\d{3})+(?:[.,]\d{1,4})?\)?(?![\d])"
    r"|(?<![\w.,])\(?-?\d+(?:[.,]\d{1,4})?\)?(?![\d])"
)


def parse_amount(text: str, decimal_sep: str | None = None) -> Decimal | None:
    """Parse '1,234.56', '1.234,56', '1 234,56', "1'234.50", '(12.00)', '€12,5'.

    decimal_sep: '.' or ',' when known for the document; resolves single-separator
    ambiguity such as '1.234' (thousands vs decimal).
    """
    if text is None:
        return None
    s = text.strip()
    neg = (s.startswith("(") and s.endswith(")")) or s.startswith("-") or s.endswith("-")
    s = re.sub(r"[^\d.,' \u00a0\u202f]", "", s).strip()
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    if not s or not re.search(r"\d", s):
        return None
    s = s.replace("'", " ")
    if " " in s:
        if not re.fullmatch(r"\d{1,3}( \d{3})+([.,]\d+)?", s):
            return None
        s = s.replace(" ", "")
    dots, commas = s.count("."), s.count(",")
    if dots and commas:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
    elif dots or commas:
        sep = "." if dots else ","
        n = dots or commas
        tail = s.rsplit(sep, 1)[1]
        if n > 1:
            dec = None  # repeated => thousands separators
        elif decimal_sep == sep:
            dec = sep
        elif decimal_sep and decimal_sep != sep:
            dec = None  # document uses the other char as decimal
        else:
            dec = None if len(tail) == 3 else sep
    else:
        dec = None
    if dec:
        thousands = "," if dec == "." else "."
        s = s.replace(thousands, "").replace(dec, ".")
    else:
        s = s.replace(".", "").replace(",", "")
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    return -v if neg else v


def infer_decimal_separator(text: str) -> str | None:
    """Vote on the document's decimal separator using unambiguous amounts."""
    votes = {".": 0, ",": 0}
    for m in re.finditer(r"\d[\d.,]*\d", text):
        tok = m.group(0)
        if "." in tok and "," in tok:
            votes["." if tok.rfind(".") > tok.rfind(",") else ","] += 2
        elif re.search(r"[.,]\d{2}$", tok) and tok.count(tok[-3]) == 1:
            votes[tok[-3]] += 1
    if votes["."] == votes[","]:
        return None
    return "." if votes["."] > votes[","] else ","


_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "okt": 10,
    "dez": 12,
    "dezember": 12,
    "oktober": 10,
    "janv": 1,
    "févr": 2,
    "fevr": 2,
    "mars": 3,
    "avr": 4,
    "juin": 6,
    "juil": 7,
    "août": 8,
    "aout": 8,
    "déc": 12,
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "avril": 4,
    "juillet": 7,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
    "ene": 1,
    "abr": 4,
    "ago": 8,
    "dic": 12,
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "octubre ": 10,
    "noviembre": 11,
    "diciembre": 12,
}

DATE_TOKEN_RE = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
    r"|\b\d{1,2}\.? [A-Za-zäéûô]{3,10}\.?,? \d{4}\b|\b[A-Za-z]{3,10}\.? \d{1,2},? \d{4}\b",
)


def _mk(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str, dayfirst: bool | None = None) -> tuple[date | None, bool]:
    """Return (date, ambiguous). Ambiguous = numeric d/m vs m/d could both be valid."""
    s = text.strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return _mk(int(m[1]), int(m[2]), int(m[3])), False
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        if a > 12 and b <= 12:
            return _mk(y, b, a), False
        if b > 12 and a <= 12:
            return _mk(y, a, b), False
        if a == b:
            return _mk(y, a, b), False
        df = True if dayfirst is None else dayfirst
        return (_mk(y, b, a) if df else _mk(y, a, b)), dayfirst is None
    m = re.fullmatch(r"(\d{1,2})\.? ([A-Za-zäéûô]{3,10})\.?,? (\d{4})", s)
    if m and m[2].lower() in _MONTHS:
        return _mk(int(m[3]), _MONTHS[m[2].lower()], int(m[1])), False
    m = re.fullmatch(r"([A-Za-z]{3,10})\.? (\d{1,2}),? (\d{4})", s)
    if m and m[1].lower() in _MONTHS:
        return _mk(int(m[3]), _MONTHS[m[1].lower()], int(m[2])), False
    return None, False


def fmt_money(v: Decimal) -> str:
    """Canonical text for a Decimal: plain notation, at least 2 decimals, no float, identical on every database."""
    s = format(v.normalize(), "f")
    if "." not in s:
        return s + ".00"
    return s + "0" if len(s.split(".")[1]) == 1 else s
