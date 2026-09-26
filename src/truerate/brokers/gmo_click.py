from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from truerate.models import SwapRecord

BROKER_ID = "gmo_click"
BROKER_NAME = "GMOクリック証券"
BASE_URL = "https://www.click-sec.com/corp/guide/fxneo/swplog/"
JST = ZoneInfo("Asia/Tokyo")

STANDARD_PAIRS = (
    "USD/JPY",
    "EUR/JPY",
    "GBP/JPY",
    "AUD/JPY",
    "NZD/JPY",
    "CAD/JPY",
    "CHF/JPY",
    "TRY/JPY",
    "CZK/JPY",
    "PLN/JPY",
    "HUF/JPY",
    "ZAR/JPY",
    "MXN/JPY",
    "EUR/USD",
    "GBP/USD",
    "AUD/USD",
    "NZD/USD",
    "EUR/GBP",
    "EUR/AUD",
    "GBP/AUD",
    "AUD/NZD",
    "EUR/CHF",
    "GBP/CHF",
    "USD/CHF",
)

PAIR_UNITS = {
    pair: (100_000 if pair in {"HUF/JPY", "ZAR/JPY", "MXN/JPY"} else 10_000)
    for pair in STANDARD_PAIRS
}

# Four standard pairs were added to FXneo on 2025-03-17. Do not request or
# preserve data before the product actually existed.
PAIR_START_DATES = {
    "CZK/JPY": date(2025, 3, 17),
    "PLN/JPY": date(2025, 3, 17),
    "HUF/JPY": date(2025, 3, 17),
    "AUD/NZD": date(2025, 3, 17),
}

DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")


def _number(text: str) -> float | None:
    cleaned = (
        text.replace(",", "")
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


def _integer(text: str) -> int | None:
    value = _number(text)
    if value is None:
        return None
    return int(value)


def parse_calendar_html(
    html: str,
    year: int,
    month: int,
    pair: str,
    *,
    source_url: str = BASE_URL,
    fetched_at: str | None = None,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    """Parse one GMO Click FXneo pair/month calendar.

    GMO Click labels each row with the date whose New York close causes the
    swap to arise and be reflected in account equity. TrueRate keeps that
    source date as trade_date and places the cashflow in the next JST calendar
    day's index using effective_date = trade_date + 1 day.
    """
    pair = pair.upper()
    if pair not in PAIR_UNITS:
        raise ValueError(f"unsupported GMO Click standard pair: {pair}")

    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()

    soup = BeautifulSoup(html, "html.parser")
    records: list[SwapRecord] = []

    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if not all(label in text for label in ("取引日", "売Swap", "買Swap", "付与日数")):
            continue

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 4:
                continue
            values = [cell.get_text(" ", strip=True) for cell in cells]
            match = DATE_RE.search(values[0])
            if not match:
                continue

            row_month = int(match.group(1))
            day = int(match.group(2))
            if row_month != month:
                continue

            short_swap = _number(values[1])
            long_swap = _number(values[2])
            sp_days = _integer(values[3])
            if sp_days is None:
                continue

            trade_date = date(year, month, day)
            effective_date = trade_date + timedelta(days=1)
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
                    unit=PAIR_UNITS[pair],
                    status=status,
                    source=source_url,
                    fetched_at=fetched_at,
                )
            )

    return sorted(records, key=lambda item: item.trade_date)


def collect_pair_month(
    year: int,
    month: int,
    pair: str,
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
            "Referer": "https://www.click-sec.com/corp/guide/fxneo/",
        }
    )
    response = client.get(
        BASE_URL,
        params={
            "year": f"{year:04d}",
            "month": f"{month:02d}",
            "pare": pair.replace("/", ""),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return parse_calendar_html(
        response.text,
        year,
        month,
        pair,
        source_url=response.url,
        today_jst=today_jst,
    )


def collect_month(
    year: int,
    month: int,
    *,
    pairs: Iterable[str] = STANDARD_PAIRS,
    session: requests.Session | None = None,
    timeout: int = 30,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    records: list[SwapRecord] = []
    for pair in pairs:
        start_date = PAIR_START_DATES.get(pair)
        month_end = date(year, month, 28) + timedelta(days=4)
        month_end = month_end - timedelta(days=month_end.day)
        if start_date is not None and month_end < start_date:
            continue

        pair_records = collect_pair_month(
            year,
            month,
            pair,
            session=client,
            timeout=timeout,
            today_jst=today_jst,
        )
        if start_date is not None:
            pair_records = [record for record in pair_records if record.trade_date >= start_date]
        records.extend(pair_records)
    return sorted(records, key=lambda item: (item.pair, item.trade_date))
