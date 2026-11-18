"""Optional AI enrichment: gate on consent -> call provider -> ground -> merge -> re-validate."""

from __future__ import annotations

from app.config import AiSettings
from app.extraction.parser import CENT, FieldValue, LineItem
from app.extraction.pipeline import ExtractionResult
from app.extraction.validation import REQUIRED, validate

from .base import AIError, AIProvider
from .consent import CloudConsent, check_consent
from .grounding import Grounder, parse_json_object
from .prompt import FIELDS_DATE, FIELDS_MONEY, FIELDS_TEXT, SYSTEM, build_user

AI_CONFIDENCE = 0.65
KEEP_THRESHOLD = 0.7  # rule-based values at/above this are never overwritten by AI


def needs_ai(res: ExtractionResult) -> bool:
    if res.parsed is None:
        return False
    missing = any(res.parsed.get(f) in (None, "") for f in REQUIRED)
    problems = any(i["severity"] in ("warning", "error") for i in res.issues)
    return missing or problems


def _ai_items(raw, g: Grounder, rejected: list) -> list[LineItem]:
    out: list[LineItem] = []
    if not isinstance(raw, list):
        return out
    for it in raw:
        if not isinstance(it, dict):
            continue
        desc = g.text_(it.get("description"))
        q = g.money(it.get("quantity")) if it.get("quantity") is not None else None
        u = g.money(it.get("unit_price")) if it.get("unit_price") is not None else None
        raw_total = it.get("line_total") if it.get("line_total") is not None else it.get("amount")
        t = g.money(raw_total) if raw_total is not None else None
        if not desc or q is None or u is None or t is None or abs((q * u).quantize(CENT) - t) > CENT:
            rejected.append(
                {"field": "line_items", "value": str(it.get("description"))[:60], "reason": "not grounded or arithmetic mismatch"}
            )
            continue
        out.append(LineItem(desc, quantity=q, unit_price=u, line_total=t, reliable=True, note="from AI, verified arithmetically"))
    return out


def ai_enrich(
    res: ExtractionResult,
    provider: AIProvider | None,
    job_id: str,
    consent: CloudConsent | None = None,
    settings: AiSettings | None = None,
    force: bool = False,
) -> ExtractionResult:
    """Never raises for provider problems (AI is optional); ConsentRequired DOES raise so callers can't bypass it."""
    settings = settings or AiSettings()
    if provider is None or res.parsed is None:
        return res
    check_consent(provider, job_id, consent)  # before any text leaves this process
    if not (force or needs_ai(res)):
        res.ai = {"provider": provider.name, "called": False, "filled": [], "rejected": []}
        return res
    text = "\n\n".join(res.text_pages)[: settings.max_chars]
    hints = {k: v.value for k, v in res.parsed.fields.items() if v.confidence >= KEEP_THRESHOLD and v.value is not None}
    audit = {"provider": provider.name, "cloud": provider.is_cloud, "called": True, "filled": [], "replaced": [], "rejected": []}
    try:
        data = parse_json_object(provider.complete_json(SYSTEM, build_user(text, hints)))
    except (AIError, ValueError) as e:
        audit["error"] = str(e)[:200]
        res.ai = audit
        res.issues.append({"code": "ai_failed", "severity": "info", "message": f"AI step skipped: {str(e)[:120]}", "field": None})
        return res
    p, g = res.parsed, Grounder("\n".join(res.text_pages), res.parsed.decimal_sep, res.parsed.dayfirst)
    checks = {
        **{f: g.text_ for f in FIELDS_TEXT if f != "currency"},
        "currency": g.currency,
        **{f: g.date_ for f in FIELDS_DATE},
        **{f: g.money for f in FIELDS_MONEY},
    }
    for f, check in checks.items():
        raw = data.get(f)
        if raw is None or raw == "":
            continue
        val = check(raw)
        if val is None:
            audit["rejected"].append({"field": f, "value": str(raw)[:60], "reason": "not found in document text"})
            continue
        cur = p.fields.get(f)
        new = FieldValue(val, f"AI ({provider.name})", AI_CONFIDENCE, None, f"ai:{provider.name}")
        if cur is None or cur.value in (None, ""):
            p.fields[f] = new
            audit["filled"].append(f)
        elif cur.value == val:
            cur.confidence = max(cur.confidence, 0.9)  # independent agreement raises confidence
        elif cur.confidence < KEEP_THRESHOLD:
            new.alternatives = [cur.value]
            p.fields[f] = new
            audit["replaced"].append(f)
        else:
            res.issues.append(
                {
                    "code": "ai_disagreement",
                    "severity": "warning",
                    "field": f,
                    "message": f"AI suggests {val} but rules found {cur.value}; rule value kept",
                }
            )
    if not p.line_items or any(not i.reliable for i in p.line_items):
        items = _ai_items(data.get("line_items"), g, audit["rejected"])
        if items:
            p.line_items = items
            audit["filled"].append("line_items")
    for r in audit["rejected"]:
        res.issues.append(
            {
                "code": "ai_rejected",
                "severity": "info",
                "field": r["field"],
                "message": f"AI value for {r['field']} rejected: {r['reason']}",
            }
        )
    keep = [i for i in res.issues if i["code"] in ("ocr_used", "ocr_partial", "ai_disagreement", "ai_rejected", "ai_failed")]
    res.issues = validate(p) + keep
    if audit["filled"] or audit["replaced"]:
        res.method += "+ai"
        res.issues.append(
            {
                "code": "ai_used",
                "severity": "info",
                "field": None,
                "message": f"AI ({provider.name}) supplied: {', '.join(audit['filled'] + audit['replaced'])}; verify",
            }
        )
    elif "error" not in audit:
        res.issues.append(
            {
                "code": "ai_checked",
                "severity": "info",
                "field": None,
                "message": f"AI ({provider.name}) checked this document; no fields changed",
            }
        )
    res.ai = audit
    res.status = "needs_review" if any(i["severity"] in ("warning", "error") for i in res.issues) else "processed"
    return res
