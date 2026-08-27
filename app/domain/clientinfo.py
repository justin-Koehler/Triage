"""Browser und Geraet aus dem Client-Kontext lesen, statt danach zu fragen.

Der User-Agent von aktuellem Chrome nennt eine eingefrorene Version (UA-Reduction),
er taugt nur noch als Fallback. Genau ist die `fullVersionList` aus den Client
Hints, die das Frontend ueber `navigator.userAgentData` mitschickt. Safari und
Firefox liefern die nicht, dort bleibt der User-Agent die einzige Quelle.
"""

from __future__ import annotations

import re

# Chromium mischt absichtlich eine Phantasiemarke in die Liste, damit niemand
# stur nach festen Namen sucht. Die Satzzeichen darin wechseln pro Version,
# deshalb wird vor dem Vergleich alles ausser Buchstaben entfernt.
NON_ALNUM = re.compile(r"[^a-z0-9]")
BRAND_NAMES = {
    "google chrome": "Chrome",
    "microsoft edge": "Edge",
    "opera": "Opera",
    "brave": "Brave",
    "vivaldi": "Vivaldi",
    "chromium": "Chromium",
}

UA_BROWSERS = (
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/(\d+)")),
    ("Opera", re.compile(r"OPR/(\d+)")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/(\d+)")),
    ("Firefox", re.compile(r"Firefox/(\d+)")),
    ("Chrome", re.compile(r"Chrome/(\d+)")),
    ("Safari", re.compile(r"Version/(\d+)[.\d]* Safari")),
)

UA_PLATFORMS = (
    ("Android", re.compile(r"Android (\d+)")),
    ("iOS", re.compile(r"(?:iPhone|iPad) OS (\d+)")),
    ("macOS", re.compile(r"Mac OS X (\d+)")),
    ("Windows", re.compile(r"Windows NT ([\d.]+)")),
    ("Linux", re.compile(r"Linux")),
)


def _major(version: object) -> str:
    text = str(version or "").strip()
    return text.split(".")[0] if text else ""


def _browser_from_brands(brands: object) -> str:
    if not isinstance(brands, list):
        return ""
    best = ""
    for entry in brands:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("brand") or "").strip()
        if not name or "notabrand" in NON_ALNUM.sub("", name.lower()):
            continue
        label = BRAND_NAMES.get(name.lower(), name)
        version = _major(entry.get("version"))
        candidate = f"{label} {version}".strip()
        # Chromium ist der kleinste gemeinsame Nenner, echte Marken gewinnen.
        if label == "Chromium" and best:
            continue
        if label != "Chromium" or not best:
            best = candidate
    return best


def _browser_from_ua(user_agent: str) -> str:
    for label, pattern in UA_BROWSERS:
        match = pattern.search(user_agent)
        if match:
            # Chrome-UA enthaelt auch Safari, Edge enthaelt Chrome. Reihenfolge zaehlt.
            return f"{label} {match.group(1)}"
    return ""


def _windows_release(platform_version: str) -> str:
    """Client Hints melden ab Windows 11 eine Major-Version von 13 aufwaerts."""
    major = _major(platform_version)
    if not major.isdigit():
        return "Windows"
    return "Windows 11" if int(major) >= 13 else "Windows 10"


def _platform_from_hints(platform: str, platform_version: str) -> str:
    name = platform.strip()
    if not name:
        return ""
    if name.lower() == "windows":
        return _windows_release(platform_version)
    major = _major(platform_version)
    if name.lower() == "macos":
        return f"macOS {major}".strip()
    return f"{name} {major}".strip()


def _platform_from_ua(user_agent: str) -> str:
    for label, pattern in UA_PLATFORMS:
        match = pattern.search(user_agent)
        if not match:
            continue
        # Windows friert im UA bei "NT 10.0" ein, macOS bei "10_15_7".
        # Ohne Client Hints ist die Version dort geraten, also weglassen.
        if label in ("Windows", "Linux", "macOS"):
            return label
        return f"{label} {match.group(1)}"
    return ""


def describe(client: dict | None) -> str:
    """Ein Satzbaustein wie 'Chrome 141 auf Windows 11, 2560x1440, Zeitzone Europe/Berlin'."""
    if not client:
        return ""
    user_agent = str(client.get("userAgent") or "")

    browser = _browser_from_brands(client.get("brands")) or _browser_from_ua(user_agent)
    platform = _platform_from_hints(
        str(client.get("platform") or ""), str(client.get("platformVersion") or "")
    ) or _platform_from_ua(user_agent)

    parts: list[str] = []
    if browser and platform:
        parts.append(f"{browser} auf {platform}")
    elif browser or platform:
        parts.append(browser or platform)

    if client.get("mobile"):
        parts.append("Mobilgerät")
    screen = str(client.get("screen") or "").strip()
    if screen:
        parts.append(screen)
    timezone = str(client.get("timezone") or "").strip()
    if timezone:
        parts.append(f"Zeitzone {timezone}")

    return ", ".join(parts)
