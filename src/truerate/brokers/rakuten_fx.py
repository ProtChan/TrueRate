from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "rakuten_fx"
BROKER_NAME = "楽天FX"
JST = ZoneInfo("Asia/Tokyo")
SOURCE_URL = "https://www.rakuten-sec.co.jp/web/fx/RateData/SwapData.dat"

# The official page JavaScript maps SwapData.dat row indexes 2..39
# directly to the corresponding table cells.
PAIR_BY_ROW_INDEX = {
    2: "USD/JPY",
    3: "EUR/JPY",
    4: "GBP/JPY",
    5: "AUD/JPY",
    6: "EUR/USD",
    7: "GBP/USD",
    8: "AUD/USD",
    9: "MXN/JPY",
    10: "NZD/JPY",
    11: "ZAR/JPY",
    12: "CAD/JPY",
    13: "CHF/JPY",
    14: "TRY/JPY",
    15: "CNH/JPY",
    16: "NZD/USD",
    17: "USD/CAD",
    18: "USD/CHF",
    19: "GBP/CHF",
    20: "EUR/GBP",
    21: "EUR/CHF",
    22: "AUD/CHF",
    23: "NZD/CHF",
    24: "AUD/NZD",
    25: "HKD/JPY",
    26: "SGD/JPY",
    27: "NOK/JPY",
    28: "EUR/AUD",
    29: "GBP/AUD",
    30: "HUF/JPY",
    31: "SEK/JPY",
    32: "PLN/JPY",
    33: "CZK/JPY",
    34: "CAD/CHF",
    35: "NOK/SEK",
    36: "AUD/CAD",
    37: "NZD/CAD",
    38: "CNH/HKD",
    39: "USD/HKD",
}


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_swap_data(
    text: str,
    *,
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = SOURCE_URL,
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    lines = text.splitlines()
    records: list[SwapRecord] = []

    for row_index, pair in PAIR_BY_ROW_INDEX.items():
        if row_index >= len(lines):
            continue
        cells = lines[row_index].split("\t")
        if len(cells) < 4:
            continue

        short_swap = _number(cells[1])
        long_swap = _number(cells[2])
        date_text = cells[3].strip()
        if len(date_text) != 8 or not date_text.isdigit():
            continue

        trade_date = datetime.strptime(date_text, "%Y%m%d").date()
        effective_date = next_business_day_after(trade_date)
        quote = pair.split("/", 1)[1]
        amounts_present = short_swap is not None and long_swap is not None

        records.append(
            SwapRecord(
                broker=BROKER_ID,
                pair=pair,
                trade_date=trade_date,
                effective_date=effective_date,
                # The public latest-value feed exposes the swap amount but not
                # the separate calendar day-count field.
                sp_days=0,
                long_swap_jpy=long_swap,
                short_swap_jpy=short_swap,
                # Rakuten states the displayed swap is per 10,000 units.
                unit=10_000,
                status=(
                    "confirmed"
                    if amounts_present and effective_date <= today_jst
                    else "scheduled"
                ),
                source=source_url,
                fetched_at=fetched_at,
                swap_currency=quote,
            )
        )

    return sorted(records, key=lambda item: item.pair)


def collect_recent(
    *,
    session: requests.Session | None = None,
    timeout: int = 30,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/153.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.rakuten-sec.co.jp/web/fx/spread_swap/",
        }
    )
    response = client.get(SOURCE_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return parse_swap_data(
        response.text,
        today_jst=today_jst,
        source_url=response.url,
    )
