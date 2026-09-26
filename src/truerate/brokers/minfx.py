from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from truerate.models import SwapRecord

BROKER_ID = "minfx"
BROKER_NAME = "みんなのFX"
JST = ZoneInfo("Asia/Tokyo")
SOURCE_URL = "https://min-fx.jp/market/swap/"

DEFAULT_UNIT = 10_000
PAIR_UNITS = {"HUF/JPY": 100_000}

TABLE_IDS = ("symbol1", "symbol2", "symbol3", "symbol4", "symbol6")
EXCLUDED_LABELS = {"RUBJPY", "USDJPYラージ"}
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})")


def _pair_from_label(label: str) -> str | None:
    cleaned = (
        label.replace("LIGHT", "")
        .replace("(L)", "")
        .replace(" ", "")
        .strip()
        .upper()
    )
    if "LIGHT" in label.upper() or cleaned in EXCLUDED_LABELS or "ラージ" in cleaned:
        return None
    if len(cleaned) != 6 or not cleaned.isascii() or not cleaned.isalpha():
        return None
    return f"{cleaned[:3]}/{cleaned[3:]}"


def _number(value: str) -> float | None:
    cleaned = value.replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―", "公表前"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _sp_days(value: str) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _infer_date(month: int, day: int, today_jst: date) -> date:
    candidates: list[date] = []
    for year in (today_jst.year - 1, today_jst.year, today_jst.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            pass
    if not candidates:
        raise ValueError(f"invalid calendar date {month}/{day}")
    return min(candidates, key=lambda candidate: abs((candidate - today_jst).days))


def parse_calendar_html(
    html: str,
    *,
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = SOURCE_URL,
) -> list[SwapRecord]:
    """Parse the public rolling one-month みんなのFX swap calendar."""
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    soup = BeautifulSoup(html, "html.parser")
    records: list[SwapRecord] = []

    for table_id in TABLE_IDS:
        container = soup.find(id=table_id)
        if container is None:
            continue
        table = container.find("table")
        if table is None:
            continue

        headers = [cell.get_text(" ", strip=True) for cell in table.select("thead th")]
        pair_columns: list[tuple[int, str]] = []
        for column, label in enumerate(headers[2:], start=2):
            pair = _pair_from_label(label)
            if pair:
                pair_columns.append((column, pair))

        rows = table.select("tbody tr")
        index = 0
        while index + 2 < len(rows):
            date_cells = [
                cell.get_text(" ", strip=True)
                for cell in rows[index].find_all(["th", "td"])
            ]
            buy_cells = [
                cell.get_text(" ", strip=True)
                for cell in rows[index + 1].find_all(["th", "td"])
            ]
            sell_cells = [
                cell.get_text(" ", strip=True)
                for cell in rows[index + 2].find_all(["th", "td"])
            ]
            index += 3

            if not date_cells or not buy_cells or not sell_cells:
                continue
            match = DATE_RE.search(date_cells[0])
            if not match or buy_cells[0] != "買" or sell_cells[0] != "売":
                continue

            trade_date = _infer_date(
                int(match.group(1)),
                int(match.group(2)),
                today_jst,
            )
            effective_date = trade_date + timedelta(days=1)

            for column, pair in pair_columns:
                if column >= len(date_cells):
                    continue
                value_column = column - 1
                if value_column >= len(buy_cells) or value_column >= len(sell_cells):
                    continue

                sp_days = _sp_days(date_cells[column])
                if sp_days is None:
                    continue

                long_swap = _number(buy_cells[value_column])
                short_swap = _number(sell_cells[value_column])
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
                        unit=PAIR_UNITS.get(pair, DEFAULT_UNIT),
                        status=status,
                        source=source_url,
                        fetched_at=fetched_at,
                    )
                )

    deduped: dict[tuple[str, date], SwapRecord] = {}
    for record in records:
        deduped[(record.pair, record.trade_date)] = record
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def collect_recent(
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
        }
    )
    response = client.get(SOURCE_URL, timeout=timeout)
    response.raise_for_status()
    return parse_calendar_html(
        response.text,
        today_jst=today_jst,
        source_url=response.url,
    )
