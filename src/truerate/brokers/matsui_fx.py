from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord

BROKER_ID = "matsui_fx"
BROKER_NAME = "松井証券FX"
SOURCE_TEMPLATE = "https://www.matsui.co.jp/fx/market/past-swap/csv/swap_{year}.csv"
JST = ZoneInfo("Asia/Tokyo")

PAIR_MAP = {
    "米ドル/円": "USD/JPY",
    "ユーロ/円": "EUR/JPY",
    "ポンド/円": "GBP/JPY",
    "豪ドル/円": "AUD/JPY",
    "NZドル/円": "NZD/JPY",
    "カナダ/円": "CAD/JPY",
    "スイス/円": "CHF/JPY",
    "ランド/円": "ZAR/JPY",
    "トルコリラ/円": "TRY/JPY",
    "メキシコペソ/円": "MXN/JPY",
    "人民元/円": "CNH/JPY",
    "ポーランド/円": "PLN/JPY",
    "ハンガリー/円": "HUF/JPY",
    "ノルウェー/円": "NOK/JPY",
    "スウェーデン/円": "SEK/JPY",
    "ユーロ/米ドル": "EUR/USD",
    "ポンド/米ドル": "GBP/USD",
    "豪ドル/米ドル": "AUD/USD",
    "NZドル/米ドル": "NZD/USD",
    "米ドル/スイス": "USD/CHF",
    "ポンド/スイス": "GBP/CHF",
    "ユーロ/スイス": "EUR/CHF",
    "ユーロ/ポンド": "EUR/GBP",
    "ユーロ/豪ドル": "EUR/AUD",
    "ポンド/豪ドル": "GBP/AUD",
    "米ドル/カナダ": "USD/CAD",
    "豪ドル/カナダ": "AUD/CAD",
    "NZドル/カナダ": "NZD/CAD",
    "ユーロ/NZドル": "EUR/NZD",
    "豪ドル/NZドル": "AUD/NZD",
    "ポンド/NZドル": "GBP/NZD",
    "ノルウェー/スウェーデン": "NOK/SEK",
}


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_year_csv(
    text: str,
    *,
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = "fixture",
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    records: list[SwapRecord] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        pair = PAIR_MAP.get((row.get("通貨ペア") or "").strip())
        if not pair:
            continue

        try:
            trade_date = datetime.strptime((row.get("取引日") or "").strip(), "%Y/%m/%d").date()
        except ValueError:
            continue
        if trade_date > today_jst:
            continue

        sp_days_raw = _number(row.get("付与日数") or "")
        short_swap = _number(row.get("売(円)") or "")
        long_swap = _number(row.get("買(円)") or "")
        if sp_days_raw is None or short_swap is None or long_swap is None:
            continue

        effective_date = trade_date + timedelta(days=1)
        records.append(
            SwapRecord(
                broker=BROKER_ID,
                pair=pair,
                trade_date=trade_date,
                effective_date=effective_date,
                sp_days=int(sp_days_raw),
                long_swap_jpy=long_swap,
                short_swap_jpy=short_swap,
                unit=10_000,
                status="confirmed" if effective_date <= today_jst else "scheduled",
                source=source_url,
                fetched_at=fetched_at,
                swap_currency="JPY",
            )
        )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def collect_year(
    year: int,
    *,
    session: requests.Session | None = None,
    timeout: int = 45,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
    )
    url = SOURCE_TEMPLATE.format(year=year)
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    text = response.content.decode("cp932")
    return parse_year_csv(text, today_jst=today_jst, source_url=response.url)
