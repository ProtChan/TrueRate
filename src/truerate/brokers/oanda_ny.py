from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "oanda_ny"
BROKER_NAME = "OANDA Japan NY"
JST = ZoneInfo("Asia/Tokyo")
SOURCE_TEMPLATE = (
    "https://www.oanda.jp/service/swappoint/"
    "swap_ny4_{pair_code}_{yyyymm}.json"
)

PAIRS = (
    "USD/JPY", "EUR/JPY", "AUD/JPY", "GBP/JPY", "NZD/JPY", "CAD/JPY",
    "CHF/JPY", "ZAR/JPY", "EUR/USD", "GBP/USD", "NZD/USD", "AUD/USD",
    "USD/CHF", "EUR/CHF", "GBP/CHF", "EUR/GBP", "AUD/NZD", "AUD/CAD",
    "AUD/CHF", "CAD/CHF", "EUR/AUD", "EUR/CAD", "EUR/DKK", "EUR/NOK",
    "EUR/NZD", "EUR/SEK", "GBP/AUD", "GBP/CAD", "GBP/NZD", "NZD/CAD",
    "NZD/CHF", "USD/CAD", "USD/DKK", "USD/NOK", "USD/SEK", "AUD/HKD",
    "AUD/SGD", "CAD/HKD", "CAD/SGD", "CHF/HKD", "CHF/ZAR", "EUR/CZK",
    "EUR/HKD", "EUR/HUF", "EUR/PLN", "EUR/SGD", "EUR/TRY", "EUR/ZAR",
    "GBP/HKD", "GBP/PLN", "GBP/SGD", "GBP/ZAR", "HKD/JPY", "NZD/HKD",
    "NZD/SGD", "SGD/CHF", "SGD/JPY", "TRY/JPY", "USD/CNH", "USD/CZK",
    "USD/HKD", "USD/HUF", "USD/MXN", "USD/PLN", "USD/SGD", "USD/THB",
    "USD/TRY", "USD/ZAR",
)

PAIR_UNITS = {
    "ZAR/JPY": 100_000,
    "HKD/JPY": 100_000,
}

DATE_RE = re.compile(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日")


def _number(value) -> float | None:
    if value is None:
        return None
    cleaned = str(value).replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_month_payload(
    payload: list[dict],
    *,
    year: int,
    month: int,
    pair: str,
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = "fixture",
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    records: list[SwapRecord] = []
    for item in payload:
        match = DATE_RE.search(str(item.get("date") or ""))
        if not match:
            continue
        item_month = int(match.group("month"))
        if item_month != month:
            continue
        try:
            trade_date = date(year, item_month, int(match.group("day")))
        except ValueError:
            continue

        long_swap = _number(item.get("buy"))
        short_swap = _number(item.get("sell"))
        sp_days = _number(item.get("days"))
        if sp_days is None:
            continue

        # Weekend placeholders are blank with zero days and carry no
        # economic cashflow. A blank buy/sell side on an actual swap row is
        # different: OANDA is not currently quoting that side.
        if long_swap is None and short_swap is None and int(sp_days) == 0:
            continue

        effective_date = next_business_day_after(trade_date)
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
                sp_days=int(sp_days),
                long_swap_jpy=long_swap,
                short_swap_jpy=short_swap,
                unit=PAIR_UNITS.get(pair, 10_000),
                status=status,
                source=source_url,
                fetched_at=fetched_at,
                swap_currency="JPY",
            )
        )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def collect_pair_month(
    year: int,
    month: int,
    pair: str,
    *,
    timeout: int = 30,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    pair_code = pair.replace("/", "").lower()
    url = SOURCE_TEMPLATE.format(pair_code=pair_code, yyyymm=f"{year:04d}{month:02d}")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.oanda.jp/fx/ny4/swap",
    }

    response = None
    for attempt in range(8):
        # OANDA's public calendar is pair/month scoped and rate-limited.
        # Pace the initial historical backfill rather than hammering the site.
        time.sleep(0.35)
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException:
            if attempt == 7:
                raise
            time.sleep(min(2 ** attempt, 20))
            continue

        if response.status_code == 404:
            return []
        if response.status_code != 429:
            response.raise_for_status()
            break

        retry_after = response.headers.get("Retry-After")
        try:
            wait = float(retry_after) if retry_after else 0.0
        except ValueError:
            wait = 0.0
        if wait <= 0:
            wait = min(2 ** attempt, 20)
        time.sleep(wait)
    else:
        raise RuntimeError(f"OANDA NY remained rate-limited: {url}")

    if response is None:
        raise RuntimeError(f"OANDA NY request produced no response: {url}")

    return parse_month_payload(
        response.json(),
        year=year,
        month=month,
        pair=pair,
        today_jst=today_jst,
        source_url=response.url,
    )


def collect_month(
    year: int,
    month: int,
    *,
    timeout: int = 30,
    today_jst: date | None = None,
    max_workers: int = 3,
) -> list[SwapRecord]:
    records: list[SwapRecord] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(
                collect_pair_month,
                year,
                month,
                pair,
                timeout=timeout,
                today_jst=today_jst,
            ): pair
            for pair in PAIRS
        }
        for future in as_completed(future_map):
            records.extend(future.result())

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))
