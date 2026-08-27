from app.domain.steckbrief_style import DEFAULT_CLIP
from app.services.prose import _is_copy, clip_tight


def test_exact_copy_is_rejected():
    text = "Urlaubsanträge sollen digital erfasst werden."
    assert _is_copy(text, text)


def test_benefit_with_new_effect_is_kept():
    description = "Urlaubsanträge laufen heute per Papier über drei Stellen."
    benefit = "Weniger Aufwand und weniger verlorene Anträge."
    assert not _is_copy(description, benefit)


def test_embedded_description_is_rejected():
    description = "Urlaubsanträge sollen digital erfasst werden im ganzen Haus."
    benefit = "Urlaubsanträge sollen digital erfasst werden im ganzen Haus, das hilft allen."
    assert _is_copy(description, benefit)


def test_clip_tight_keeps_short_text():
    assert clip_tight("Weniger Aufwand.") == "Weniger Aufwand."


def test_clip_tight_cuts_long_prose():
    text = ("Der Change reduziert manuelle Nacharbeit in den betroffenen Abläufen. " * 40).strip()
    out = clip_tight(text)
    assert len(out) <= DEFAULT_CLIP
    assert len(out) < len(text)
