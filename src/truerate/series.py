from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable

BROKERS = {
    "click365": {
        "id": "click365",
        "name": "くりっく365",
    },
    "matsui_fx": {
        "id": "matsui_fx",
        "name": "松井証券FX",
    },
    "fxbroadnet": {
        "id": "fxbroadnet",
        "name": "FXブロードネット",
    },
    "hirose": {
        "id": "hirose",
        "name": "ヒロセ通商 LION FX",
    },
    "jfx": {
        "id": "jfx",
        "name": "JFX MATRIX TRADER",
    },
    "lightfx": {
        "id": "lightfx",
        "name": "LIGHT FX",
    },
    "lightfx_light": {
        "id": "lightfx_light",
        "name": "LIGHT FX LIGHT",
    },
    "minfx_light": {
        "id": "minfx_light",
        "name": "みんなのFX LIGHT",
    },
    "sbi_fx": {
        "id": "sbi_fx",
        "name": "SBI FXトレード",
    },
    "minfx": {
        "id": "minfx",
        "name": "みんなのFX",
    },
    "gaitame_com": {
        "id": "gaitame_com",
        "name": "外為どっとコム",
    },
    "triauto": {
        "id": "triauto",
        "name": "トライオートFX",
    },
    "gmo_click": {
        "id": "gmo_click",
        "name": "GMOクリック証券",
    },
    "gmo_gaika": {
        "id": "gmo_gaika",
        "name": "GMO外貨",
    },
}


def _daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _split_pair(pair: str) -> tuple[str, str]:
    base, quote = pair.split("/", 1)
    return base.upper(), quote.upper()


def _daily_rate_map(
    rate_rows: list[dict[str, str]],
    currencies: set[str],
    start: date,
    end: date,
) -> dict[str, dict[date, float]]:
    raw: dict[str, dict[date, float]] = defaultdict(dict)
    earliest_raw: date | None = None

    for row in rate_rows:
        currency = row["currency"].upper()
        row_date = date.fromisoformat(row["date"])
        raw[currency][row_date] = float(row["per_usd"])
        if earliest_raw is None or row_date < earliest_raw:
            earliest_raw = row_date

    scan_start = earliest_raw or start
    if scan_start > start:
        scan_start = start

    result: dict[str, dict[date, float]] = {}
    for currency in currencies:
        if currency == "USD":
            result[currency] = {day: 1.0 for day in _daterange(scan_start, end)}
            continue

        last: float | None = None
        daily: dict[date, float] = {}
        source = raw.get(currency, {})
        for day in _daterange(scan_start, end):
            if day in source:
                last = source[day]
            if last is not None:
                daily[day] = last
        result[currency] = daily

    return result


def build_site_payload(
    swap_rows: list[dict[str, str]],
    rate_rows: list[dict[str, str]],
    *,
    generated_at: str,
    today: date,
    unit: int = 10_000,
    margin_requirements: dict | None = None,
) -> dict:
    """Build broker/pair daily primitives for browser-side return rebasing."""
    confirmed = [
        row
        for row in swap_rows
        if row.get("status") == "confirmed"
        and row.get("long_swap_jpy", "") != ""
        and row.get("short_swap_jpy", "") != ""
    ]
    if not confirmed:
        return {
            "metadata": {
                "generated_at": generated_at,
                "unit": unit,
                "rate_provider": "Frankfurter blended official-source reference rates",
                "swap_effective_rule": "default: next business day after broker calendar display date (JST); SBI FX Trade: display date itself, weekend display rolled to next Monday",
                "margin_requirements": margin_requirements or {},
            },
            "brokers": list(BROKERS.values()),
            "pairs": [],
            "series": {},
        }

    currencies: set[str] = {"JPY"}
    for row in confirmed:
        base, quote = _split_pair(row["pair"])
        swap_currency = (row.get("swap_currency") or "JPY").upper()
        currencies.update({base, quote, swap_currency})

    min_trade_date = min(date.fromisoformat(row["trade_date"]) for row in confirmed)
    rates = _daily_rate_map(rate_rows, currencies, min_trade_date, today)

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in confirmed:
        grouped[(row["pair"], row["broker"])].append(row)

    series: dict[str, dict[str, dict]] = {}
    available_pairs: set[str] = set()

    for (pair, broker), rows in sorted(grouped.items()):
        base, quote = _split_pair(pair)
        row_swap_currencies = {
            (row.get("swap_currency") or "JPY").upper()
            for row in rows
        }
        required = {base, quote, "JPY", *row_swap_currencies}
        if any(not rates.get(currency) for currency in required):
            continue

        start = min(date.fromisoformat(row["trade_date"]) for row in rows)
        while start <= today and any(start not in rates[currency] for currency in required):
            start += timedelta(days=1)
        if start > today:
            continue

        by_effective_date: dict[date, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_effective_date[date.fromisoformat(row["effective_date"])].append(row)

        cumulative_long = 0.0
        cumulative_short = 0.0
        points: list[dict] = []

        for day in _daterange(start, today):
            if any(day not in rates[currency] for currency in required):
                continue

            for row in by_effective_date.get(day, []):
                row_unit = int(row["unit"])
                scale = unit / row_unit
                swap_currency = (row.get("swap_currency") or "JPY").upper()
                if swap_currency == "JPY":
                    to_jpy = 1.0
                else:
                    if day not in rates.get(swap_currency, {}):
                        continue
                    to_jpy = rates["JPY"][day] / rates[swap_currency][day]
                cumulative_long += float(row["long_swap_jpy"]) * scale * to_jpy
                cumulative_short += float(row["short_swap_jpy"]) * scale * to_jpy

            base_per_usd = rates[base][day]
            quote_per_usd = rates[quote][day]
            jpy_per_usd = rates["JPY"][day]

            spot = quote_per_usd / base_per_usd
            base_jpy = jpy_per_usd / base_per_usd
            quote_jpy = jpy_per_usd / quote_per_usd

            points.append(
                {
                    "date": day.isoformat(),
                    "spot": round(spot, 10),
                    "base_jpy": round(base_jpy, 10),
                    "quote_jpy": round(quote_jpy, 10),
                    "cum_long_swap_jpy": round(cumulative_long, 4),
                    "cum_short_swap_jpy": round(cumulative_short, 4),
                }
            )

        if not points:
            continue

        available_pairs.add(pair)
        series.setdefault(pair, {})[broker] = {
            "start_date": points[0]["date"],
            "end_date": points[-1]["date"],
            "points": points,
        }

    return {
        "metadata": {
            "generated_at": generated_at,
            "unit": unit,
            "rate_provider": "Frankfurter blended official-source reference rates",
            "swap_effective_rule": "default: next business day after broker calendar display date (JST); SBI FX Trade: display date itself, weekend display rolled to next Monday",
            "calculation": (
                "FX PnL is fixed base-unit PnL converted from quote currency to JPY "
                "at each day's reference rate; broker swap cashflow is added separately."
            ),
            "margin_requirements": margin_requirements or {},
        },
        "brokers": [BROKERS[key] for key in sorted(BROKERS)],
        "pairs": sorted(available_pairs),
        "series": series,
    }
