from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from truerate.brokers.ainet_fx import collect_recent_products as collect_ainet_products
from truerate.brokers.oanda_tokyo import collect_history as collect_oanda_tokyo_history
from truerate.brokers.dmm_fx import collect_recent_products as collect_dmm_products
from truerate.brokers.rakuten_fx import collect_recent as collect_rakuten_recent
from truerate.brokers.click365 import collect_period as collect_click365_period
from truerate.brokers.fxbroadnet import collect_month as collect_fxbroadnet_month
from truerate.brokers.matsui_fx import collect_year as collect_matsui_year
from truerate.brokers.gaitame_com import collect_month as collect_gaitame_month
from truerate.brokers.gaitame_online import collect_month as collect_gaitame_online_month
from truerate.brokers.hirose import collect_history as collect_hirose_history
from truerate.brokers.jfx import collect_history as collect_jfx_history
from truerate.brokers.lightfx import collect_recent_products as collect_lightfx_products
from truerate.brokers.minfx import collect_recent_products as collect_minfx_products
from truerate.brokers.sbi_fx import (
    collect_month as collect_sbi_month,
    effective_date_for_trade_date as sbi_effective_date_for_trade_date,
)
from truerate.brokers.gmo_click import (
    PAIR_START_DATES as GMO_CLICK_PAIR_START_DATES,
    collect_month as collect_gmo_click_month,
)
from truerate.brokers.gmo_gaika import collect_month as collect_gmo_gaika_month, iter_months
from truerate.brokers.triauto import collect_month as collect_triauto_month
from truerate.margins import build_margin_requirements
from truerate.models import next_business_day_after
from truerate.rates.frankfurter import fetch_usd_cross
from truerate.series import build_site_payload

JST = ZoneInfo("Asia/Tokyo")
OANDA_TOKYO_SWAP_PATH = ROOT / "data" / "swaps" / "oanda_tokyo.csv"
GAITAME_ONLINE_SWAP_PATH = ROOT / "data" / "swaps" / "gaitame_online.csv"
AINET_SWAP_PATH = ROOT / "data" / "swaps" / "ainet_fx.csv"
AINET_LOOP_SWAP_PATH = ROOT / "data" / "swaps" / "ainet_loop.csv"
RAKUTEN_SWAP_PATH = ROOT / "data" / "swaps" / "rakuten_fx.csv"
DMM_SWAP_PATH = ROOT / "data" / "swaps" / "dmm_fx.csv"
DMM_MINI_SWAP_PATH = ROOT / "data" / "swaps" / "dmm_fx_mini.csv"
DMM_LARGE_SWAP_PATH = ROOT / "data" / "swaps" / "dmm_fx_large.csv"
CLICK365_SWAP_PATH = ROOT / "data" / "swaps" / "click365.csv"
MATSUI_SWAP_PATH = ROOT / "data" / "swaps" / "matsui_fx.csv"
FXBROADNET_SWAP_PATH = ROOT / "data" / "swaps" / "fxbroadnet.csv"
MINFX_SWAP_PATH = ROOT / "data" / "swaps" / "minfx.csv"
MINFX_LIGHT_SWAP_PATH = ROOT / "data" / "swaps" / "minfx_light.csv"
LIGHTFX_SWAP_PATH = ROOT / "data" / "swaps" / "lightfx.csv"
LIGHTFX_LIGHT_SWAP_PATH = ROOT / "data" / "swaps" / "lightfx_light.csv"
SBI_SWAP_PATH = ROOT / "data" / "swaps" / "sbi_fx.csv"
HIROSE_SWAP_PATH = ROOT / "data" / "swaps" / "hirose.csv"
JFX_SWAP_PATH = ROOT / "data" / "swaps" / "jfx.csv"
GAITAME_SWAP_PATH = ROOT / "data" / "swaps" / "gaitame_com.csv"
GMO_GAIKA_SWAP_PATH = ROOT / "data" / "swaps" / "gmo_gaika.csv"
GMO_CLICK_SWAP_PATH = ROOT / "data" / "swaps" / "gmo_click.csv"
TRIAUTO_SWAP_PATH = ROOT / "data" / "swaps" / "triauto.csv"
RATE_PATH = ROOT / "data" / "rates" / "usd_reference.csv"
SITE_DATA_PATH = ROOT / "site" / "data" / "site-data.json"

