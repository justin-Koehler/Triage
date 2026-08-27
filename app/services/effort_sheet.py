"""Aufwand aus einer geteilten Google-Sheets-Tabelle lesen."""

from __future__ import annotations

import csv
import io
import re
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import ROOT
from app.domain.calc import parse_number
from app.models import AppSetting

TEMPLATE_PATH = ROOT / "config" / "effort_sheet_template.csv"
DUMMY_TEMPLATE_URL = (
    "https://docs.google.com/spreadsheets/d/dummyCRITRaufwandTemplate/edit"
)
DUMMY_OPEN_URL = "https://docs.google.com/spreadsheets/create"
_SHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_ALLOWED_HOSTS = {"docs.google.com"}
_NOT_SHARED = "Sheet nicht freigegeben. Unter Freigabe: Jeder mit dem Link (Lesen)."
_SHARE_PREFIX = "effort.share."
_DUMMY_MARK = "dummycritraufwand"


class EffortSheetError(ValueError):
    """URL ungültig oder Sheet nicht lesbar."""


def extract_sheet_id(url: str) -> str | None:
    match = _SHEET_ID.search(url or "")
    return match.group(1) if match else None


def is_dummy_template_url(url: str) -> bool:
    return _DUMMY_MARK in (url or "").lower()


def dummy_open_url(template_url: str) -> str:
    if is_dummy_template_url(template_url) or not extract_sheet_id(template_url):
        return DUMMY_OPEN_URL
    return (template_url or "").strip()


def copy_url(template_url: str) -> str:
    if is_dummy_template_url(template_url):
        return DUMMY_OPEN_URL
    sheet_id = extract_sheet_id(template_url)
    if not sheet_id:
        return ""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/copy"


def parse_dummy_template(url: str = "") -> dict[str, str]:
    parsed = parse_effort_csv(TEMPLATE_PATH.read_text(encoding="utf-8"))
    parsed["effort_sheet_url"] = (url or DUMMY_TEMPLATE_URL).strip()
    return parsed


def export_csv_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise EffortSheetError("Nur Google-Sheets-Links (docs.google.com) sind erlaubt.")
    sheet_id = extract_sheet_id(url)
    if not sheet_id:
        raise EffortSheetError("Keine Spreadsheet-ID in der URL.")
    gid = "0"
    query = parse_qs(parsed.query)
    if query.get("gid"):
        gid = query["gid"][0]
    elif parsed.fragment.startswith("gid="):
        gid = parsed.fragment.split("=", 1)[-1]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _norm(header: str) -> str:
    return (
        str(header or "")
        .strip()
        .lower()
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ß", "ss")
    )


def _phase(raw: str) -> str:
    text = _norm(raw)
    if "betrieb" in text or text in {"operate", "ops"}:
        return "operate"
    return "concept"


def _party(raw: str) -> str:
    text = _norm(raw)
    if any(token in text for token in ("cit", "it", "sit")):
        return "cit"
    return "scs"


def parse_effort_csv(text: str) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO(text or ""))
    if not reader.fieldnames:
        raise EffortSheetError("Tabelle ohne Kopfzeile.")
    index = {_norm(name): name for name in reader.fieldnames if name}
    phase_col = next((index[k] for k in index if k in {"phase", "abschnitt"}), None)
    party_col = next((index[k] for k in index if k in {"bereich", "partei", "team"}), None)
    pt_col = next((index[k] for k in index if k in {"pt", "personentage", "tage"}), None)
    cost_col = next(
        (index[k] for k in index if k in {"sachkosten", "kosten", "euro", "eur"}),
        None,
    )
    if not pt_col:
        raise EffortSheetError("Spalte PT fehlt.")
    totals = {
        "concept_scs": 0.0,
        "concept_cit": 0.0,
        "operate_scs": 0.0,
        "operate_cit": 0.0,
        "costs": 0.0,
    }
    for row in reader:
        if not any(str(value or "").strip() for value in row.values()):
            continue
        phase = _phase(row.get(phase_col) if phase_col else "")
        party = _party(row.get(party_col) if party_col else "")
        pt = parse_number(row.get(pt_col))
        totals[f"{phase}_{party}"] += pt
        if cost_col:
            totals["costs"] += parse_number(row.get(cost_col))
    concept_scs = totals["concept_scs"]
    concept_cit = totals["concept_cit"]
    operate_scs = totals["operate_scs"]
    operate_cit = totals["operate_cit"]
    costs = totals["costs"]
    return {
        "effort_fb": _format_pt(concept_scs),
        "effort_it": _format_pt(concept_cit),
        "concept_scs_pt": _qty(concept_scs),
        "concept_cit_pt": _qty(concept_cit),
        "operate_scs_pt": _qty(operate_scs),
        "operate_cit_pt": _qty(operate_cit),
        "costs": _qty(costs) if costs else "",
    }


