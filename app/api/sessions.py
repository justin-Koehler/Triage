from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

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
    fetch_effort_sheet,
    load_share_csv,
    share_html,
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
    return AssistantService(db=db, intake=service)


def _load(service: IntakeService, session_id: str):
    try:
        return service.load_session(session_id)
    except SessionNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session unbekannt") from None


@router.post("")
def create_session(
    service: IntakeService = Depends(get_service),
    user: User = Depends(current_actor),
) -> dict:
    session = service.create_session(user)
    return {"sessionId": session.id}


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
    _: User = Depends(current_actor),
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
    _: User = Depends(current_actor),
) -> dict:
    try:
        return {"text": infer_benefit(db, payload.text, payload.title)}
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/reason")
def post_reason(
    payload: ReasonIn,
    db: Session = Depends(get_db),
    _: User = Depends(current_actor),
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
    _: User = Depends(current_actor),
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
    _: User = Depends(current_actor),
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
    _: User = Depends(current_actor),
) -> dict:
    try:
        return infer_overview(db, payload.text, payload.title)
    except LlmUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err


@router.post("/effort")
def post_effort(
    payload: EffortIn,
    db: Session = Depends(get_db),
    _: User = Depends(current_actor),
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


@router.get("/effort-sheet/template")
def get_effort_sheet_template(_: User = Depends(current_actor)) -> Response:
    return Response(
        content=template_bytes(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="aufwand-vorlage.csv"'},
    )


@router.post("/effort-sheet")
def post_effort_sheet(
    payload: EffortSheetIn,
    _: User = Depends(current_actor),
) -> dict:
    try:
        return fetch_effort_sheet(payload.url)
    except EffortSheetError as err:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(err)) from err


@router.post("/effort-sheet/commit")
def post_effort_sheet_commit(
    payload: EffortSheetCommitIn,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(current_actor),
) -> dict:
    try:
        return commit_effort_csv(db, payload.csv, str(request.base_url))
    except EffortSheetError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err


@router.post("/priority")
def post_priority(
    payload: ContextIn,
    db: Session = Depends(get_db),
    _: User = Depends(current_actor),
) -> dict:
    return priority_payload(payload.text, db=db, use_llm=True)


@router.post("/kind")
def post_kind(
    payload: ContextIn,
    db: Session = Depends(get_db),
    _: User = Depends(current_actor),
) -> dict:
    return kind_payload(payload.text, db=db, use_llm=True)


@router.post("/{session_id}/message")
def post_message(
    session_id: str,
    payload: MessageIn,
    assistant: AssistantService = Depends(get_assistant),
    user: User = Depends(current_actor),
) -> dict:
    session = _load(assistant.intake, session_id)
    client = payload.client.model_dump() if payload.client else None
    return assistant.handle(session, payload.text, client, actor=user)


@router.post("/{session_id}/override")
def post_override(
    session_id: str,
    payload: OverrideIn,
    service: IntakeService = Depends(get_service),
    _: User = Depends(current_actor),
) -> dict:
    session = _load(service, session_id)
    try:
        return service.override(session, kind=payload.kind, priority=payload.priority)
    except NotReadyForCreation as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err)) from err


@router.patch("/{session_id}/draft")
def patch_draft(
    session_id: str,
    payload: DraftPatchIn,
    service: IntakeService = Depends(get_service),
    _: User = Depends(current_actor),
) -> dict:
    session = _load(service, session_id)
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
    session = _load(assistant.intake, session_id)
    return assistant.intake.ai_fill(session, field_key=payload.fieldKey, overwrite=payload.overwrite, user=user)


@router.post("/{session_id}/confirm")
def post_confirm(
    session_id: str,
    service: IntakeService = Depends(get_service),
    user: User = Depends(current_actor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    session = _load(service, session_id)
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


@share_router.get("/aufwand/{share_id}", response_class=HTMLResponse)
def effort_sheet_share(share_id: str, db: Session = Depends(get_db)) -> str:
    csv_text = load_share_csv(db, share_id)
    if not csv_text:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aufwandstabelle unbekannt")
    return share_html(csv_text)