SWAP_FIELDS = [
    "broker",
    "pair",
    "trade_date",
    "effective_date",
    "sp_days",
    "long_swap_jpy",
    "short_swap_jpy",
    "unit",
    "swap_currency",
    "status",
    "source",
    "fetched_at",
]
RATE_FIELDS = ["date", "currency", "per_usd", "provider"]


def parse_month(value: str) -> date:
    try:
        year_text, month_text = value.split("-", 1)
        return date(int(year_text), int(month_text), 1)
    except Exception as exc:
        raise argparse.ArgumentTypeError("month must be YYYY-MM") from exc


def previous_month(day: date) -> date:
    first = day.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def _normalize_effective_date(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    trade_date = date.fromisoformat(normalized["trade_date"])
    if normalized.get("broker") == "sbi_fx":
        effective_date = sbi_effective_date_for_trade_date(trade_date)
    else:
        effective_date = next_business_day_after(trade_date)
    normalized["effective_date"] = effective_date.isoformat()
    return normalized


def merge_swaps(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
) -> list[dict[str, str]]:
    existing = [_normalize_effective_date(row) for row in existing]
    incoming = [_normalize_effective_date(row) for row in incoming]
    merged = {(row["broker"], row["pair"], row["trade_date"]): row for row in existing}

    for row in incoming:
        key = (row["broker"], row["pair"], row["trade_date"])
        current = merged.get(key)
        incoming_complete = row["long_swap_jpy"] != "" and row["short_swap_jpy"] != ""

        if (
            current
            and current.get("status") == "confirmed"
            and (row.get("status") != "confirmed" or not incoming_complete)
        ):
            continue
        merged[key] = row

    return sorted(
        merged.values(),
        key=lambda row: (row["broker"], row["pair"], row["trade_date"]),
    )


def merge_rates(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged = {(row["date"], row["currency"]): row for row in existing}
    for row in incoming:
        merged[(row["date"], row["currency"])] = row
    return sorted(merged.values(), key=lambda row: (row["date"], row["currency"]))


def _merge_and_write(
    path: Path,
    existing: list[dict[str, str]],
    records,
) -> list[dict[str, str]]:
    merged = merge_swaps(existing, [record.to_csv_row() for record in records])
    write_csv(path, merged, SWAP_FIELDS)
    return merged


def refresh_minfx(today: date) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    standard_existing = load_csv(MINFX_SWAP_PATH)
    light_existing = load_csv(MINFX_LIGHT_SWAP_PATH)
    print("Collecting MinFX public rolling calendar...")
    standard, light = collect_minfx_products(today_jst=today)
    standard_count = len({record.pair for record in standard})
    light_count = len({record.pair for record in light})
    print(
        f"  standard: {len(standard)} rows / {standard_count} pairs; "
        f"LIGHT: {len(light)} rows / {light_count} pairs"
    )
    if standard_count < 30 or light_count < 10:
        raise RuntimeError("MinFX collector returned an unexpectedly small product set.")
    return (
        _merge_and_write(MINFX_SWAP_PATH, standard_existing, standard),
        _merge_and_write(MINFX_LIGHT_SWAP_PATH, light_existing, light),
    )


def refresh_lightfx(today: date) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    standard_existing = load_csv(LIGHTFX_SWAP_PATH)
    light_existing = load_csv(LIGHTFX_LIGHT_SWAP_PATH)
    print("Collecting LIGHT FX public rolling calendar...")
    standard, light = collect_lightfx_products(today_jst=today)
    standard_count = len({record.pair for record in standard})
    light_count = len({record.pair for record in light})
    print(
        f"  standard: {len(standard)} rows / {standard_count} pairs; "
        f"LIGHT: {len(light)} rows / {light_count} pairs"
    )
    if standard_count < 30 or light_count < 10:
        raise RuntimeError("LIGHT FX collector returned an unexpectedly small product set.")
    return (
        _merge_and_write(LIGHTFX_SWAP_PATH, standard_existing, standard),
        _merge_and_write(LIGHTFX_LIGHT_SWAP_PATH, light_existing, light),
    )


def refresh_hirose(today: date, *, start: date) -> list[dict[str, str]]:
    existing = load_csv(HIROSE_SWAP_PATH)
    print(f"Collecting Hirose LION FX history from {start}...")
    records = collect_hirose_history(start=start, today_jst=today)
    pair_count = len({record.pair for record in records})
    print(f"  {len(records)} rows / {pair_count} pairs")
    if pair_count < 40:
        raise RuntimeError("Hirose collector returned fewer than 40 pairs.")
    return _merge_and_write(HIROSE_SWAP_PATH, existing, records)


def refresh_jfx(today: date, *, start: date) -> list[dict[str, str]]:
    existing = load_csv(JFX_SWAP_PATH)
    for row in existing:
        if row.get("pair") == "HUF/JPY":
            row["unit"] = "100000"
    print(f"Collecting JFX history from {start}...")
    records = collect_jfx_history(start=start, today_jst=today)
    pair_count = len({record.pair for record in records})
    print(f"  {len(records)} rows / {pair_count} pairs")
    if pair_count < 35:
        raise RuntimeError("JFX collector returned fewer than 35 pairs.")
    return _merge_and_write(JFX_SWAP_PATH, existing, records)


def refresh_sbi(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(SBI_SWAP_PATH)
    # Historical rows created before the KRW quote-unit fix treated the
    # 10,000 displayed units as 10,000 KRW. At SBI one displayed KRW unit
    # represents 100 KRW, so those rows actually correspond to 1,000,000 KRW.
    for row in existing:
        if row.get("pair") == "KRW/JPY":
            row["unit"] = "1000000"
        trade_date = date.fromisoformat(row["trade_date"])
        effective_date = sbi_effective_date_for_trade_date(trade_date)
        row["effective_date"] = effective_date.isoformat()
        if row.get("long_swap_jpy", "") != "" and row.get("short_swap_jpy", "") != "":
            row["status"] = "confirmed" if effective_date <= today else "scheduled"
    month_start = start if full or not existing else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year, month in iter_months(month_start, today):
        print(f"Collecting SBI FX Trade {year:04d}-{month:02d}...")
        records = collect_sbi_month(year, month, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year and month == today.month:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 20:
        raise RuntimeError("SBI FX Trade current-month collector returned fewer than 20 pairs.")

    merged = merge_swaps(existing, incoming)
    write_csv(SBI_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_oanda_tokyo(today: date) -> list[dict[str, str]]:
    existing = load_csv(OANDA_TOKYO_SWAP_PATH)
    print("Collecting OANDA Japan Tokyo server full swap CSV...")
    records = collect_oanda_tokyo_history(today_jst=today)
    pair_count = len({record.pair for record in records})
    print(f"  {len(records)} rows / {pair_count} pairs")
    if pair_count < 25:
        raise RuntimeError(
            "OANDA Tokyo collector returned fewer than 25 pairs; "
            "refusing to publish possibly broken official CSV data."
        )

    merged = merge_swaps(existing, [record.to_csv_row() for record in records])
    write_csv(OANDA_TOKYO_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_gaitame_online(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(GAITAME_ONLINE_SWAP_PATH)
    month_start = start if full or not existing else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year, month in iter_months(month_start, today):
        print(f"Collecting Gaitame Online {year:04d}-{month:02d}...")
        records = collect_gaitame_online_month(year, month, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year and month == today.month:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 24:
        raise RuntimeError(
            "Gaitame Online current-month collector returned fewer than 24 pairs; "
            "refusing to publish possibly broken PDF data."
        )

    merged = merge_swaps(existing, incoming)
    write_csv(GAITAME_ONLINE_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_ainet(today: date) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    regular_existing = load_csv(AINET_SWAP_PATH)
    loop_existing = load_csv(AINET_LOOP_SWAP_PATH)
    print("Collecting Ainet FX regular + Loop-if-done current/previous month PDFs...")
    regular_records, loop_records = collect_ainet_products(today_jst=today)
    regular_pairs = len({record.pair for record in regular_records})
    loop_pairs = len({record.pair for record in loop_records})
    print(f"  regular: {len(regular_records)} rows / {regular_pairs} pairs")
    print(f"  loop: {len(loop_records)} rows / {loop_pairs} pairs")

    if regular_pairs < 22 or loop_pairs < 22:
        raise RuntimeError(
            "Ainet FX collector returned an unexpectedly small pair set; "
            "refusing to publish possibly broken PDF data."
        )

    regular = _merge_and_write(AINET_SWAP_PATH, regular_existing, regular_records)
    loop = _merge_and_write(AINET_LOOP_SWAP_PATH, loop_existing, loop_records)
    return regular, loop


def refresh_rakuten(today: date) -> list[dict[str, str]]:
    existing = load_csv(RAKUTEN_SWAP_PATH)
    print("Collecting Rakuten FX public swap feed...")
    records = collect_rakuten_recent(today_jst=today)
    pair_count = len({record.pair for record in records})
    print(f"  {len(records)} rows / {pair_count} pairs")
    if pair_count < 35:
        raise RuntimeError("Rakuten FX collector returned fewer than 35 pairs.")
    return _merge_and_write(RAKUTEN_SWAP_PATH, existing, records)


def refresh_dmm(today: date) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    standard_existing = load_csv(DMM_SWAP_PATH)
    mini_existing = load_csv(DMM_MINI_SWAP_PATH)
    large_existing = load_csv(DMM_LARGE_SWAP_PATH)

    print("Collecting DMM FX standard + Mini + Large rolling API...")
    standard, mini, large = collect_dmm_products(today_jst=today)
    standard_count = len({record.pair for record in standard})
    mini_count = len({record.pair for record in mini})
    large_count = len({record.pair for record in large})
    print(
        f"  standard: {len(standard)} rows / {standard_count} pairs; "
        f"Mini: {len(mini)} rows / {mini_count} pairs; "
        f"Large: {len(large)} rows / {large_count} pairs"
    )
    if standard_count < 20 or mini_count < 4 or large_count < 4:
        raise RuntimeError("DMM FX API returned an unexpectedly small product set.")

    return (
        _merge_and_write(DMM_SWAP_PATH, standard_existing, standard),
        _merge_and_write(DMM_MINI_SWAP_PATH, mini_existing, mini),
        _merge_and_write(DMM_LARGE_SWAP_PATH, large_existing, large),
    )


def refresh_click365(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(CLICK365_SWAP_PATH)
    period_start = start if full or not existing else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    cursor = period_start
    while cursor <= today:
        period_end = min(date(cursor.year, 12, 31), today)
        print(f"Collecting Click365 {cursor}..{period_end}...")
        records = collect_click365_period(cursor, period_end, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if period_end == today:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)
        cursor = date(cursor.year + 1, 1, 1)

    if current_pair_count < 20:
        raise RuntimeError(
            "Click365 current-period collector returned fewer than 20 pairs; "
            "refusing to publish possibly broken exchange data."
        )

    merged = merge_swaps(existing, incoming)
    write_csv(CLICK365_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_matsui(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(MATSUI_SWAP_PATH)
    start_year = start.year if full or not existing else max(start.year, (today - timedelta(days=45)).year)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year in range(start_year, today.year + 1):
        print(f"Collecting Matsui FX {year}...")
        records = collect_matsui_year(year, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 28:
        raise RuntimeError(
            "Matsui FX current-year collector returned fewer than 28 pairs; "
            "refusing to publish possibly broken source data."
        )

    merged = merge_swaps(existing, incoming)
    write_csv(MATSUI_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_fxbroadnet(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(FXBROADNET_SWAP_PATH)
    month_start = start if full or not existing else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year, month in iter_months(month_start, today):
        print(f"Collecting FX Broadnet {year:04d}-{month:02d}...")
        records = collect_fxbroadnet_month(year, month, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year and month == today.month:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 20:
        raise RuntimeError(
            "FX Broadnet current-month collector returned fewer than 20 pairs; "
            "refusing to publish possibly broken PDF data."
        )

    merged = merge_swaps(existing, incoming)
    write_csv(FXBROADNET_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_gaitame(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(GAITAME_SWAP_PATH)
    month_start = start if full or not existing else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year, month in iter_months(month_start, today):
        print(f"Collecting Gaitame.com {year:04d}-{month:02d}...")
        records = collect_gaitame_month(year, month, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year and month == today.month:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 35:
        raise RuntimeError(
            "Gaitame.com current-month collector returned fewer than 35 active pairs; "
            "refusing to publish possibly broken source data."
        )

    merged = merge_swaps(existing, incoming)
    write_csv(GAITAME_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_gmo_gaika(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(GMO_GAIKA_SWAP_PATH)
    month_start = start if full or not existing else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year, month in iter_months(month_start, today):
        print(f"Collecting GMO Gaika {year:04d}-{month:02d}...")
        records = collect_gmo_gaika_month(year, month, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year and month == today.month:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 20:
        raise RuntimeError(
            "GMO Gaika current-month parser returned fewer than 20 pairs; "
            "refusing to publish possibly broken scrape data."
        )

    merged = merge_swaps(existing, incoming)
    write_csv(GMO_GAIKA_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def refresh_gmo_click(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(GMO_CLICK_SWAP_PATH)
    dual_currency_pairs = {"EUR/USD", "GBP/USD", "AUD/USD", "NZD/USD"}
    needs_dual_currency_repair = any(
        row.get("pair") in dual_currency_pairs
        and int(float(row.get("sp_days") or 0)) > 0
        and (row.get("long_swap_jpy") in {"", None} or row.get("short_swap_jpy") in {"", None})
        for row in existing
    )
    if needs_dual_currency_repair:
        print("Repairing historical GMO Click dual-currency swap rows...")
    month_start = start if full or not existing or needs_dual_currency_repair else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year, month in iter_months(month_start, today):
        print(f"Collecting GMO Click {year:04d}-{month:02d}...")
        records = collect_gmo_click_month(year, month, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year and month == today.month:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 20:
        raise RuntimeError(
            "GMO Click current-month parser returned fewer than 20 standard pairs; "
            "refusing to publish possibly broken scrape data."
        )

    merged = merge_swaps(existing, incoming)

    # Guard against stale/incorrect rows from dates before a pair existed.
    cleaned: list[dict[str, str]] = []
    for row in merged:
        pair_start = GMO_CLICK_PAIR_START_DATES.get(row["pair"])
        if pair_start is not None and date.fromisoformat(row["trade_date"]) < pair_start:
            continue
        cleaned.append(row)

    write_csv(GMO_CLICK_SWAP_PATH, cleaned, SWAP_FIELDS)
    return cleaned


def refresh_triauto(
    today: date,
    *,
    full: bool,
    start: date,
) -> list[dict[str, str]]:
    existing = load_csv(TRIAUTO_SWAP_PATH)
    month_start = start if full or not existing else previous_month(today)
    incoming: list[dict[str, str]] = []
    current_pair_count = 0

    for year, month in iter_months(month_start, today):
        print(f"Collecting Triauto FX {year:04d}-{month:02d}...")
        records = collect_triauto_month(year, month, today_jst=today)
        pair_count = len({record.pair for record in records})
        print(f"  {len(records)} rows / {pair_count} pairs")
        if year == today.year and month == today.month:
            current_pair_count = pair_count
        incoming.extend(record.to_csv_row() for record in records)

    if current_pair_count < 28:
        raise RuntimeError(
            "Triauto current-month collector returned fewer than 28 active pairs; "
            "refusing to publish possibly broken source data."
        )

    merged = merge_swaps(existing, incoming)
    write_csv(TRIAUTO_SWAP_PATH, merged, SWAP_FIELDS)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh TrueRate data")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Re-fetch configured history for all brokers and reference rates.",
    )
    parser.add_argument(
        "--start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_START_MONTH", "2022-01")),
        help="GMO Gaika historical backfill start month (default: 2022-01).",
    )
    parser.add_argument(
        "--click365-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_CLICK365_START_MONTH", "2021-01")),
        help="Click365 historical backfill start month (default: 2021-01).",
    )
    parser.add_argument(
        "--matsui-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_MATSUI_START_MONTH", "2023-01")),
        help="Matsui FX historical backfill start month (default: 2023-01).",
    )
    parser.add_argument(
        "--fxbroadnet-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_FXBROADNET_START_MONTH", "2023-10")),
        help="FX Broadnet historical PDF backfill start month (default: 2023-10).",
    )
    parser.add_argument(
        "--gaitame-online-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_GAITAME_ONLINE_START_MONTH", "2024-01")),
        help="Gaitame Online historical PDF start month (default: 2024-01).",
    )
    parser.add_argument(
        "--gaitame-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_GAITAME_START_MONTH", "2022-01")),
        help="Gaitame.com historical backfill start month (default: 2022-01).",
    )
    parser.add_argument(
        "--gmo-click-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_GMO_CLICK_START_MONTH", "2024-01")),
        help="GMO Click historical backfill start month (default: 2024-01).",
    )
    parser.add_argument(
        "--sbi-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_SBI_START_MONTH", "2021-01")),
        help="SBI FX Trade historical backfill start month (default: 2021-01).",
    )
    parser.add_argument(
        "--hirose-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_HIROSE_START_MONTH", "2021-01")),
        help="Hirose historical CSV start month (default: 2021-01).",
    )
    parser.add_argument(
        "--jfx-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_JFX_START_MONTH", "2021-01")),
        help="JFX historical CSV start month (default: 2021-01).",
    )
    parser.add_argument(
        "--triauto-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_TRIAUTO_START_MONTH", "2024-01")),
        help="Triauto FX historical backfill start month (default: 2024-01).",
    )
    args = parser.parse_args()

    now = datetime.now(tz=JST)
    today = now.date()

    oanda_tokyo_swaps = refresh_oanda_tokyo(today)
    gaitame_online_swaps = refresh_gaitame_online(
        today,
        full=args.full,
        start=args.gaitame_online_start,
    )
    ainet_swaps, ainet_loop_swaps = refresh_ainet(today)
    rakuten_swaps = refresh_rakuten(today)
    dmm_swaps, dmm_mini_swaps, dmm_large_swaps = refresh_dmm(today)
    click365_swaps = refresh_click365(today, full=args.full, start=args.click365_start)
    matsui_swaps = refresh_matsui(today, full=args.full, start=args.matsui_start)
    fxbroadnet_swaps = refresh_fxbroadnet(today, full=args.full, start=args.fxbroadnet_start)
    minfx_swaps, minfx_light_swaps = refresh_minfx(today)
    lightfx_swaps, lightfx_light_swaps = refresh_lightfx(today)
    sbi_swaps = refresh_sbi(today, full=args.full, start=args.sbi_start)
    hirose_swaps = refresh_hirose(today, start=args.hirose_start)
    jfx_swaps = refresh_jfx(today, start=args.jfx_start)
    gaitame_swaps = refresh_gaitame(today, full=args.full, start=args.gaitame_start)
    gaika_swaps = refresh_gmo_gaika(today, full=args.full, start=args.start)
    click_swaps = refresh_gmo_click(today, full=args.full, start=args.gmo_click_start)
    triauto_swaps = refresh_triauto(today, full=args.full, start=args.triauto_start)
    swaps = (
        oanda_tokyo_swaps
        + gaitame_online_swaps
        + ainet_swaps
        + ainet_loop_swaps
        + rakuten_swaps
        + dmm_swaps
        + dmm_mini_swaps
        + dmm_large_swaps
        + click365_swaps
        + matsui_swaps
        + fxbroadnet_swaps
        + minfx_swaps
        + minfx_light_swaps
        + lightfx_swaps
        + lightfx_light_swaps
        + sbi_swaps
        + hirose_swaps
        + jfx_swaps
        + gaitame_swaps
        + gaika_swaps
        + click_swaps
        + triauto_swaps
    )

    confirmed_swaps = [
        row
        for row in swaps
        if row.get("status") == "confirmed"
        and row.get("long_swap_jpy", "") != ""
        and row.get("short_swap_jpy", "") != ""
    ]
    if not confirmed_swaps:
        raise RuntimeError("No confirmed broker swap rows are available.")

    first_trade = min(date.fromisoformat(row["trade_date"]) for row in confirmed_swaps)
    rate_history_start = first_trade - timedelta(days=10)

    currencies = {"JPY"}
    for row in swaps:
        base, quote = row["pair"].split("/", 1)
        swap_currency = (row.get("swap_currency") or "JPY").upper()
        currencies.update({base.upper(), quote.upper(), swap_currency})
    currencies.discard("USD")

    existing_rates = load_csv(RATE_PATH)
    existing_currencies = {row["currency"] for row in existing_rates}
    earliest_rate_by_currency: dict[str, date] = {}
    for row in existing_rates:
        currency = row["currency"]
        row_date = date.fromisoformat(row["date"])
        previous = earliest_rate_by_currency.get(currency)
        if previous is None or row_date < previous:
            earliest_rate_by_currency[currency] = row_date

    incoming_rates: list[dict[str, str]] = []

    for currency in sorted(currencies):
        earliest_existing = earliest_rate_by_currency.get(currency)
        if (
            args.full
            or not existing_rates
            or currency not in existing_currencies
            or earliest_existing is None
            or earliest_existing > rate_history_start
        ):
            currency_start = rate_history_start
        else:
            currency_start = max(rate_history_start, today - timedelta(days=10))

        print(f"Collecting reference rate USD/{currency} from {currency_start}...")
        rows = fetch_usd_cross(currency, currency_start, today)
        if not rows:
            print(f"  warning: no Frankfurter history for {currency}; affected pairs will be omitted")
        else:
            print(f"  {len(rows)} rate rows")
        incoming_rates.extend(rows)

    rates = merge_rates(existing_rates, incoming_rates)
    write_csv(RATE_PATH, rates, RATE_FIELDS)

    print("Collecting current margin requirements...")
    margin_requirements = build_margin_requirements(today)
    click365_margin = margin_requirements.get("click365", {})
    print(
        "  Click365 margin schedule "
        f"{click365_margin.get('effective_start')}..{click365_margin.get('effective_end')} "
        f"/ {len(click365_margin.get('per_pair_jpy', {}))} pairs"
    )

    payload = build_site_payload(
        swaps,
        rates,
        generated_at=now.isoformat(timespec="seconds"),
        today=today,
        unit=10_000,
        margin_requirements=margin_requirements,
    )
    SITE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_json = SITE_DATA_PATH.with_suffix(".json.tmp")
    temp_json.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temp_json.replace(SITE_DATA_PATH)

    print(
        f"Published {len(payload['pairs'])} pairs, "
        f"{len(swaps)} swap rows, {len(rates)} reference-rate rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
