"""Kosten- und PT-Summen. Formeln stehen hier, Saetze in config/rates.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings

NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")

PHASES = ("concept", "operate")
PARTIES = ("scs", "cit")


@dataclass(frozen=True)
class Rates:
    scs_daily: float = 750.0
    cit_daily: float = 665.0
    overhead_pct: float = 15.44
    margin_pct: float = 5.0


def parse_number(text: object) -> float:
    raw = str(text or "").strip()
    if not raw:
        return 0.0
    match = NUMBER.search(raw.replace(" ", ""))
    if not match:
        return 0.0
    return float(match.group(0).replace(",", "."))


def money(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"{sign}{grouped},{frac} €"


def _scs_total(pt: float, material: float, rates: Rates) -> float:
    return pt * rates.scs_daily + material


def _cit_total(pt: float, material: float, rates: Rates) -> float:
    net = pt * rates.cit_daily
    with_overhead = net * (1 + rates.overhead_pct / 100)
    with_margin = with_overhead * (1 + rates.margin_pct / 100)
    return with_margin + material


def compute(values: dict[str, str], rates: Rates | None = None) -> dict[str, str]:
    """Eingaben normalisieren. Entfernte Felder werden verworfen."""
    out = dict(values)
    for key in (
        "concept_scs_total",
        "concept_cit_total",
        "operate_scs_total",
        "operate_cit_total",
        "benefit_quality",
        "benefit_strategy",
    ):
        out.pop(key, None)
    return out


@lru_cache
def load_rates(path: Path | None = None) -> Rates:
    settings = get_settings()
    target = path or settings.rates_path
    if not target.is_file():
        return Rates()
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return Rates(
        scs_daily=float(raw.get("scs_daily", 750)),
        cit_daily=float(raw.get("cit_daily", 665)),
        overhead_pct=float(raw.get("overhead_pct", 15.44)),
        margin_pct=float(raw.get("margin_pct", 5)),
    )
