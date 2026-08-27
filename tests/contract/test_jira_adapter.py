"""Jira-Adapter gegen aufgezeichnete Fixtures (kein Netz)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.domain.types import Priority, RequestKind
from app.ports.jira_v3 import JiraRestV3
from app.ports.ticket_port import IssuePayload, TicketPortError
from app.services.settings_service import RuntimeConfig

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def runtime():
    return RuntimeConfig(
        llm_provider="ollama",
        llm_model="x",
        llm_base_url="",
        llm_api_key="",
        llm_timeout=30,
        jira_enabled=True,
        jira_base_url="https://example.atlassian.net",
        jira_search_url="",
        jira_email="bot@example.com",
        jira_api_token="token",
        jira_api_key="",
        jira_oauth_token_url="",
        jira_client_id="",
        jira_client_secret="",
        jira_project_key="TRI",
    )


def test_create_issue_builds_adf_and_parses_key(runtime, monkeypatch):
    captured = {}

    def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        request = httpx.Request(method, "https://example.atlassian.net" + path)
        return httpx.Response(201, json={"key": "TRI-42", "id": "10042"}, request=request)

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    port = JiraRestV3(runtime=runtime)
    ref = port.create_issue(
        IssuePayload(
            request_id="r1",
            reference="AN-1001",
            kind=RequestKind.CHANGE_REQUEST,
            priority=Priority.HIGH,
            title="Kommunikation zentralisieren",
            steckbrief_name="Change Request: Kommunikation zentralisieren",
            description="Bereichsübergreifend",
            fields={"sponsor": "SCS"},
            labels=["triage-intake"],
        )
    )
    assert ref.key == "TRI-42"
    assert "TRI-42" in ref.url
    assert captured["method"] == "POST"
    assert captured["path"] == "/rest/api/3/issue"
    fields = captured["json"]["fields"]
    assert fields["summary"] == "Kommunikation zentralisieren"
    assert fields["description"]["type"] == "doc"
    assert fields["project"]["key"] == "TRI"
    assert fields.get("customfield_19753") == "Change Request: Kommunikation zentralisieren"


def _payload(**extra):
    data = dict(
        request_id="r1",
        reference="AN-1001",
        kind=RequestKind.CHANGE_REQUEST,
        priority=Priority.HIGH,
        title="Kommunikation zentralisieren",
        steckbrief_name="Change Request: Kommunikation zentralisieren",
        description="Bereichsübergreifend",
        fields={"sponsor": "SCS"},
        labels=["triage-intake"],
    )
    data.update(extra)
    return IssuePayload(**data)


def test_gateway_sends_apikey_and_bearer_auth(runtime, monkeypatch):
    runtime.jira_api_key = "gw-key"
    runtime.jira_search_url = "https://gw.example/jira/v1/api/2/search"
    captured = {}

    def fake(method, url, **kwargs):
        captured["headers"] = kwargs.get("headers") or {}
        captured["auth"] = kwargs.get("auth")
        request = httpx.Request(method, url)
        return httpx.Response(201, json={"key": "TRI-9", "id": "9"}, request=request)

    monkeypatch.setattr(httpx, "request", fake)
    JiraRestV3(runtime=runtime).create_issue(_payload())
    assert captured["headers"]["x-apikey"] == "gw-key"
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["auth"] is None


def test_gateway_create_uses_api2_plain_description(runtime, monkeypatch):
    runtime.jira_search_url = "https://gw.example/jira/v1/api/2/search"
    captured = {}

    def fake_request(self, method, path, **kwargs):
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        request = httpx.Request(method, "https://gw.example" + path)
        return httpx.Response(201, json={"key": "TRI-9", "id": "9"}, request=request)

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    ref = JiraRestV3(runtime=runtime).create_issue(_payload())
    assert ref.key == "TRI-9"
    assert captured["path"] == "/issue"
    assert isinstance(captured["json"]["fields"]["description"], str)
    assert captured["json"]["fields"]["customfield_19753"] == (
        "Change Request: Kommunikation zentralisieren"
    )


def test_gateway_oauth_uses_bearer_token(runtime, monkeypatch):
    runtime.jira_api_key = "gw-key"
    runtime.jira_search_url = "https://gw.example/jira/v1/api/2/search"
    runtime.jira_oauth_token_url = "https://gw.example/oauth/token"
    runtime.jira_client_id = "cid"
    runtime.jira_client_secret = "sec"
    captured = {}

    def fake_post(url, **kwargs):
        captured["token_url"] = url
        captured["token_headers"] = kwargs.get("headers") or {}
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"access_token": "oauth-123", "expires_in": 3600},
            request=request,
        )

    def fake_request(method, url, **kwargs):
        captured["headers"] = kwargs.get("headers") or {}
        captured["auth"] = kwargs.get("auth")
        request = httpx.Request(method, url)
        return httpx.Response(201, json={"key": "TRI-10", "id": "10"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "request", fake_request)
    JiraRestV3(runtime=runtime).create_issue(_payload())

    assert captured["token_url"] == "https://gw.example/oauth/token"
    assert captured["token_headers"]["x-apikey"] == "gw-key"
    assert captured["headers"]["x-apikey"] == "gw-key"
    assert captured["headers"]["Authorization"] == "Bearer oauth-123"
    assert captured["auth"] is None


def test_redirect_is_not_treated_as_json(runtime, monkeypatch):
    def fake(method, url, **kwargs):
        request = httpx.Request(method, url)
        return httpx.Response(
            302,
            headers={"location": "https://login.example"},
            request=request,
        )

    monkeypatch.setattr(httpx, "request", fake)
    with pytest.raises(TicketPortError, match="302"):
        JiraRestV3(runtime=runtime).create_issue(_payload())


def test_create_issue_sets_reporter_from_hint(runtime, monkeypatch):
    captured = {}

    def fake_request(self, method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        request = httpx.Request(method, "https://example.atlassian.net" + path)
        return httpx.Response(201, json={"key": "TRI-77", "id": "77"}, request=request)

    def fake_resolve(self, raw, *, user_token=None, user_email=None):
        assert raw == "Justin"
        return {"name": "koehlerj"}

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    monkeypatch.setattr(JiraRestV3, "resolve_user", fake_resolve)
    JiraRestV3(runtime=runtime).create_issue(
        _payload(reporter_hint="Justin", fields={"sponsor": "SCS"})
    )
    assert captured["json"]["fields"]["reporter"] == {"name": "koehlerj"}


def test_format_jira_summary_screen_error():
    from app.ports.jira_v3 import _format_jira_error

    text = _format_jira_error(
        400,
        '{"errors":{"summary":"Field \'summary\' cannot be set. It is not on the appropriate screen, or unknown."}}',
    )
    assert "Create-Berechtigung" in text or "Summary" in text


def test_search_assignable_users_paginates_past_50(runtime, monkeypatch):
    calls: list[dict] = []

    def fake_request(self, method, path, **kwargs):
        params = kwargs.get("params") or {}
        calls.append(dict(params))
        start = int(params.get("startAt") or 0)
        batch = int(params.get("maxResults") or 50)
        # 120 User → drei Seiten
        total = 120
        rows = [
            {
                "name": f"u{i}",
                "displayName": f"User {i}",
                "emailAddress": f"u{i}@example.com",
            }
            for i in range(start, min(start + batch, total))
        ]
        request = httpx.Request(method, "https://example.atlassian.net" + path)
        return httpx.Response(200, json=rows, request=request)

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    users = JiraRestV3(runtime=runtime).search_assignable_users("", limit=5000)
    assert len(users) == 120
    assert users[0]["name"] == "u0"
    assert users[-1]["name"] == "u119"
    assert len(calls) >= 3
    assert calls[0]["startAt"] == 0
    assert calls[1]["startAt"] == 50


def test_search_assignable_users_stops_when_page_repeats(runtime, monkeypatch):
    calls: list[dict] = []

    def fake_request(self, method, path, **kwargs):
        calls.append(dict(kwargs.get("params") or {}))
        request = httpx.Request(method, "https://example.atlassian.net" + path)
        return httpx.Response(
            200,
            json=[{"name": "same", "displayName": "Same", "emailAddress": ""}],
            request=request,
        )

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    users = JiraRestV3(runtime=runtime).search_assignable_users("", limit=5000)
    assert [row["name"] for row in users] == ["same"]
    assert len(calls) == 1


def test_resolve_user_uses_assignable_search(runtime, monkeypatch):
    runtime.jira_search_url = "https://gw.example/jira/v1/api/2/search"

    def fake_search(self, query="", *, limit=10, user_token=None, user_email=None):
        return [{"name": "koehlerj", "displayName": "Justin Koehler", "emailAddress": ""}]

    monkeypatch.setattr(JiraRestV3, "search_assignable_users", fake_search)
    resolved = JiraRestV3(runtime=runtime).resolve_user("Justin Koehler")
    assert resolved == {"name": "koehlerj"}
    assert JiraRestV3(runtime=runtime).resolve_user("Just") is None


def test_resolve_components_fuzzy(runtime, monkeypatch):
    runtime.jira_search_url = "https://gw.example/jira/v1/api/2/search"

    def fake_components(self, *, user_token=None, user_email=None):
        return ["CIT", "Collaborative Innovation"]

    monkeypatch.setattr(JiraRestV3, "list_components", fake_components)
    resolved = JiraRestV3(runtime=runtime).resolve_components("cit")
    assert resolved == [{"name": "CIT"}]


def test_fixture_create_response_shape():
    raw = json.loads((FIXTURES / "jira_create_issue.json").read_text(encoding="utf-8"))
    assert raw["key"].startswith("TRI-")


def test_rejected_field_ids_from_screen_error():
    from app.ports.jira_v3 import _rejected_field_ids

    ids = _rejected_field_ids(
        '{"errors":{"customfield_17203":"Field \'customfield_17203\' cannot be set. '
        'It is not on the appropriate screen, or unknown."}}'
    )
    assert ids == ["customfield_17203"]


def test_create_skips_kind_and_create_false_fields(runtime, monkeypatch):
    captured = {}

    def fake_request(self, method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        request = httpx.Request(method, "https://example.atlassian.net" + path)
        return httpx.Response(201, json={"key": "TRI-88", "id": "88"}, request=request)

    def fake_resolve(self, raw, *, user_token=None, user_email=None):
        return {"name": "someone"}

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    monkeypatch.setattr(JiraRestV3, "resolve_user", fake_resolve)
    JiraRestV3(runtime=runtime).create_issue(
        _payload(
            fields={
                "sponsor": "SCS",
                "responsible_sit": "Alice",
                "change_team": "Team A",
                "concept_cit_pt": "3",
            }
        )
    )
    fields = captured["json"]["fields"]
    assert "customfield_17203" not in fields
    assert "customfield_19652" not in fields
    assert "customfield_17200" not in fields
    desc = json.dumps(fields["description"])
    assert "Ist die verantwortliche Person aus der IT" in desc or "Alice" in desc


def test_create_retries_without_screen_rejected_fields(runtime, monkeypatch):
    calls: list[dict] = []

    def fake_request(self, method, path, **kwargs):
        body = kwargs.get("json") or {}
        request = httpx.Request(method, "https://example.atlassian.net" + path)
        if method == "POST" and path.endswith("/issue"):
            calls.append(body)
            fields = body.get("fields") or {}
            if "customfield_14203" in fields:
                raise TicketPortError(
                    "Jira 400: cannot be set",
                    rejected_fields=["customfield_14203"],
                )
            return httpx.Response(201, json={"key": "TRI-99", "id": "99"}, request=request)
        return httpx.Response(200, json={"issues": []}, request=request)

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    ref = JiraRestV3(runtime=runtime).create_issue(
        _payload(fields={"sponsor": "SCS", "stakeholder": "Finanzen"})
    )
    assert ref.key == "TRI-99"
    assert len(calls) == 2
    assert "customfield_14203" in calls[0]["fields"]
    assert "customfield_14203" not in calls[1]["fields"]


def test_create_issue_sends_effort_sheet_url(runtime, monkeypatch):
    runtime.jira_effort_sheet_field = "customfield_99901"
    captured = {}

    def fake_request(self, method, path, **kwargs):
        captured["json"] = kwargs.get("json")
        request = httpx.Request(method, "https://example.atlassian.net" + path)
        return httpx.Response(201, json={"key": "TRI-80", "id": "80"}, request=request)

    monkeypatch.setattr(JiraRestV3, "_request", fake_request)
    JiraRestV3(runtime=runtime).create_issue(
        _payload(
            fields={
                "sponsor": "SCS",
                "effort_sheet_url": "https://docs.google.com/spreadsheets/d/abc/edit",
            }
        )
    )
    fields = captured["json"]["fields"]
    assert fields["customfield_99901"] == "https://docs.google.com/spreadsheets/d/abc/edit"
