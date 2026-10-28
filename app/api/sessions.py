from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.config import ROOT
from app.db import get_db
from app.models import User
from app.schemas import (
    AiFillIn,
    ContextIn,
    DraftPatchIn,
    EffortIn,
    EffortSheetCommitIn,
    EffortSheetIn,
    MessageIn,
    OverrideIn,
    PolishIn,
    ReasonIn,
    RiskIn,
    SolutionIn,
    TicketPublishIn,
)
from app.security import current_actor
from app.services.assistant import AssistantService
from app.services.classify import kind_payload, priority_payload
from app.services.effort import review_effort
from app.services.effort_sheet import (
    EffortSheetError,
    commit_effort_csv,
    dummy_template_bytes,
    effort_sync_fields,
    fetch_effort_sheet,
    kalkulation_xlsx,
    ensure_effort_share,
    load_share_csv,
    template_bytes,
)
from app.services.fields import (
    infer_benefit,
    infer_overview,
    infer_reason,
    infer_risks,
    infer_solution,
)
from app.services.intake import IntakeService, NotReadyForCreation, SessionNotFound
from app.services.polish import polish_description
from app.services.settings_service import get_runtime_config
from app.triage.engine import TriageEngine
from app.triage.providers import LlmUnavailable, build_provider_from_runtime

router = APIRouter(prefix="/api/sessions", tags=["intake"])


def get_service(db: Session = Depends(get_db)) -> IntakeService:
    provider = build_provider_from_runtime(get_runtime_config(db))
    return IntakeService(db=db, engine=TriageEngine(provider=provider))


def get_assistant(
    db: Session = Depends(get_db),
    service: IntakeService = Depends(get_service),
) -> AssistantService:
    provider = build_provider_from_runtime(get_runtime_config(db))
    return AssistantService(db=db, intake=service, provider=provider)


def _load(service: IntakeService, session_id: str, user: User | None = None):
    try:
        session = service.load_session(session_id)
    except SessionNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session unbekannt") from None
    if user is not None and session.user_id and session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session gehört einem anderen Nutzer")
    return session


@router.post("")
def create_session(
    service: IntakeService = Depends(get_service),
    user: User = Depends(current_actor),
) -> dict:
    session = service.create_session(user)
    return {"sessionId": session.id}


@router.get("/hub-chats")
def list_hub_chats(
    assistant: AssistantService = Depends(get_assistant),
    user: User = Depends(current_actor),
    limit: int = Query(8, ge=1, le=20),
) -> dict:
    return {"items": assistant.list_hub_chats(user, limit=limit)}


@router.get("/{session_id}/history")
def get_session_history(
    session_id: str,
    assistant: AssistantService = Depends(get_assistant),
    user: User = Depends(current_actor),
) -> dict:
    session = _load(assistant.intake, session_id, user)
    return assistant.hub_history_payload(session)


@router.post("/{session_id}/message/stream")
def post_message_stream(
    session_id: str,
    payload: MessageIn,
    assistant: AssistantService = Depends(get_assistant),
    user: User = Depends(current_actor),
) -> StreamingResponse:
    session = _load(assistant.intake, session_id, user)
    client = payload.client.model_dump() if payload.client else None

    def events():
        try:
            for event in assistant.handle_stream(
                session, payload.text, client, actor=user
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as err:  # noqa: BLE001 — SSE-Fehler an Client
            yield f"data: {json.dumps({'event': 'done', 'payload': {'type': 'answer', 'text': str(err)}}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/publish")
def post_publish(
    payload: TicketPublishIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    service: IntakeService = Depends(get_service),
    user: User = Depends(current_actor),
) -> dict:
    try:
        result = service.publish_ticket(
            title=payload.title,
            kind=payload.kind,
            priority=payload.priority,
            fields=payload.fields,
            user=user,
            wait_for_sync=payload.waitSync,
        )
    except NotReadyForCreation as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from err
    if not payload.waitSync and result.get("requestId"):
        # Commit bevor Background läuft — sonst sieht der Job die Outbox nicht.
        db.commit()
        request_id = str(result["requestId"])

        def _sync_later() -> None:
            import logging

            from app.db import SessionLocal
            from app.ports import build_ticket_port
            from app.sync.outbox import process_request

            log = logging.getLogger("triage.sync")
            with SessionLocal() as session:
                try:
                    stats = process_request(session, build_ticket_port(), request_id)
                    session.commit()
                    log.info("async create %s %s", request_id[:8], stats)
                except Exception:
                    session.rollback()
                    log.exception("async create fehlgeschlagen %s", request_id[:8])

        background_tasks.add_task(_sync_later)
    return result


