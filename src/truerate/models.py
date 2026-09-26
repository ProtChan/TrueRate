from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class SwapRecord:
    broker: str
    pair: str
    trade_date: date
    effective_date: date
    sp_days: int
    long_swap_jpy: Optional[float]
    short_swap_jpy: Optional[float]
    unit: int
    status: str
    source: str
    fetched_at: str

    def to_csv_row(self) -> dict[str, str]:
        row = asdict(self)
        row["trade_date"] = self.trade_date.isoformat()
        row["effective_date"] = self.effective_date.isoformat()
        row["long_swap_jpy"] = "" if self.long_swap_jpy is None else str(self.long_swap_jpy)
        row["short_swap_jpy"] = "" if self.short_swap_jpy is None else str(self.short_swap_jpy)
        return {key: str(value) for key, value in row.items()}
