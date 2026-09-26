from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "gaitame_com"
BROKER_NAME = "外為どっとコム"
JST = ZoneInfo("Asia/Tokyo")

CALENDAR_URL = "https://www.gaitame.com/service/fx/swap-cal.html"
CSV_URL_TEMPLATE = "https://www.gaitame.com/products/nextneo/csv/{year:04d}{month:02d}.csv"

# The official calendar publishes 10 Lots: 10,000 currency for standard pairs,
# but 100,000 currency for HUF/JPY (and suspended RUB/JPY).
DEFAULT_UNIT = 10_000
PAIR_UNITS = {"HUF/JPY": 100_000}

# RUB/JPY has been unavailable for new orders since 2022-03-23.
EXCLUDED_PAIRS = {"RUB/JPY"}

PAIR_NAME_MAP = {
    "米ドル/円": "USD/JPY",
    "ユーロ/円": "EUR/JPY",
    "ユーロ/米ドル": "EUR/USD",
    "豪ドル/円": "AUD/JPY",
    "ポンド/円": "GBP/JPY",
    "NZドル/円": "NZD/JPY",
    "カナダ/円": "CAD/JPY",
    "カナダドル/円": "CAD/JPY",
    "スイス/円": "CHF/JPY",
    "スイスフラン/円": "CHF/JPY",
    "香港ドル/円": "HKD/JPY",
    "ポンド/米ドル": "GBP/USD",
    "米ドル/スイス": "USD/CHF",
    "米ドル/スイスフラン": "USD/CHF",
    "南アランド/円": "ZAR/JPY",
    "南アフリカランド/円": "ZAR/JPY",
    "豪ドル/米ドル": "AUD/USD",
    "NZドル/米ドル": "NZD/USD",
    "ユーロ/豪ドル": "EUR/AUD",
    "トルコ/円": "TRY/JPY",
    "トルコリラ/円": "TRY/JPY",
    "人民元/円": "CNH/JPY",
    "ノルウェー/円": "NOK/JPY",
    "ノルウェークローネ/円": "NOK/JPY",
    "スウェーデン/円": "SEK/JPY",
    "スウェーデンクローナ/円": "SEK/JPY",
    "メキシコペソ/円": "MXN/JPY",
    "ポンド/豪ドル": "GBP/AUD",
    "ユーロ/ポンド": "EUR/GBP",
    "米ドル/カナダ": "USD/CAD",
    "米ドル/カナダドル": "USD/CAD",
    "豪ドル/カナダ": "AUD/CAD",
    "豪ドル/カナダドル": "AUD/CAD",
    "ユーロ/NZドル": "EUR/NZD",
    "豪ドル/NZドル": "AUD/NZD",
    "米ドル/トルコ": "USD/TRY",
    "米ドル/トルコリラ": "USD/TRY",
    "ユーロ/トルコ": "EUR/TRY",
    "ユーロ/トルコリラ": "EUR/TRY",
    "SGドル/円": "SGD/JPY",
    "シンガポールドル/円": "SGD/JPY",
    "露ルーブル/円": "RUB/JPY",
    "ポンド/トルコリラ": "GBP/TRY",
    "スイス/トルコリラ": "CHF/TRY",
    "スイスフラン/トルコリラ": "CHF/TRY",
    "米ドル/南アランド": "USD/ZAR",
    "米ドル/南アフリカランド": "USD/ZAR",
    "スイス/南アランド": "CHF/ZAR",
    "スイスフラン/南アフリカランド": "CHF/ZAR",
    "米ドル/メキシコペソ": "USD/MXN",
    "スイス/メキシコペソ": "CHF/MXN",
    "スイスフラン/メキシコペソ": "CHF/MXN",
    "ユーロ/スイスフラン": "EUR/CHF",
    "ポンド/スイスフラン": "GBP/CHF",
    "米ドル/人民元": "USD/CNH",
    "ハンガリー/円": "HUF/JPY",
    "ハンガリーフォリント/円": "HUF/JPY",
    "チェココルナ/円": "CZK/JPY",
    "ポーランドズロチ/円": "PLN/JPY",
}

DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})")


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


def parse_month_csv(
    text: str,
    year: int,
    month: int,
    *,
    source_url: str | None = None,
    fetched_at: str | None = None,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    """Parse one official 外為どっとコム monthly swap CSV."""
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if source_url is None:
        source_url = CSV_URL_TEMPLATE.format(year=year, month=month)

    rows = list(csv.reader(io.StringIO(text, newline="")))
    if len(rows) < 3:
        return []

    pair_header = rows[0]
    pair_columns: list[tuple[int, str]] = []
    for offset in range(1, len(pair_header), 3):
        raw_name = pair_header[offset].strip() if offset < len(pair_header) else ""
        pair = PAIR_NAME_MAP.get(raw_name)
        if pair and pair not in EXCLUDED_PAIRS:
            pair_columns.append((offset, pair))

    records: list[SwapRecord] = []
    for row in rows[2:]:
        if not row:
            continue
        match = DATE_RE.search(row[0])
        if not match:
            continue

        row_month = int(match.group(1))
        day = int(match.group(2))
        if row_month != month:
            continue

        trade_date = date(year, month, day)
        effective_date = next_business_day_after(trade_date)

        for offset, pair in pair_columns:
            if offset + 2 >= len(row):
                continue
            sp_days_value = _number(row[offset])
            if sp_days_value is None:
                continue
            sp_days = int(sp_days_value)
            long_swap = _number(row[offset + 1])
            short_swap = _number(row[offset + 2])
            amounts_present = long_swap is not None and short_swap is not None
            status = (
                "confirmed"
                if amounts_present and effective_date <= today_jst
                else "scheduled"
            )

            records.append(
                SwapRecord(
                    broker=BROKER_ID,
                    pair=pair,
                    trade_date=trade_date,
                    effective_date=effective_date,
                    sp_days=sp_days,
                    long_swap_jpy=long_swap,
                    short_swap_jpy=short_swap,
                    unit=PAIR_UNITS.get(pair, DEFAULT_UNIT),
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
    url = CSV_URL_TEMPLATE.format(year=year, month=month)
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    text = response.content.decode("cp932")
    return parse_month_csv(
        text,
        year,
        month,
        source_url=response.url,
        today_jst=today_jst,
    )
