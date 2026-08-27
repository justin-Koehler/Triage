from app.domain.types import RequestKind
from app.services.classify import infer_kind, match_it


def test_sap_is_it_request():
    assert match_it("Schnittstelle nach SAP einrichten")
    assert infer_kind("Schnittstelle nach SAP einrichten") is RequestKind.IT_REQUEST


def test_process_without_it_is_change():
    text = "Abteilungen zusammenlegen, neue Abstimmung im Jour fixe."
    assert not match_it(text)
    assert infer_kind(text) is RequestKind.CHANGE_REQUEST


def test_llm_marks_it_when_keywords_miss(monkeypatch):
    class Fake:
        name = "test"

        def complete_json(self, system, user):
            assert "kind" in system
            return {"kind": "it_request"}

    monkeypatch.setattr("app.services.classify.get_runtime_config", lambda db: None)
    monkeypatch.setattr("app.services.classify.build_provider_from_runtime", lambda runtime: Fake())
    kind = infer_kind(
        "Die Fachanwendung muss angepasst werden, sonst kann niemand buchen.",
        db=object(),
        use_llm=True,
    )
    assert kind is RequestKind.IT_REQUEST


def test_portal_without_llm_is_change():
    text = (
        "Neues Informationsportal für den Kulturwandel: nur Texte und "
        "Abstimmungsrunden, keine technische Umsetzung durch IT."
    )
    assert not match_it(text)
    assert infer_kind(text) is RequestKind.CHANGE_REQUEST


def test_llm_overrides_keyword_false_positive(monkeypatch):
    """Keyword 'portal' allein darf nicht gegen den LLM-Kontext gewinnen."""
    text = (
        "Neues Informationsportal für den Kulturwandel: nur Texte und "
        "Abstimmungsrunden, keine technische Umsetzung durch IT."
    )
    assert not match_it(text)

    class Fake:
        name = "test"

        def complete_json(self, system, user):
            return {"kind": "change_request"}

    monkeypatch.setattr("app.services.classify.get_runtime_config", lambda db: None)
    monkeypatch.setattr("app.services.classify.build_provider_from_runtime", lambda runtime: Fake())
    assert infer_kind(text, db=object(), use_llm=True) is RequestKind.CHANGE_REQUEST


def test_llm_unavailable_falls_back_to_keywords(monkeypatch):
    from app.triage.providers import LlmUnavailable

    class Fake:
        name = "test"

        def complete_json(self, system, user):
            raise LlmUnavailable("offline")

    monkeypatch.setattr("app.services.classify.get_runtime_config", lambda db: None)
    monkeypatch.setattr("app.services.classify.build_provider_from_runtime", lambda runtime: Fake())
    assert (
        infer_kind("SAP-Schnittstelle anbinden", db=object(), use_llm=True)
        is RequestKind.IT_REQUEST
    )