@router.post("/polish")
def post_polish(
    payload: PolishIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    try:
        return {
            "text": polish_description(
                db,
                payload.text,
                payload.title,
                payload.field,
                payload.kind,
                payload.fields,
            )
        }
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/benefit")
def post_benefit(
    payload: PolishIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    try:
        return {"text": infer_benefit(db, payload.text, payload.title)}
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/reason")
def post_reason(
    payload: ReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    try:
        return {
            "text": infer_reason(
                db, payload.text, payload.title, payload.benefit
            )
        }
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/solution")
def post_solution(
    payload: SolutionIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    try:
        return {
            "text": infer_solution(
                db,
                payload.text,
                payload.title,
                payload.benefit,
                payload.reason,
            )
        }
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/risks")
def post_risks(
    payload: RiskIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    try:
        return {
            "text": infer_risks(
                db,
                payload.text,
                payload.title,
                payload.benefit,
                payload.reason,
                payload.solution,
            )
        }
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/overview")
def post_overview(
    payload: PolishIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    try:
        return infer_overview(db, payload.text, payload.title)
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/effort")
def post_effort(
    payload: EffortIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    """Prüft Nutzer-PT und schlägt eine Spanne aus Detailgrad + Web vor."""
    try:
        return review_effort(
            db,
            payload.text,
            title=payload.title,
            kind=payload.kind,
            fb=payload.fb,
            it=payload.it,
        )
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


def _public_base(request: Request) -> str:
    from app.config import get_settings

    configured = (get_settings().public_base_url or "").strip().rstrip("/")
    if configured and "127.0.0.1" not in configured and "localhost" not in configured:
        return configured
    # Fallback: Cidaas-Redirect-Host (Prod) oder Request-Host
    redirect = (get_settings().cidaas_redirect_url or "").strip()
    if redirect.startswith("http"):
        from urllib.parse import urlparse

        parsed = urlparse(redirect)
        if parsed.scheme and parsed.netloc and "127.0.0.1" not in parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    ).split(",")[0].strip()
    return f"{proto}://{host}"


@router.get("/effort-sheet/template")
def get_effort_sheet_template(
    dummy: bool = Query(default=False),
    user: User = Depends(current_actor),
) -> Response:
    content = dummy_template_bytes() if dummy else template_bytes()
    name = "aufwand-dummy.csv" if dummy else "aufwand-vorlage.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/effort-sheet")
def post_effort_sheet(
    payload: EffortSheetIn,
    user: User = Depends(current_actor),
) -> dict:
    try:
        return fetch_effort_sheet(payload.url)
    except EffortSheetError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err


@router.post("/effort-sheet/xlsx")
def post_effort_sheet_xlsx(
    payload: EffortSheetCommitIn,
    user: User = Depends(current_actor),
) -> Response:
    try:
        data = kalkulation_xlsx(payload.csv)
    except EffortSheetError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="kalkulation.xlsx"'},
    )


@router.post("/effort-sheet/commit")
def post_effort_sheet_commit(
    payload: EffortSheetCommitIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    try:
        parsed = commit_effort_csv(
            db, payload.csv, _public_base(request), share_id=payload.share_id
        )
    except EffortSheetError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    from app.services.jira_inbox import find_request_by_effort_share
    from app.services.requests_service import get_request, update_request

    ticket = None
    if payload.request_id:
        ticket = get_request(db, payload.request_id)
    if not ticket and parsed.get("share_id"):
        ticket = find_request_by_effort_share(db, str(parsed.get("share_id")))
    if ticket:
        update_request(db, ticket, effort_sync_fields(parsed))
        parsed["request_id"] = ticket.id
        parsed["reference"] = ticket.reference
    return parsed


@router.post("/priority")
def post_priority(
    payload: ContextIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    return priority_payload(payload.text, db=db, use_llm=True)


@router.post("/kind")
def post_kind(
    payload: ContextIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_actor),
) -> dict:
    return kind_payload(payload.text, db=db, use_llm=True)


@router.post("/{session_id}/message")
def post_message(
    session_id: str,
    payload: MessageIn,
    assistant: AssistantService = Depends(get_assistant),
    user: User = Depends(current_actor),
) -> dict:
    session = _load(assistant.intake, session_id, user)
    client = payload.client.model_dump() if payload.client else None
    return assistant.handle(session, payload.text, client, actor=user)


@router.post("/{session_id}/override")
def post_override(
    session_id: str,
    payload: OverrideIn,
    service: IntakeService = Depends(get_service),
    user: User = Depends(current_actor),
) -> dict:
    session = _load(service, session_id, user)
    try:
        return service.override(session, kind=payload.kind, priority=payload.priority)
    except NotReadyForCreation as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from err


@router.patch("/{session_id}/draft")
def patch_draft(
    session_id: str,
    payload: DraftPatchIn,
    service: IntakeService = Depends(get_service),
    user: User = Depends(current_actor),
) -> dict:
    session = _load(service, session_id, user)
    try:
        return service.patch_draft(session, payload.fields)
    except NotReadyForCreation as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from err


@router.post("/{session_id}/ai-fill")
def post_ai_fill(
    session_id: str,
    payload: AiFillIn,
    assistant: AssistantService = Depends(get_assistant),
    user: User = Depends(current_actor),
) -> dict:
    # AssistantService hat Zugriff auf die Intake-Service, wir nutzen aber
    # direkt den Intake-Service für den Draft-Writeback.
    session = _load(assistant.intake, session_id, user)
    return assistant.intake.ai_fill(session, field_key=payload.fieldKey, overwrite=payload.overwrite, user=user)


@router.post("/{session_id}/confirm")
def post_confirm(
    session_id: str,
    service: IntakeService = Depends(get_service),
    user: User = Depends(current_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    session = _load(service, session_id, user)
    try:
        payload = service.confirm(session, idempotency_key=idempotency_key, user=user)
    except NotReadyForCreation as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from err
    # Soft-Hinweis nach Anlage: naechster Turn bleibt im Chat.
    reference = payload.get("reference") or ""
    payload["hint"] = (
        f"{reference} liegt. Frag nach offenen Anliegen, setz Priorität, "
        "oder beschreib das Nächste."
    ).strip()
    return payload


share_router = APIRouter(tags=["intake"])


@share_router.get("/aufwand/{share_id}/xlsx")
def effort_sheet_share_xlsx(share_id: str, db: Session = Depends(get_db)) -> Response:
    csv_text = ensure_effort_share(db, share_id)
    db.commit()
    data = kalkulation_xlsx(csv_text)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="kalkulation-{share_id[:8]}.xlsx"'
        },
    )


@share_router.get("/aufwand/{share_id}/meta")
def effort_sheet_share_meta(share_id: str, db: Session = Depends(get_db)) -> dict:
    from app.ports.jira_v3 import public_browse_url
    from app.services.jira_inbox import find_request_by_effort_share

    ticket = find_request_by_effort_share(db, share_id)
    if not ticket:
        return {"key": "", "url": "", "title": ""}
    ref = ticket.external_refs[0] if ticket.external_refs else None
    key = str((ref.external_key if ref else "") or ticket.reference or "").strip()
    url = public_browse_url(ref.external_url if ref else "", key) if key else ""
    return {"key": key, "url": url, "title": ticket.title or ""}


@share_router.get("/aufwand/{share_id}/data")
def effort_sheet_share_data(share_id: str, db: Session = Depends(get_db)) -> Response:
    csv_text = ensure_effort_share(db, share_id)
    db.commit()
    body = csv_text if isinstance(csv_text, str) else csv_text.decode("utf-8")
    if not body.startswith("\ufeff"):
        body = f"\ufeff{body}"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="kalkulation-{share_id[:8]}.csv"'
        },
    )


@share_router.put("/aufwand/{share_id}")
@share_router.post("/aufwand/{share_id}")
async def effort_sheet_share_save(
    share_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Öffentlicher Speicherpunkt für den Aufwand-Link (Jira / Share)."""
    from app.config import get_settings
    from app.services.jira_inbox import find_request_by_effort_share
    from app.services.requests_service import update_request

    raw = (await request.body()).decode("utf-8", errors="replace")
    csv_text = raw.lstrip("\ufeff").strip()
    if len(csv_text) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV fehlt")
    base = (get_settings().public_base_url or "").rstrip("/")
    if not base or "127.0.0.1" in base or "localhost" in base:
        redirect = (get_settings().cidaas_redirect_url or "").strip()
        if redirect.startswith("http"):
            from urllib.parse import urlparse

            parsed_u = urlparse(redirect)
            base = f"{parsed_u.scheme}://{parsed_u.netloc}"
        else:
            base = _public_base(request)
    ensure_effort_share(db, share_id, public_base=base)
    try:
        parsed = commit_effort_csv(db, csv_text, base, share_id=share_id)
    except EffortSheetError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    ticket = find_request_by_effort_share(db, share_id)
    if ticket:
        update_request(db, ticket, effort_sync_fields(parsed))
        parsed["request_id"] = ticket.id
        parsed["reference"] = ticket.reference
    db.commit()
    return {"ok": True, "share_id": share_id, "synced": bool(ticket), **{k: parsed.get(k) for k in ("request_id", "reference", "total_costs", "costs") if parsed.get(k)}}


@share_router.get("/aufwand/{share_id}")
def effort_sheet_share(share_id: str, db: Session = Depends(get_db)) -> FileResponse:
    # Fehlende Shares (z. B. alter Jira-Link) automatisch anlegen statt 404.
    ensure_effort_share(db, share_id)
    db.commit()
    return FileResponse(ROOT / "static" / "effort-sheet.html", media_type="text/html")
