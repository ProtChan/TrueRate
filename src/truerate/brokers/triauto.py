from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "triauto"
BROKER_NAME = "トライオートFX"
UNIT = 10_000
JST = ZoneInfo("Asia/Tokyo")

CALENDAR_URL = "https://www.invast.jp/triauto/swap-calendar/"
MONTH_SWAP_URL = "https://www.invast.jp/triauto/service/summary/swap_csv/dailyswap.php"
ADD_DAYS_URL = "https://www.invast.jp/swappoint/adddays/adddays.php"

# The public Triauto swap calendar currently exposes these 34 standard pairs.
# Internal *_AP rows and legacy/inactive rows returned by the backend are ignored.
STANDARD_PAIRS = (
    "USD/JPY",
    "EUR/JPY",
    "GBP/JPY",
    "AUD/JPY",
    "NZD/JPY",
    "CAD/JPY",
    "CHF/JPY",
    "CNH/JPY",
    "NOK/JPY",
    "CZK/JPY",
    "PLN/JPY",
    "HUF/JPY",
    "TRY/JPY",
    "MXN/JPY",
    "ZAR/JPY",
    "EUR/USD",
    "GBP/USD",
    "AUD/USD",
    "NZD/USD",
    "USD/CAD",
    "AUD/CAD",
    "NZD/CAD",
    "USD/CHF",
    "USD/SGD",
    "EUR/AUD",
    "EUR/GBP",
    "EUR/PLN",
    "CHF/TRY",
    "CHF/MXN",
    "CHF/ZAR",
    "CHF/HUF",
    "AUD/NZD",
    "NOK/SEK",
    "NOK/ZAR",
)
STANDARD_PAIR_SET = set(STANDARD_PAIRS)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    cleaned = (
        str(value)
        .replace(",", "")
        .replace("円", "")
        .replace("−", "-")
        .replace("－", "-")
        .strip()
    )
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _date_key_to_date(key: str) -> date | None:
    if len(key) != 8 or not key.isdigit():
        return None
    try:
        return date(int(key[:4]), int(key[4:6]), int(key[6:8]))
    except ValueError:
        return None


def parse_month_payload(
    daily_swap: dict[str, Any],
    add_days: dict[str, Any],
    year: int,
    month: int,
    *,
    source_url: str = MONTH_SWAP_URL,
    fetched_at: str | None = None,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    """Normalize one month of Triauto's official swap-calendar backend.

    The monthly swap endpoint stores each pair as:
        [display_pair, sell_swap, buy_swap]

    The add-days endpoint stores:
        [display_date, display_pair, number_of_swap_days]

    TrueRate keeps the source transaction date but applies the cashflow to the
    following JST calendar day, matching the site's common D+1 index rule.
    """
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()

    records: list[SwapRecord] = []

    for key, pair_map in daily_swap.items():
        trade_date = _date_key_to_date(str(key))
        if trade_date is None or trade_date.year != year or trade_date.month != month:
            continue
        if not isinstance(pair_map, dict):
            continue

        days_for_date = add_days.get(str(key), {})
        if not isinstance(days_for_date, dict):
            days_for_date = {}

        for raw_pair_key, values in pair_map.items():
            if not isinstance(values, (list, tuple)) or len(values) < 3:
                continue

            pair = str(values[0]).replace("_AP", "").upper()
            if "_AP" in str(values[0]).upper() or pair not in STANDARD_PAIR_SET:
                continue

            short_swap = _number(values[1])
            long_swap = _number(values[2])
            if short_swap is None or long_swap is None:
                continue

            # A 0/0 backend row is used for inactive/not-applicable instruments
            # on some historical dates. It carries no cashflow and should not
            # establish an artificial history start date.
            if short_swap == 0 and long_swap == 0:
                continue

            raw_days = days_for_date.get(raw_pair_key)
            if raw_days is None:
                compact_key = pair.replace("/", "")
                raw_days = days_for_date.get(compact_key)
            if not isinstance(raw_days, (list, tuple)) or len(raw_days) < 3:
                continue

            sp_days_value = _number(raw_days[2])
            if sp_days_value is None:
                continue
            sp_days = int(sp_days_value)

            effective_date = next_business_day_after(trade_date)
            status = "confirmed" if effective_date <= today_jst else "scheduled"

            records.append(
                SwapRecord(
                    broker=BROKER_ID,
                    pair=pair,
                    trade_date=trade_date,
                    effective_date=effective_date,
                    sp_days=sp_days,
                    long_swap_jpy=long_swap,
                    short_swap_jpy=short_swap,
                    unit=UNIT,
                    status=status,
                    source=source_url,
                    fetched_at=fetched_at,
                )
            )

    return sorted(records, key=lambda item: (item.pair, item.trade_date))


def collect_month(
    year: int,
    month: int,
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
            "Referer": CALENDAR_URL,
        }
    )
    params = {"year": year, "month": month}

    swap_response = client.get(MONTH_SWAP_URL, params=params, timeout=timeout)
    swap_response.raise_for_status()
    add_days_response = client.get(ADD_DAYS_URL, params=params, timeout=timeout)
    add_days_response.raise_for_status()

    source_url = swap_response.url
    daily_swap = swap_response.json()
    add_days = add_days_response.json()
    if not isinstance(daily_swap, dict) or not isinstance(add_days, dict):
        raise RuntimeError("Unexpected Triauto monthly API payload.")

    return parse_month_payload(
        daily_swap,
        add_days,
        year,
        month,
        source_url=source_url,
        today_jst=today_jst,
    )
