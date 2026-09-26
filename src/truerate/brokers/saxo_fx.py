from __future__ import annotations

import io
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from pypdf import PdfReader

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "saxo_fx"
BROKER_NAME = "サクソバンク証券"
JST = ZoneInfo("Asia/Tokyo")

HISTORY_URL = "https://cdn-storage.saxobank.com/jp/swappoint/swappoint-historical.pdf"
WEEKLY_URL = "https://cdn-storage.saxobank.com/jp/swappoint/swappoint-weekly.pdf"

ROW_RE = re.compile(
    r"^(?P<code>[A-Z]{6})\s+.*?"
    r"(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日\([^)]*\)\s+"
    r"(?P<sell>-?[\d,]+(?:\.\d+)?)\s+"
    r"(?P<buy>-?[\d,]+(?:\.\d+)?)\s+"
    r"(?P<days>\d+)\s*$"
)


def _number(value: str) -> float:
    return float(value.replace(",", "").replace("−", "-").replace("－", "-"))


def _pair_from_code(code: str) -> str:
    return f"{code[:3]}/{code[3:]}"


def parse_pdf_text(
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

        pair = _pair_from_code(match.group("code"))
        effective_date = next_business_day_after(trade_date)
        records.append(
            SwapRecord(
                broker=BROKER_ID,
                pair=pair,
                trade_date=trade_date,
                effective_date=effective_date,
                sp_days=int(match.group("days")),
                long_swap_jpy=_number(match.group("buy")),
                short_swap_jpy=_number(match.group("sell")),
                unit=10_000,
                status="confirmed" if effective_date <= today_jst else "scheduled",
                source=source_url,
                fetched_at=fetched_at,
                swap_currency="JPY",
            )
        )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def parse_pdf(
    content: bytes,
    *,
    today_jst: date | None = None,
    source_url: str,
) -> list[SwapRecord]:
    fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")
    reader = PdfReader(io.BytesIO(content))
    records: list[SwapRecord] = []
    for page in reader.pages:
        records.extend(
            parse_pdf_text(
                page.extract_text() or "",
                today_jst=today_jst,
                fetched_at=fetched_at,
                source_url=source_url,
            )
        )
    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def _fetch_pdf(
    client: requests.Session,
    url: str,
    *,
    timeout: int,
) -> tuple[bytes, str]:
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"Saxo swap source is not a PDF: {response.url}")
    return response.content, response.url


def collect_history(
    *,
    session: requests.Session | None = None,
    timeout: int = 120,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }
    )

    records: list[SwapRecord] = []
    for url in (HISTORY_URL, WEEKLY_URL):
        content, source_url = _fetch_pdf(client, url, timeout=timeout)
        records.extend(parse_pdf(content, today_jst=today_jst, source_url=source_url))

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))