def _format_pt(value: float) -> str:
    if value <= 0:
        return "0 PT"
    if value == int(value):
        return f"{int(value)} PT"
    return f"{value:.1f}".replace(".", ",") + " PT"


def _qty(value: float) -> str:
    if value <= 0:
        return ""
    if value == int(value):
        return str(int(value))
    return str(value).replace(".", ",")


def fetch_effort_sheet(url: str, *, timeout: int = 15) -> dict[str, str]:
    if is_dummy_template_url(url):
        return parse_dummy_template(url)
    export = export_csv_url(url)
    try:
        response = httpx.get(
            export,
            timeout=timeout,
            follow_redirects=True,
            trust_env=False,
            headers={"accept": "text/csv,text/plain,*/*"},
        )
    except httpx.HTTPError as err:
        raise EffortSheetError("Sheet nicht erreichbar.") from err
    host = (urlparse(str(response.url)).hostname or "").lower()
    if host not in _ALLOWED_HOSTS and "googleusercontent.com" not in host:
        raise EffortSheetError(_NOT_SHARED)
    if response.status_code >= 400:
        raise EffortSheetError(_NOT_SHARED)
    ctype = (response.headers.get("content-type") or "").lower()
    body = response.text or ""
    if "html" in ctype or body.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        raise EffortSheetError(_NOT_SHARED)
    parsed = parse_effort_csv(body)
    parsed["effort_sheet_url"] = (url or "").strip()
    return parsed


def commit_effort_csv(db: Session, csv_text: str, public_base: str) -> dict[str, str]:
    parsed = parse_effort_csv(csv_text)
    share_id = str(uuid.uuid4())
    key = f"{_SHARE_PREFIX}{share_id}"
    row = db.get(AppSetting, key)
    if row:
        row.value = csv_text
        row.secret = False
    else:
        db.add(AppSetting(key=key, value=csv_text, secret=False))
    db.flush()
    parsed["effort_sheet_url"] = f"{public_base.rstrip('/')}/aufwand/{share_id}"
    parsed["share_id"] = share_id
    return parsed


def load_share_csv(db: Session, share_id: str) -> str | None:
    try:
        uuid.UUID(share_id)
    except ValueError:
        return None
    row = db.get(AppSetting, f"{_SHARE_PREFIX}{share_id}")
    return row.value if row and row.value else None


def share_html(csv_text: str) -> str:
    reader = csv.reader(io.StringIO(csv_text or ""))
    rows = list(reader)
    if not rows:
        body = "<p>Leere Tabelle.</p>"
    else:
        head, *rest = rows
        th = "".join(f"<th>{_esc(cell)}</th>" for cell in head)
        tb = "".join(
            "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>"
            for row in rest
        )
        body = f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"
    return (
        "<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>Aufwand</title>"
        "<link rel='stylesheet' href='/styles.css?v=effort-sheet-popup-v1'/>"
        "</head><body class='effort-sheet-share'><main>"
        "<h1>Aufwandstabelle</h1>"
        f"{body}</main></body></html>"
    )


def _esc(value: object) -> str:
    from html import escape

    return escape(str(value or ""))


def template_bytes() -> bytes:
    path = Path(TEMPLATE_PATH)
    return path.read_bytes()
