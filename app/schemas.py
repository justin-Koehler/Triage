from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.domain.types import Priority, RequestKind, RequestStatus


class ClientContext(BaseModel):
    """Was der Browser ueber sich selbst verraet. Alles optional, nichts erzwungen."""

    userAgent: str | None = Field(default=None, max_length=500)
    brands: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    platform: str | None = Field(default=None, max_length=60)
    platformVersion: str | None = Field(default=None, max_length=40)
    mobile: bool | None = None
    screen: str | None = Field(default=None, max_length=40)
    language: str | None = Field(default=None, max_length=40)
    timezone: str | None = Field(default=None, max_length=60)
    page: str | None = Field(default=None, max_length=200)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    client: ClientContext | None = None

    @field_validator("text")
    @classmethod
    def strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("leer")
        return stripped


class PolishIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    title: str = Field(default="", max_length=200)
    field: str = Field(default="description", max_length=40)
    kind: str = Field(default="", max_length=40)
    fields: dict[str, str] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("leer")
        return stripped

    @field_validator("title", "field", "kind")
    @classmethod
    def strip_meta(cls, value: str) -> str:
        return value.strip()

    @field_validator("fields")
    @classmethod
    def clip_fields(cls, value: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, raw in (value or {}).items():
            name = str(key or "").strip()[:80]
            if not name:
                continue
            out[name] = str(raw or "").strip()[:4000]
            if len(out) >= 80:
                break
        return out


class ReasonIn(PolishIn):
    benefit: str = Field(default="", max_length=4000)

    @field_validator("benefit")
    @classmethod
    def strip_benefit(cls, value: str) -> str:
        return value.strip()


class SolutionIn(ReasonIn):
    reason: str = Field(default="", max_length=4000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class RiskIn(SolutionIn):
    solution: str = Field(default="", max_length=4000)

    @field_validator("solution")
    @classmethod
    def strip_solution(cls, value: str) -> str:
        return value.strip()


class EffortSheetIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.strip()


class EffortSheetCommitIn(BaseModel):
    csv: str = Field(min_length=8, max_length=50000)

    @field_validator("csv")
    @classmethod
    def strip_csv(cls, value: str) -> str:
        return value.strip()


class EffortIn(PolishIn):
    kind: str = Field(default="", max_length=40)
    # Nutzer-Angabe — KI prüft nur, schätzt nicht neu.
    fb: str = Field(default="", max_length=40)
    it: str = Field(default="", max_length=40)

    @field_validator("kind", "fb", "it")
    @classmethod
    def strip_effort_fields(cls, value: str) -> str:
        return value.strip()


class ContextIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("leer")
        return stripped


class DraftPatchIn(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)


class TicketPublishIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="change_request", max_length=40)
    priority: str = Field(default="medium", max_length=20)
    fields: dict[str, str] = Field(default_factory=dict)
    waitSync: bool = True

    @field_validator("title", "kind", "priority")
    @classmethod
    def strip_meta(cls, value: str) -> str:
        return value.strip()

    @field_validator("fields")
    @classmethod
    def clip_fields(cls, value: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, raw in (value or {}).items():
            name = str(key or "").strip()[:80]
            if not name:
                continue
            out[name] = str(raw or "").strip()[:4000]
            if len(out) >= 80:
                break
        return out


class AiFillIn(BaseModel):
    fieldKey: str = Field(min_length=1, max_length=80)
    overwrite: bool = False


class OverrideIn(BaseModel):
    kind: RequestKind | None = None
    priority: Priority | None = None


class RequestPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    status: RequestStatus | None = None
    priority: Priority | None = None
    service: str | None = Field(default=None, max_length=80)
    responsible: str | None = Field(default=None, max_length=80)
    company: str | None = Field(default=None, max_length=80)
    change_lead: str | None = Field(default=None, max_length=80)
    fields: dict[str, str] = Field(default_factory=dict)

    def changes(self) -> dict:
        payload = self.model_dump(exclude_none=True, exclude={"fields"})
        if payload.get("responsible") and "change_lead" not in payload:
            payload["change_lead"] = payload.pop("responsible")
        else:
            payload.pop("responsible", None)
        payload.pop("service", None)
        payload.update(self.fields)
        return {k: (v.value if hasattr(v, "value") else v) for k, v in payload.items()}


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class StatusUpdateIn(BaseModel):
    reportedOn: str | None = Field(default=None, max_length=10)
    overallRag: str | None = Field(default=None, max_length=16)
    summary: str | None = None
    decisions: str | None = None
    risks: str | None = None
    nextSteps: str | None = None
    scheduleRag: str | None = Field(default=None, max_length=16)
    scheduleReason: str | None = None
    planStart: str | None = None
    planEnd: str | None = None
    actualStart: str | None = None
    actualEnd: str | None = None
    milestones: list[dict] | None = None
    costRag: str | None = Field(default=None, max_length=16)
    costPlanFb: str | None = None
    costPlanIt: str | None = None
    costPlanLicense: str | None = None
    costActualFb: str | None = None
    costActualIt: str | None = None
    costActualLicense: str | None = None
    body: str | None = Field(default=None, max_length=8000)


class LoginIn(BaseModel):
    account: str = Field(min_length=1, max_length=80)


class LlmSettingsIn(BaseModel):
    provider: str | None = None
    model: str | None = None
    baseUrl: str | None = None
    timeout: int | None = Field(default=None, ge=5, le=600)
    apiKey: str | None = None


class JiraSettingsIn(BaseModel):
    enabled: bool | None = None
    baseUrl: str | None = None
    searchUrl: str | None = None
    email: str | None = None
    projectKey: str | None = None
    apiToken: str | None = None
    apiKey: str | None = None
    oauthTokenUrl: str | None = None
    clientId: str | None = None
    clientSecret: str | None = None
    effortSheetField: str | None = None
    effortSheetTemplateUrl: str | None = None


class SettingsIn(BaseModel):
    llm: LlmSettingsIn | None = None
    jira: JiraSettingsIn | None = None
