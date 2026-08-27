"""Browser-Erkennung: Client Hints schlagen den User-Agent."""

from __future__ import annotations

from app.domain.clientinfo import describe

CHROME = {
    "userAgent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "brands": [
        {"brand": "Not)A;Brand", "version": "99.0.0.0"},
        {"brand": "Chromium", "version": "141.0.7390.55"},
        {"brand": "Google Chrome", "version": "141.0.7390.55"},
    ],
    "platform": "Windows",
    "platformVersion": "15.0.0",
    "screen": "2560x1440",
    "timezone": "Europe/Berlin",
}

SAFARI = {
    "userAgent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.3 Safari/605.1.15"
    ),
    "screen": "1512x982",
    "timezone": "Europe/Berlin",
}


def test_client_hints_beat_the_user_agent():
    assert describe(CHROME) == "Chrome 141 auf Windows 11, 2560x1440, Zeitzone Europe/Berlin"


def test_windows_ten_stays_windows_ten():
    assert describe(CHROME | {"platformVersion": "10.0.0"}).startswith("Chrome 141 auf Windows 10")


def test_phantasiemarke_wird_ignoriert():
    only_noise = {"brands": [{"brand": "Not/A)Brand", "version": "8.0.0.0"}], "userAgent": ""}
    assert describe(only_noise) == ""


def test_safari_faellt_auf_den_user_agent_zurueck():
    assert describe(SAFARI) == "Safari 18 auf macOS, 1512x982, Zeitzone Europe/Berlin"


def test_firefox_ohne_hints():
    firefox = {
        "userAgent": "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
    }
    assert describe(firefox) == "Firefox 130 auf Linux"


def test_mobilgeraet_wird_genannt():
    android = {
        "userAgent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/141.0.0.0 Mobile",
        "mobile": True,
    }
    assert describe(android) == "Chrome 141 auf Android 14, Mobilgerät"


def test_leerer_kontext_bleibt_leer():
    assert describe(None) == ""
    assert describe({}) == ""
