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

from truerate.brokers.gaitame_com import collect_month as collect_gaitame_month
from truerate.brokers.minfx import collect_recent as collect_minfx_recent
from truerate.brokers.gmo_click import (
    PAIR_START_DATES as GMO_CLICK_PAIR_START_DATES,
    collect_month as collect_gmo_click_month,
)
from truerate.brokers.gmo_gaika import collect_month as collect_gmo_gaika_month, iter_months
from truerate.brokers.triauto import collect_month as collect_triauto_month
from truerate.rates.frankfurter import fetch_usd_cross
from truerate.series import build_site_payload

JST = ZoneInfo("Asia/Tokyo")
MINFX_SWAP_PATH = ROOT / "data" / "swaps" / "minfx.csv"
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


def merge_swaps(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
) -> list[dict[str, str]]:
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


def refresh_minfx(today: date) -> list[dict[str, str]]:
    existing = load_csv(MINFX_SWAP_PATH)
    print("Collecting MinFX public rolling calendar...")
    records = collect_minfx_recent(today_jst=today)
    pair_count = len({record.pair for record in records})
    print(f"  {len(records)} rows / {pair_count} pairs")

    if pair_count < 30:
        raise RuntimeError(
            "MinFX collector returned fewer than 30 standard pairs; "
            "refusing to publish possibly broken source data."
        )

    merged = merge_swaps(existing, [record.to_csv_row() for record in records])
    write_csv(MINFX_SWAP_PATH, merged, SWAP_FIELDS)
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
    month_start = start if full or not existing else previous_month(today)
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
        "--triauto-start",
        type=parse_month,
        default=parse_month(os.environ.get("TRUERATE_TRIAUTO_START_MONTH", "2024-01")),
        help="Triauto FX historical backfill start month (default: 2024-01).",
    )
    args = parser.parse_args()

    now = datetime.now(tz=JST)
    today = now.date()

    minfx_swaps = refresh_minfx(today)
    gaitame_swaps = refresh_gaitame(today, full=args.full, start=args.gaitame_start)
    gaika_swaps = refresh_gmo_gaika(today, full=args.full, start=args.start)
    click_swaps = refresh_gmo_click(today, full=args.full, start=args.gmo_click_start)
    triauto_swaps = refresh_triauto(today, full=args.full, start=args.triauto_start)
    swaps = minfx_swaps + gaitame_swaps + gaika_swaps + click_swaps + triauto_swaps

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
        currencies.update({base.upper(), quote.upper()})
    currencies.discard("USD")

    existing_rates = load_csv(RATE_PATH)
    existing_currencies = {row["currency"] for row in existing_rates}
    incoming_rates: list[dict[str, str]] = []

    for currency in sorted(currencies):
        if args.full or not existing_rates or currency not in existing_currencies:
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

    payload = build_site_payload(
        swaps,
        rates,
        generated_at=now.isoformat(timespec="seconds"),
        today=today,
        unit=10_000,
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
