from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "jfx"
BROKER_NAME = "JFX MATRIX TRADER"
SOURCE_URL = "https://info.jfx.co.jp/jfxapl/updateapl/matrix_swap.csv"
JST = ZoneInfo("Asia/Tokyo")

DEFAULT_UNIT = 1_000
PAIR_UNITS = {
    "MXN/JPY": 10_000,
    "NOK/JPY": 10_000,
    "SEK/JPY": 10_000,
    "CNH/JPY": 10_000,
    "CZK/JPY": 10_000,
    "THB/JPY": 10_000,
    "HUF/JPY": 100_000,
}


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_history_csv(
    text: str,
    *,
    start: date = date(2021, 1, 1),
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = SOURCE_URL,
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    rows = list(csv.reader(io.StringIO(text, newline="")))
    if len(rows) < 3:
        return []

    pair_columns: list[tuple[int, str]] = []
    header = rows[0]
    for column in range(1, len(header) - 1, 2):
        pair = header[column].strip()
        if not pair or pair.startswith("大口") or "/" not in pair:
            continue
        pair_columns.append((column, pair.upper()))

    parsed: dict[str, list[tuple[date, float | None, float | None]]] = {
        pair: [] for _, pair in pair_columns
    }
    for row in rows[2:]:
        if not row or not row[0].strip():
            continue
        try:
            trade_date = datetime.strptime(row[0].strip(), "%Y%m%d").date()
        except ValueError:
            continue
        if trade_date < start or trade_date > today_jst:
            continue

        for column, pair in pair_columns:
            sell = _number(row[column]) if column < len(row) else None
            buy = _number(row[column + 1]) if column + 1 < len(row) else None
            parsed[pair].append((trade_date, sell, buy))

    records: list[SwapRecord] = []
    for pair, values in parsed.items():
        active_dates = [
            trade_date
            for trade_date, sell, buy in values
            if (sell is not None and abs(sell) > 1e-12)
            or (buy is not None and abs(buy) > 1e-12)
        ]
        if not active_dates:
            continue
        active_start = min(active_dates)
        quote = pair.split("/", 1)[1]

        for trade_date, sell, buy in values:
            if trade_date < active_start or sell is None or buy is None:
                continue
            effective_date = next_business_day_after(trade_date)
            records.append(
                SwapRecord(
                    broker=BROKER_ID,
                    pair=pair,
                    trade_date=trade_date,
                    effective_date=effective_date,
                    sp_days=0,
                    long_swap_jpy=buy,
                    short_swap_jpy=sell,
                    unit=PAIR_UNITS.get(pair, DEFAULT_UNIT),
                    status="confirmed" if effective_date <= today_jst else "scheduled",
                    source=source_url,
                    fetched_at=fetched_at,
                    swap_currency=quote,
                )
            )

    return sorted(records, key=lambda item: (item.pair, item.trade_date))


def collect_history(
    *,
    start: date = date(2021, 1, 1),
    session: requests.Session | None = None,
    timeout: int = 45,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    client.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Language": "ja,en;q=0.8"})
    response = client.get(SOURCE_URL, timeout=timeout)
    response.raise_for_status()
    text = response.content.decode("cp932")
    return parse_history_csv(
        text,
        start=start,
        today_jst=today_jst,
        source_url=response.url,
    )
