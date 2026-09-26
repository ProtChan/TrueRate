from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from pypdf import PdfReader

from truerate.models import SwapRecord

BROKER_ID = "fxbroadnet"
BROKER_NAME = "FXブロードネット"
SOURCE_TEMPLATE = "https://www.fxbroadnet.com/pdf/swap_calendar{year:04d}{month:02d}.pdf"
JST = ZoneInfo("Asia/Tokyo")

PAGE_PAIRS = (
    (
        "USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/JPY",
        "NZD/JPY", "CAD/JPY", "CHF/JPY", "ZAR/JPY",
    ),
    (
        "EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD",
        "USD/CAD", "USD/CHF", "EUR/GBP", "EUR/AUD",
    ),
    (
        "EUR/NZD", "EUR/CAD", "EUR/CHF", "GBP/AUD",
        "GBP/NZD", "GBP/CHF", "AUD/NZD", "AUD/CHF",
    ),
)
PAIR_UNITS = {"ZAR/JPY": 100_000}

ROW_RE = re.compile(
    r"^\s*(?P<month>\d{1,2})月(?P<day>\d{1,2})日\s*\([^)]+\)"
    r"(?:\s+(?P<settle_month>\d{1,2})月(?P<settle_day>\d{1,2})日\s*\([^)]+\))?"
    r"\s*(?P<values>.*)$"
)
TOKEN_RE = re.compile(r"(?<!\d)-?(?:\d[\d,]*)(?:\.\d+)?|(?<!\S)-(?!\S)")


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_page_text(
    text: str,
    *,
    year: int,
    month: int,
    page_index: int,
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = "fixture",
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    if page_index >= len(PAGE_PAIRS):
        return []

    pairs = PAGE_PAIRS[page_index]
    records: list[SwapRecord] = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        match = ROW_RE.match(line)
        if not match:
            continue
        if int(match.group("month")) != month:
            continue

        try:
            trade_date = date(year, month, int(match.group("day")))
        except ValueError:
            continue

        tokens = TOKEN_RE.findall(match.group("values"))
        needed = len(pairs) * 3
        if len(tokens) < needed:
            continue
        tokens = tokens[:needed]

        for index, pair in enumerate(pairs):
            sp_days = _number(tokens[index * 3])
            short_swap = _number(tokens[index * 3 + 1])
            long_swap = _number(tokens[index * 3 + 2])
            if sp_days is None or short_swap is None or long_swap is None:
                continue

            effective_date = trade_date + timedelta(days=1)
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
                    status="confirmed" if effective_date <= today_jst else "scheduled",
                    source=source_url,
                    fetched_at=fetched_at,
                    swap_currency="JPY",
                )
            )

    return records


def parse_pdf(
    content: bytes,
    *,
    year: int,
    month: int,
    today_jst: date | None = None,
    source_url: str = "fixture",
) -> list[SwapRecord]:
    fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    reader = PdfReader(io.BytesIO(content))
    records: list[SwapRecord] = []
    for page_index, page in enumerate(reader.pages[: len(PAGE_PAIRS)]):
        records.extend(
            parse_page_text(
                page.extract_text() or "",
                year=year,
                month=month,
                page_index=page_index,
                today_jst=today_jst,
                fetched_at=fetched_at,
                source_url=source_url,
            )
        )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def collect_month(
    year: int,
    month: int,
    *,
    session: requests.Session | None = None,
    timeout: int = 60,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
    )
    url = SOURCE_TEMPLATE.format(year=year, month=month)
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"FX Broadnet source is not a PDF: {response.url}")
    return parse_pdf(
        response.content,
        year=year,
        month=month,
        today_jst=today_jst,
        source_url=response.url,
    )
