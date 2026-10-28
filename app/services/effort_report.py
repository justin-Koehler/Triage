"""Live-Auswertung der IT-Personentage aus den gespeicherten Aufwand-Feldern."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.calc import parse_number
from app.domain.types import STATUS_LABELS, RequestStatus
from app.models import Request, User
from app.services.stand_summary import stand_health

UNASSIGNED = "Ohne Zuordnung"


def _owner(request: Request) -> str:
    values = request.field_values()
    for key in ("responsible_sit", "it_owner"):
        name = str(values.get(key) or "").strip()
        if name:
            return name
    lead = str(request.change_lead or "").strip()
    return lead or UNASSIGNED


def _points(request: Request) -> tuple[float, float]:
    values = request.field_values()
    concept = parse_number(values.get("concept_cit_pt"))
    operate = parse_number(values.get("operate_cit_pt"))
    if concept == 0 and operate == 0:
        concept = parse_number(values.get("effort_it"))
    return concept, operate


def _bucket(request: Request) -> str:
    if stand_health(request).get("key") == "white":
        return "hold"
    status = str(request.status or "")
    if status == RequestStatus.DONE.value:
        return "done"
    if status == RequestStatus.REJECTED.value:
        return "rejected"
    if status == RequestStatus.APPROVED.value:
        return "approved"
    return "open"


def _status_label(request: Request, bucket: str) -> str:
    if bucket == "hold":
        return "On hold"
    try:
        return STATUS_LABELS[RequestStatus(request.status)]
    except (ValueError, KeyError):
        return str(request.status or "")


def _round(value: float) -> float:
    return round(value + 1e-9, 1)


def _jira_key(request: Request) -> str:
    for ref in getattr(request, "external_refs", None) or []:
        key = str(ref.external_key or "").strip()
        if key:
            return key
    return ""


def _bucket_name(status: str) -> str:
    low = (status or "").strip().lower()
    if any(token in low for token in ("on hold", "onhold", "hold", "paus")):
        return "hold"
    if any(token in low for token in ("ablehn", "reject", "cancel", "abbruch")):
        return "rejected"
    if any(token in low for token in ("done", "abgeschlossen", "geschlossen", "closed", "fertig")):
        return "done"
    if any(token in low for token in ("freigegeben", "approved", "final")):
        return "approved"
    return "open"


def _jira_owner(issue: dict) -> str:
    values = issue.get("values") or {}
    for raw in (
        values.get("responsible_sit"),
        values.get("it_owner"),
        issue.get("assignee"),
    ):
        name = str(raw or "").strip()
        if name:
            return name
    return ""


def _jira_concept(issue: dict) -> float:
    values = issue.get("values") or {}
    concept = parse_number(values.get("concept_cit_pt"))
    if concept:
        return concept
    return parse_number(values.get("effort_it"))


def _line(request: Request) -> dict:
    concept, operate = _points(request)
    bucket = _bucket(request)
    return {
        "id": request.id,
        "key": _jira_key(request),
        "title": str(request.title or request.reference or "Change").strip(),
        "owner": _owner(request),
        "statusLabel": _status_label(request, bucket),
        "bucket": bucket,
        "concept": concept,
        "operate": operate,
    }


def merge_lines(requests: list[Request], issues: list[dict] | None) -> list[dict]:
    """Sheet-Felder bleiben, Jira füllt Status, Verantwortliche und fehlende PT."""
    by_key: dict[str, dict] = {}
    loose: list[dict] = []
    for request in requests:
        line = _line(request)
        if line["key"]:
            by_key[line["key"]] = line
        else:
            loose.append(line)

    lines: list[dict] = []
    seen: set[str] = set()
    for issue in issues or []:
        key = str(issue.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        local = by_key.pop(key, None)
        jira_concept = _jira_concept(issue)
        jira_owner = _jira_owner(issue)
        status = str(issue.get("status") or "").strip()
        if local:
            concept = local["concept"] or jira_concept
            operate = local["operate"]
            owner = local["owner"] if local["owner"] != UNASSIGNED else (jira_owner or UNASSIGNED)
            status_label = status or local["statusLabel"]
            bucket = _bucket_name(status) if status else local["bucket"]
            title = str(issue.get("title") or local["title"]).strip()
            request_id = local["id"]
        else:
            concept = jira_concept
            operate = 0.0
            owner = jira_owner or UNASSIGNED
            status_label = status or "Offen"
            bucket = _bucket_name(status_label)
            title = str(issue.get("title") or key).strip()
            request_id = ""
        if concept + operate <= 0:
            continue
        lines.append(
            {
                "id": request_id,
                "title": title,
                "owner": owner,
                "statusLabel": status_label,
                "bucket": bucket,
                "concept": concept,
                "operate": operate,
            }
        )

    for line in list(by_key.values()) + loose:
        if line["concept"] + line["operate"] <= 0:
            continue
        lines.append(line)
    return lines


def _aggregate(lines: list[dict]) -> dict:
    owners: dict[str, dict] = {}
    changes: list[dict] = []
    for line in lines:
        concept_r = _round(line["concept"])
        operate_r = _round(line["operate"])
        total_r = _round(concept_r + operate_r)
        if total_r <= 0:
            continue
        name = line["owner"] or UNASSIGNED
        bucket = line["bucket"]
        row = owners.setdefault(
            name,
            {
                "name": name,
                "projects": 0,
                "conceptPt": 0.0,
                "totalPt": 0.0,
                "approvedPt": 0.0,
                "openPt": 0.0,
                "holdPt": 0.0,
                "donePt": 0.0,
                "rejectedPt": 0.0,
            },
        )
        row["projects"] += 1
        row["conceptPt"] = _round(row["conceptPt"] + concept_r)
        row["totalPt"] = _round(row["totalPt"] + total_r)
        key = {
            "approved": "approvedPt",
            "open": "openPt",
            "hold": "holdPt",
            "done": "donePt",
            "rejected": "rejectedPt",
        }[bucket]
        row[key] = _round(row[key] + total_r)
        changes.append(
            {
                "id": line.get("id") or "",
                "title": line.get("title") or "Change",
                "statusLabel": line.get("statusLabel") or "",
                "owner": name,
                "conceptPt": concept_r,
                "operatePt": operate_r,
                "totalPt": total_r,
            }
        )

    owner_rows = sorted(owners.values(), key=lambda item: (-item["totalPt"], item["name"].lower()))
    changes.sort(key=lambda item: item["title"].lower())
    it_pt = _round(sum(item["totalPt"] for item in owner_rows))
    named = [item for item in owner_rows if item["name"] != UNASSIGNED]
    divisor = len(named) or len(owner_rows)
    return {
        "totals": {
            "itPt": it_pt,
            "projects": sum(item["projects"] for item in owner_rows),
            "owners": len(named),
            "avgPerOwner": _round(it_pt / divisor) if divisor else 0.0,
        },
        "owners": owner_rows,
        "changes": changes,
    }


def build_effort_report(requests: list[Request]) -> dict:
    return _aggregate(merge_lines(requests, None))


def _jira_issues(db: Session, user: User | None) -> list[dict]:
    try:
        from app.api.jira_lookup import _inbox_port, _user_jira_credentials

        token, email = _user_jira_credentials(db, user) if user else (None, None)
        return _inbox_port(db).list_issues(
            limit=400,
            include_closed=True,
            user_token=token,
            user_email=email,
        )
    except Exception:
        return []


def effort_evaluation(db: Session, user: User | None = None) -> dict:
    rows = db.scalars(
        select(Request).options(
            selectinload(Request.fields),
            selectinload(Request.status_updates),
            selectinload(Request.external_refs),
        )
    ).all()
    return _aggregate(merge_lines(list(rows), _jira_issues(db, user)))
