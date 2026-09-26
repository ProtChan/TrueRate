from __future__ import annotations

import io
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from pypdf import PdfReader

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "gaitame_online"
BROKER_NAME = "外為オンライン"
JST = ZoneInfo("Asia/Tokyo")
SOURCE_TEMPLATE = "https://www.gaitameonline.com/pdf/swap{year:04d}{month:02d}.pdf"

PAGE_PAIRS = (
    ("USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/JPY", "NZD/JPY", "CAD/JPY", "CHF/JPY"),
    ("AUD/CHF", "AUD/NZD", "AUD/USD", "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/GBP"),
    ("EUR/NZD", "EUR/USD", "GBP/AUD", "GBP/CHF", "GBP/NZD", "GBP/USD", "NZD/USD"),
    ("USD/CAD", "USD/CHF", "ZAR/JPY", "TRY/JPY", "MXN/JPY"),
)

ROW_RE = re.compile(
    r"^\s*(?P<year>\d{4})\s*/\s*(?P<month>\d{1,2})\s*/\s*(?P<day>\d{1,2})"
    r"\s+\S+\s+(?P<values>.*)$"
)
TOKEN_RE = re.compile(r"(?<!\S)-?(?:\d[\d,]*)(?:\.\d+)?|(?<!\S)-(?!\S)")


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

        try:
            trade_date = date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
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
            if sp_days is None:
                continue
            sp_days_int = int(sp_days)
            if not 0 <= sp_days_int <= 10:
                continue

            # Older PDFs can reorder visually empty/zero cells during text extraction.
            # A zero-day row must economically contribute zero regardless of cell order.
            if sp_days_int == 0:
                short_swap = 0.0
                long_swap = 0.0

            effective_date = next_business_day_after(trade_date)
            amounts_present = short_swap is not None and long_swap is not None
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
                    sp_days=sp_days_int,
                    long_swap_jpy=long_swap,
                    short_swap_jpy=short_swap,
                    unit=10_000,
                    status=status,
                    source=source_url,
                    fetched_at=fetched_at,
                    swap_currency="JPY",
                )
            )

    return records


def parse_pdf(
    content: bytes,
    *,
    today_jst: date | None = None,
    source_url: str,
) -> list[SwapRecord]:
    fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    reader = PdfReader(io.BytesIO(content))
    records: list[SwapRecord] = []
    for page_index, page in enumerate(reader.pages[: len(PAGE_PAIRS)]):
        records.extend(
            parse_page_text(
                page.extract_text() or "",
                page_index=page_index,
                today_jst=today_jst,
                fetched_at=fetched_at,
                source_url=source_url,
            )
        )
    deduped = {(r.pair, r.trade_date): r for r in records}
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
        raise RuntimeError(f"Gaitame Online source is not a PDF: {response.url}")
    return parse_pdf(response.content, today_jst=today_jst, source_url=response.url)
