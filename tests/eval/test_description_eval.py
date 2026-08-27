from __future__ import annotations

import os

import pytest

from app.domain.description import (
    description_job,
    description_user_prompt,
    normalize_description,
    polish_mode,
    score_description,
)
from tests.eval.golden_descriptions import GOLDEN_BAD, GOLDEN_GOOD, GOLDEN_POLISH_INPUTS


@pytest.mark.parametrize("case", GOLDEN_GOOD, ids=[c["id"] for c in GOLDEN_GOOD])
def test_golden_good_scores_ok(case):
    scored = score_description(case["text"], case.get("draft", ""))
    assert scored.ok, f"{case['id']}: {scored.issues}"
    assert case["min_sentences"] <= scored.sentences <= case["max_sentences"]
    if case.get("must_have_soll"):
        assert scored.has_soll


@pytest.mark.parametrize("case", GOLDEN_BAD, ids=[c["id"] for c in GOLDEN_BAD])
def test_golden_bad_flags_issues(case):
    scored = score_description(case["text"], case.get("draft", ""))
    assert not scored.ok
    for needle in case["expect_issues"]:
        assert needle in scored.issues, f"{case['id']}: want {needle} in {scored.issues}"


@pytest.mark.parametrize(
    "case",
    GOLDEN_POLISH_INPUTS[:4],
    ids=[c["id"] for c in GOLDEN_POLISH_INPUTS[:4]],
)
def test_prompt_split_and_mode_for_golden_drafts(case):
    mode = polish_mode(case["draft"])
    user = description_user_prompt(case["draft"], case["kind"], mode)
    job = description_job(case["kind"])
    assert "Ist → Problem → Soll" in job
    if case["kind"] == "it_request":
        assert "Systeme" in job or "IT" in job
    else:
        assert "Prozess" in job or "Change" in job
    if mode == "expand":
        assert "Ausformulieren" in user
    else:
        assert "Klarziehen" in user


def _llm_ready() -> bool:
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if provider in {"", "none", "off", "disabled"}:
        return False
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or provider == "fake")


@pytest.mark.eval
@pytest.mark.skipif(not _llm_ready(), reason="LLM nicht konfiguriert")
@pytest.mark.parametrize(
    "case",
    GOLDEN_POLISH_INPUTS,
    ids=[c["id"] for c in GOLDEN_POLISH_INPUTS],
)
def test_polish_golden_live(case, tmp_path, monkeypatch):
    db_path = tmp_path / "eval.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("TICKET_PORT", "fake")

    from app.config import get_settings

    get_settings.cache_clear()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.db as dbmod
    import app.models  # noqa: F401
    from app.db import Base
    from app.services.polish import polish_description

    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    dbmod.engine = engine
    dbmod.SessionLocal = Session

    with Session() as db:
        out = polish_description(
            db,
            case["draft"],
            title=case["id"],
            field="description",
            kind=case["kind"],
        )
    out = normalize_description(out, case["draft"])
    scored = score_description(out, case["draft"])
    assert scored.ok, f"{case['id']}: {scored.issues}\n{out}"
    assert case["min_sentences"] <= scored.sentences <= case["max_sentences"]
    if case.get("must_have_soll"):
        assert scored.has_soll, out
    lowered = out.lower()
    assert "auftraggeber" not in lowered
    assert "gemeinnützig" not in lowered
    assert "signifikant" not in lowered
