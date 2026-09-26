from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from truerate.models import SwapRecord

BROKER_ID = "sbi_fx"
BROKER_NAME = "SBI FXトレード"
SOURCE_URL = "https://www.sbifxt.co.jp/fxtaccount/pc/SWHis?RICH=Y"
JST = ZoneInfo("Asia/Tokyo")

PAIRS = (
    "USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/JPY", "NZD/JPY", "CAD/JPY",
    "CHF/JPY", "ZAR/JPY", "TRY/JPY", "CNH/JPY", "KRW/JPY", "HKD/JPY",
    "RUB/JPY", "BRL/JPY", "PLN/JPY", "SEK/JPY", "NOK/JPY", "MXN/JPY",
    "SGD/JPY", "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD", "USD/CAD",
    "USD/CHF", "USD/CNH", "EUR/GBP", "EUR/AUD", "EUR/NZD", "EUR/CHF",
    "GBP/AUD", "GBP/CHF", "AUD/NZD", "AUD/CHF",
)
SPECIAL_100K = {"ZAR/JPY", "CNH/JPY", "HKD/JPY", "MXN/JPY", "RUB/JPY"}
KRW_BASE_UNITS = 1_000_000
DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_month_html(
    html: str,
    year: int,
    month: int,
    *,
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = SOURCE_URL,
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    soup = BeautifulSoup(html, "html.parser")
    records: list[SwapRecord] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        match = DATE_RE.search(cells[0].get_text(" ", strip=True))
        if not match:
            continue
        row_month = int(match.group(1))
        day = int(match.group(2))
        if row_month != month:
            continue
        try:
            trade_date = date(year, month, day)
        except ValueError:
            continue

        grouped: dict[str, list[str]] = {}
        for cell in cells[1:]:
            code = None
            for cls in cell.get("class", []):
                if cls.startswith("td_commodity_"):
                    code = cls.removeprefix("td_commodity_")
                    break
            if code:
                grouped.setdefault(code, []).append(cell.get_text(" ", strip=True))

        for code, values in grouped.items():
            if len(values) < 4 or len(code) != 6:
                continue
            pair = f"{code[:3]}/{code[3:]}"
            if pair not in PAIRS:
                continue

            sp_days_raw = _number(values[0])
            sell = _number(values[2])
            buy = _number(values[3])
            if sp_days_raw is None or sell is None or buy is None:
                continue

            if pair == "KRW/JPY":
                # SBI quotes KRW/JPY per 100 KRW. The history endpoint's
                # "10,000 currency units" therefore represents 1,000,000 KRW.
                multiplier = 1.0
                row_unit = KRW_BASE_UNITS
            elif pair in SPECIAL_100K:
                multiplier = 10.0
                row_unit = 100_000
            else:
                multiplier = 1.0
                row_unit = 10_000
            effective_date = trade_date + timedelta(days=1)
            records.append(
                SwapRecord(
                    broker=BROKER_ID,
                    pair=pair,
                    trade_date=trade_date,
                    effective_date=effective_date,
                    sp_days=int(sp_days_raw),
                    long_swap_jpy=buy * multiplier,
                    short_swap_jpy=sell * multiplier,
                    unit=row_unit,
                    status="confirmed" if effective_date <= today_jst else "scheduled",
                    source=source_url,
                    fetched_at=fetched_at,
                    swap_currency="JPY",
                )
            )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def _post_month(
    client: requests.Session,
    year: int,
    month: int,
    selected_pair: str,
    timeout: int,
) -> requests.Response:
    code = selected_pair.replace("/", "")
    response = client.post(
        SOURCE_URL,
        data={
            "YEAR": str(year),
            "MONTH": f"{month:02d}",
            "SELECTED_TERMINAL": "mobileTerminal",
            "SELECTED_CURRENCY_PAIR": code,
            "SELECTED_CURRENCY_UNIT": "tenThousandCurrencyUnit",
            "MAX_CURRENCY_PAIR": "34",
            "GUID": str(int(datetime.now().timestamp() * 1000)),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def collect_month(
    year: int,
    month: int,
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
            "Referer": "https://www.sbifxt.co.jp/market/swap_calendar.html",
        }
    )

    response = _post_month(client, year, month, "USD/JPY", timeout)
    records = parse_month_html(
        response.text,
        year,
        month,
        today_jst=today_jst,
        source_url=response.url,
    )
    if len({record.pair for record in records}) >= 20:
        return records

    merged = {(record.pair, record.trade_date): record for record in records}
    for pair in PAIRS:
        response = _post_month(client, year, month, pair, timeout)
        for record in parse_month_html(
            response.text,
            year,
            month,
            today_jst=today_jst,
            source_url=response.url,
        ):
            merged[(record.pair, record.trade_date)] = record

    return sorted(merged.values(), key=lambda item: (item.pair, item.trade_date))
