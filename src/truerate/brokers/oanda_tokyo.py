from __future__ import annotations

import csv
import io
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "oanda_tokyo"
BROKER_NAME = "OANDA Japan 東京サーバー"
SOURCE_URL = (
    "https://storage.googleapis.com/oanda-prod-asne1-oj-jp-hp/"
    "downloads/swaps/Tokyo-mt4-and-mt5swaps.csv"
)
JST = ZoneInfo("Asia/Tokyo")


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
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = SOURCE_URL,
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    records: list[SwapRecord] = []
    for row in csv.DictReader(io.StringIO(text)):
        pair = (row.get("Symbol") or "").strip().upper()
        if "/" not in pair:
            continue
        try:
            trade_date = date.fromisoformat((row.get("TradeDate") or "").strip())
        except ValueError:
            continue

        long_swap = _number(row.get("SwapLong") or "")
        short_swap = _number(row.get("SwapShort") or "")

        effective_date = next_business_day_after(trade_date)
        quote = pair.split("/", 1)[1]
        amounts_present = long_swap is not None and short_swap is not None
        if not amounts_present:
            status = "unavailable"
        elif effective_date <= today_jst:
            status = "confirmed"
        else:
            status = "scheduled"

        records.append(
            SwapRecord(
                broker=BROKER_ID,
                pair=pair,
                trade_date=trade_date,
                effective_date=effective_date,
                sp_days=0,
                long_swap_jpy=long_swap,
                short_swap_jpy=short_swap,
                unit=10_000,
                status=status,
                source=source_url,
                fetched_at=fetched_at,
                swap_currency=quote,
            )
        )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def collect_history(
    *,
    session: requests.Session | None = None,
    timeout: int = 90,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
    )
    response = client.get(SOURCE_URL, timeout=timeout)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig")
    return parse_history_csv(
        text,
        today_jst=today_jst,
        source_url=response.url,
    )
