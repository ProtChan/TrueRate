from __future__ import annotations

from datetime import date
from typing import Iterable

from truerate.models import SwapRecord


def currently_unavailable_pairs(
    records: Iterable[SwapRecord],
    *,
    today: date,
) -> set[str]:
    """Return pairs whose latest OANDA row on/before today has a blank side."""
    latest: dict[str, SwapRecord] = {}

    for record in records:
        if record.trade_date > today:
            continue
        current = latest.get(record.pair)
        if current is None or record.trade_date >= current.trade_date:
            latest[record.pair] = record

    return {
        pair
        for pair, record in latest.items()
        if record.long_swap_jpy is None or record.short_swap_jpy is None
    }


def complete_supported_records(
    records: Iterable[SwapRecord],
    *,
    unavailable_pairs: set[str],
) -> list[SwapRecord]:
    """Keep only fully quoted rows for pairs that are currently supported."""
    return [
        record
        for record in records
        if record.pair not in unavailable_pairs
        and record.long_swap_jpy is not None
        and record.short_swap_jpy is not None
    ]
