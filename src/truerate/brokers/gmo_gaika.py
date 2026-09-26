from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "gmo_gaika"
BROKER_NAME = "GMO外貨"
BASE_URL = "https://sec.gaikaex.com/gaikaex/mark/swap/calendar.php"
UNIT = 10_000
PAIR_RE = re.compile(r"\b([A-Z]{3})\s*/\s*([A-Z]{3})\b")
DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
JST = ZoneInfo("Asia/Tokyo")


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


def _record_quality(record: SwapRecord) -> tuple[int, int]:
    has_amounts = int(record.long_swap_jpy is not None and record.short_swap_jpy is not None)
    is_confirmed = int(record.status == "confirmed")
    return has_amounts, is_confirmed


def parse_calendar_html(
    html: str,
    year: int,
    month: int,
    *,
    source_url: str = BASE_URL,
    fetched_at: str | None = None,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    """Parse one GMO Gaika monthly swap calendar.

    GMO's calendar labels rows with a Japanese "trade date". The actual cash
    balance is updated after the NY close, which is the following calendar day
    in Japan. TrueRate therefore stores both dates and uses trade_date + 1 day
    as effective_date.

    A populated amount is only treated as confirmed once effective_date has
    arrived in JST. Future populated values remain scheduled because GMO notes
    that pre-credit values can change.
    """
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()

    soup = BeautifulSoup(html, "html.parser")
    records: dict[tuple[str, date], SwapRecord] = {}

    for table in soup.find_all("table"):
        table_text = table.get_text(" ", strip=True)
        if "取引日" not in table_text:
            continue

        pairs: list[str] = []
        for header in table.find_all("th"):
            match = PAIR_RE.search(header.get_text(" ", strip=True))
            if match:
                pair = f"{match.group(1)}/{match.group(2)}"
                if pair not in pairs:
                    pairs.append(pair)

        if not pairs:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if not cells:
                continue

            cell_text = [cell.get_text(" ", strip=True) for cell in cells]
            date_match = DATE_RE.search(cell_text[0])
            if not date_match:
                continue

            row_month = int(date_match.group(1))
            day = int(date_match.group(2))
            if row_month != month:
                continue

            values = cell_text[1:]
            required = len(pairs) * 3
            if len(values) < required:
                continue

            trade_date = date(year, month, day)
            effective_date = next_business_day_after(trade_date)

            for index, pair in enumerate(pairs):
                offset = index * 3
                sp_days = _integer(values[offset])
                long_swap = _number(values[offset + 1])
                short_swap = _number(values[offset + 2])
                if sp_days is None:
                    continue

                amounts_present = long_swap is not None and short_swap is not None
                status = (
                    "confirmed"
                    if amounts_present and effective_date <= today_jst
                    else "scheduled"
                )
                record = SwapRecord(
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
                key = (pair, trade_date)
                current = records.get(key)
                if current is None or _record_quality(record) > _record_quality(current):
                    records[key] = record

    return sorted(records.values(), key=lambda item: (item.pair, item.trade_date))


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
            "Referer": "https://sec.gaikaex.com/gaikaex/mark/swap/",
        }
    )
    response = client.get(
        BASE_URL,
        params={"date": f"{year:04d}{month:02d}"},
        timeout=timeout,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return parse_calendar_html(
        response.text,
        year,
        month,
        source_url=response.url,
        today_jst=today_jst,
    )


def iter_months(start: date, end: date) -> Iterable[tuple[int, int]]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
