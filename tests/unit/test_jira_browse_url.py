from app.ports.jira_v3 import public_browse_url


def test_gateway_browse_opens_jira_ui():
    raw = "https://live.api.schwarz/sit/atlassian-schwarz/browse/SCSCM-12"
    assert public_browse_url(raw, "SCSCM-12") == "https://jira.schwarz/browse/SCSCM-12"


def test_existing_ui_link_stays():
    raw = "https://jira.schwarz/browse/SCSCM-3"
    assert public_browse_url(raw, "SCSCM-3") == raw


def test_missing_url_uses_key():
    assert public_browse_url("", "SCSCM-9") == "https://jira.schwarz/browse/SCSCM-9"
