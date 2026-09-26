from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from truerate.brokers.click365 import CROSS_PAIRS, JPY_PAIRS, PAIR_UNITS
from truerate.series import BROKERS

TFX_MARGIN_URL_TEMPLATE = "https://www.tfx.co.jp/mkinfo/data/{yyyymmdd}fxmargin.csv"
OANDA_NY_MARGIN_URL = "https://www.oanda.jp/fx/ny4/retail-lineup"

# Domestic retail OTC FX products in this project use the 25x retail basis.
# Keep this broker-specific so exceptions can be changed without touching the UI.
OTC_MARGIN_RATES = {
    broker_id: 0.04
    for broker_id in BROKERS
    if broker_id != "click365"
}

# Current individual-account exceptions published by the brokers.
OTC_PAIR_MARGIN_RATES = {
    "sbi_fx": {
        "BRL/JPY": 0.10,
        "RUB/JPY": 0.33,
    },
    "minfx": {
        "RUB/JPY": 0.10,
    },
    "lightfx": {
        "RUB/JPY": 0.10,
    },
}


def _candidate_publication_mondays(today: date) -> list[date]:
    # TFX publishes the amount for the following applicable week.
    # Mon-Fri: use the file published one week before the current Monday.
    # Weekend: use the file from the just-finished week's Monday for next week.
    if today.weekday() <= 4:
        applicable_monday = today - timedelta(days=today.weekday())
    else:
        applicable_monday = today + timedelta(days=(7 - today.weekday()))
    first = applicable_monday - timedelta(days=7)
    return [first - timedelta(days=7 * offset) for offset in range(5)]


def parse_click365_margin_csv(text: str, *, source_url: str) -> dict:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2:
        raise ValueError("Click365 margin CSV is missing its effective date row")

    effective_start = date.fromisoformat(
        f"{rows[0][0][0:4]}-{rows[0][0][4:6]}-{rows[0][0][6:8]}"
    )
    effective_end = date.fromisoformat(
        f"{rows[0][1][0:4]}-{rows[0][1][4:6]}-{rows[0][1][6:8]}"
    )

    valid_pairs = set(JPY_PAIRS) | set(CROSS_PAIRS)
    per_pair_jpy: dict[str, float] = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        pair = row[0].strip().upper()
        if pair not in valid_pairs:
            continue
        try:
            amount = float(row[1].replace(",", "").strip())
        except ValueError:
            continue
        contract_unit = PAIR_UNITS.get(pair, 10_000)
        per_pair_jpy[pair] = round(amount * (10_000 / contract_unit), 4)

    if not per_pair_jpy:
        raise ValueError("Click365 margin CSV contained no standard currency pairs")

    return {
        "source": source_url,
        "effective_start": effective_start.isoformat(),
        "effective_end": effective_end.isoformat(),
        "normalized_unit": 10_000,
        "per_pair_jpy": per_pair_jpy,
    }


def fetch_click365_margin_schedule(
    today: date,
    *,
    session: requests.Session | None = None,
    timeout: int = 30,
) -> dict:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
    )

    last_error: Exception | None = None
    for publication_day in _candidate_publication_mondays(today):
        url = TFX_MARGIN_URL_TEMPLATE.format(yyyymmdd=publication_day.strftime("%Y%m%d"))
        try:
            response = client.get(url, timeout=timeout)
            if response.status_code != 200:
                continue
            return parse_click365_margin_csv(
                response.content.decode("cp932"),
                source_url=response.url,
            )
        except Exception as exc:
            last_error = exc

    raise RuntimeError("Could not fetch an applicable Click365 retail margin schedule") from last_error


def fetch_oanda_ny_margin_rates(
    *,
    session: requests.Session | None = None,
    timeout: int = 30,
) -> dict[str, float]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
    )
    response = client.get(OANDA_NY_MARGIN_URL, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rates: dict[str, float] = {}
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if len(cells) < 3 or "/" not in cells[0]:
            continue
        pair = cells[0].strip().upper()
        rate_text = cells[2].strip().replace("%", "")
        try:
            rate = float(rate_text) / 100
        except ValueError:
            continue
        rates[pair] = rate
    if len(rates) < 60:
        raise ValueError("OANDA NY retail lineup returned fewer than 60 margin rates")
    return rates


def build_margin_requirements(today: date) -> dict:
    pair_rates = {broker: dict(rates) for broker, rates in OTC_PAIR_MARGIN_RATES.items()}
    try:
        pair_rates["oanda_ny"] = fetch_oanda_ny_margin_rates()
    except Exception:
        pair_rates.setdefault("oanda_ny", {})

    return {
        "method": (
            "OTC retail legs use broker-specific 25x margin rates; "
            "Click365 uses the applicable TFX retail margin reference amount."
        ),
        "default_otc_margin_rate": 0.04,
        "margin_rate_by_broker": OTC_MARGIN_RATES,
        "margin_rate_by_broker_pair": pair_rates,
        "click365": fetch_click365_margin_schedule(today),
    }
