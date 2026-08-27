from app.services.effort import format_pt, heuristic_pt, tshirt_for


def test_tshirt_bands():
    assert tshirt_for(1) == "XS"
    assert tshirt_for(2) == "XS"
    assert tshirt_for(3) == "S"
    assert tshirt_for(5) == "S"
    assert tshirt_for(6) == "M"
    assert tshirt_for(15) == "M"
    assert tshirt_for(16) == "L"
    assert tshirt_for(40) == "L"
    assert tshirt_for(41) == "XL"


def test_format_pt():
    assert format_pt(3) == "3 PT"
    assert format_pt(1.5) == "1,5 PT"
    assert format_pt(0) == "0 PT"


def test_heuristic_change_has_no_it():
    fb, it = heuristic_pt("Neue Abstimmungsrunde zwischen Bau und Event.", False)
    assert fb >= 2
    assert it == 0


def test_heuristic_it_gets_it_days():
    fb, it = heuristic_pt("SAP-Schnittstelle für die Buchung anbinden.", True)
    assert it >= 3
