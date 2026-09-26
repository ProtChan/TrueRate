from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "click365"
BROKER_NAME = "くりっく365"
SOURCE_URL = "https://www.tfx.co.jp/historical/fx/result"
JST = ZoneInfo("Asia/Tokyo")

JPY_PAIRS = (
    "USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/JPY", "CHF/JPY", "CAD/JPY",
    "NZD/JPY", "ZAR/JPY", "TRY/JPY", "NOK/JPY", "SEK/JPY", "HKD/JPY",
    "PLN/JPY", "MXN/JPY", "CNH/JPY", "HUF/JPY", "CZK/JPY",
)
CROSS_PAIRS = (
    "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/CAD", "GBP/CHF",
    "USD/CHF", "EUR/CHF", "EUR/AUD", "GBP/AUD", "EUR/GBP",
)
PAIR_UNITS = {
    "ZAR/JPY": 100_000,
    "HKD/JPY": 100_000,
    "NOK/JPY": 100_000,
    "SEK/JPY": 100_000,
    "MXN/JPY": 100_000,
    "HUF/JPY": 100_000,
    "CZK/JPY": 100_000,
}


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―", "－－－"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_summary_csv(
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

    rows = list(csv.reader(io.StringIO(text)))
    header_index = next(
        (i for i, row in enumerate(rows) if row and row[0].strip() == "商品名"),
        None,
    )
    if header_index is None:
        return []

    records: list[SwapRecord] = []
    valid_pairs = set(JPY_PAIRS) | set(CROSS_PAIRS)
    for row in rows[header_index + 1 :]:
        if len(row) < 4:
            continue
        pair = row[0].strip().upper()
        if pair not in valid_pairs:
            continue
        try:
            trade_date = datetime.strptime(row[2].strip(), "%Y/%m/%d").date()
        except ValueError:
            continue
        if trade_date > today_jst:
            continue

        swap = _number(row[3])
        if swap is None:
            swap = 0.0

        effective_date = next_business_day_after(trade_date)
        quote = pair.split("/", 1)[1]
        records.append(
            SwapRecord(
                broker=BROKER_ID,
                pair=pair,
                trade_date=trade_date,
                effective_date=effective_date,
                sp_days=0,
                long_swap_jpy=swap,
                short_swap_jpy=-swap,
                unit=PAIR_UNITS.get(pair, 10_000),
                status="confirmed" if effective_date <= today_jst else "scheduled",
                source=source_url,
                fetched_at=fetched_at,
                swap_currency=quote,
            )
        )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def _fetch_group(
    client: requests.Session,
    *,
    start: date,
    end: date,
    group_key: str,
    pairs: tuple[str, ...],
    timeout: int,
    today_jst: date | None,
) -> list[SwapRecord]:
    params: list[tuple[str, str]] = [
        ("HistoricalData[submit_type]", "csv"),
        ("HistoricalData[period_start_type]", "date"),
        ("HistoricalData[period_start][year]", str(start.year)),
        ("HistoricalData[period_start][month]", str(start.month)),
        ("HistoricalData[period_start][day]", str(start.day)),
        ("HistoricalData[period_end_type]", "date"),
        ("HistoricalData[period_end][year]", str(end.year)),
        ("HistoricalData[period_end][month]", str(end.month)),
        ("HistoricalData[period_end][day]", str(end.day)),
        ("HistoricalData[get_preference][]", "swap_point"),
    ]
    params.extend((group_key, pair) for pair in pairs)

    response = client.get(SOURCE_URL, params=params, timeout=timeout)
    response.raise_for_status()
    text = response.content.decode("cp932")
    return parse_summary_csv(
        text,
        today_jst=today_jst,
        source_url=response.url,
    )


def collect_period(
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    timeout: int = 60,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    if end < start:
        return []
    if (end - start).days > 366:
        raise ValueError("Click365 historical endpoint accepts at most about one year per request")

    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.tfx.co.jp/historical/fx/",
        }
    )

    records = _fetch_group(
        client,
        start=start,
        end=end,
        group_key="HistoricalData[product_type1][]",
        pairs=JPY_PAIRS,
        timeout=timeout,
        today_jst=today_jst,
    )
    records.extend(
        _fetch_group(
            client,
            start=start,
            end=end,
            group_key="HistoricalData[product_type2][]",
            pairs=CROSS_PAIRS,
            timeout=timeout,
            today_jst=today_jst,
        )
    )
    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))
