"""Websuche fuer aehnliche Loesungen und Risiken. Ausfall ist leer.

DuckDuckGo Instant Answer, danach HTML-Treffer. Timeout kurz. Fehler schlucken.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote, urlparse

import httpx

from app.config import get_settings

log = logging.getLogger("triage.websearch")

HEADERS = {"User-Agent": "CRITR-Triage/1.0"}
UDDG = re.compile(r"uddg=([^&\"]+)")
TITLE = re.compile(r'class="result__a"[^>]*>([^<]+)', re.I)


def search(query: str, limit: int = 3) -> list[dict]:
    raw = " ".join(str(query or "").split())[:120]
    if not raw or not get_settings().web_search_enabled:
        return []
    hits = _instant(raw, limit)
    if len(hits) < limit:
        for item in _html(raw, limit):
            if item["url"] in {h["url"] for h in hits}:
                continue
            hits.append(item)
            if len(hits) >= limit:
                break
    return hits[:limit]


def search_risks(title: str, description: str, limit: int = 4) -> list[dict]:
    head = " ".join(str(title or "").split())
    if len(head) < 12:
        head = " ".join(str(description or "").split())[:90]
    if not head:
        return []
    return search(f"{head} Risiken Change Einführung Akzeptanz", limit=limit)


def _effort_head(title: str, description: str) -> str:
    head = " ".join(str(title or "").split())
    if len(head) >= 8:
        return head[:90]
    blob = " ".join(str(description or "").split())
    if not blob:
        return head
    # Erste inhaltliche Phrase aus der Beschreibung, nicht den ganzen Absatz.
    for sep in (". ", "! ", "? ", "; "):
        if sep in blob:
            blob = blob.split(sep, 1)[0].strip()
            break
    return (head + " " + blob).strip()[:90]


def search_effort(title: str, description: str, limit: int = 4) -> list[dict]:
    """Ähnliche Projekte inkl. Dauer/Aufwand — ohne fest verdrahtete Projektnamen."""
    head = _effort_head(title, description)
    if not head:
        return []
    queries = (
        f"{head} Projekt Dauer Monate Fallstudie",
        f"{head} implementation timeline months case study",
        f"{head} Aufwand Personentage Wochen Monate",
    )
    primary: list[dict] = []
    seen: set[str] = set()
    for query in queries:
        for hit in search(query, limit=max(2, limit)):
            url = str(hit.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            primary.append(hit)
            if len(primary) >= limit:
                return primary[:limit]
    return primary[:limit]


def hits_block(hits: list[dict] | None, heading: str = "Webrecherche") -> str:
    lines: list[str] = []
    for hit in hits or []:
        title = " ".join(str(hit.get("title") or "").split())
        snippet = " ".join(str(hit.get("snippet") or "").split())
        line = " — ".join(part for part in (title, snippet) if part)
        if line:
            lines.append(f"- {line[:280]}")
    if not lines:
        return ""
    return f"{heading}:\n" + "\n".join(lines)


def first_snippet(hits: list[dict] | None) -> str:
    for hit in hits or []:
        text = " ".join(str(hit.get("snippet") or hit.get("title") or "").split())
        if text:
            return text[:220]
    return ""


def _instant(query: str, limit: int) -> list[dict]:
    try:
        response = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers=HEADERS,
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as err:
        log.info("websearch instant fehlgeschlagen: %s", err)
        return []
    out: list[dict] = []
    abstract = str(data.get("AbstractText") or "").strip()
    url = str(data.get("AbstractURL") or "").strip()
    heading = str(data.get("Heading") or "").strip()
    if abstract and url and _public_url(url):
        out.append({"title": heading or abstract[:80], "url": url, "snippet": abstract[:240]})
    for item in _flatten_topics(data.get("RelatedTopics") or []):
        if len(out) >= limit:
            break
        if item["url"] in {h["url"] for h in out}:
            continue
        out.append(item)
    return out


def _flatten_topics(items: list) -> list[dict]:
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("Topics"):
            out.extend(_flatten_topics(item["Topics"]))
            continue
        url = str(item.get("FirstURL") or "").strip()
        text = str(item.get("Text") or "").strip()
        if url and text and _public_url(url):
            out.append({"title": text[:80], "url": url, "snippet": text[:240]})
    return out


def _html(query: str, limit: int) -> list[dict]:
    try:
        response = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=8,
        )
        response.raise_for_status()
        body = response.text
    except httpx.HTTPError as err:
        log.info("websearch html fehlgeschlagen: %s", err)
        return []
    out: list[dict] = []
    titles = TITLE.findall(body)
    urls = [unquote(u) for u in UDDG.findall(body)]
    for index, url in enumerate(urls):
        if not _public_url(url):
            continue
        title = titles[index].strip() if index < len(titles) else url
        if url in {h["url"] for h in out}:
            continue
        out.append({"title": title[:80], "url": url, "snippet": title[:240]})
        if len(out) >= limit:
            break
    return out


def _public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1"}:
        return False
    return "." in host
