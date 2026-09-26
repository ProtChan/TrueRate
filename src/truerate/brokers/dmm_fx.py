from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from truerate.models import SwapRecord, next_business_day_after

BROKER_ID = "dmm_fx"
BROKER_MINI_ID = "dmm_fx_mini"
BROKER_LARGE_ID = "dmm_fx_large"

BROKER_NAME = "DMM FX"
BROKER_MINI_NAME = "DMM FX Mini"
BROKER_LARGE_NAME = "DMM FX Large"

JST = ZoneInfo("Asia/Tokyo")
SOURCE_TEMPLATE = "https://fx.dmm.com/api/fx/swap/swapcalendar_{code}.json"

STANDARD_CODES = (
    "USD_JPY", "EUR_JPY", "GBP_JPY", "AUD_JPY", "NZD_JPY", "CAD_JPY",
    "CHF_JPY", "ZAR_JPY", "MXN_JPY", "TRY_JPY",
    "EUR_USD", "GBP_USD", "AUD_USD", "NZD_USD",
    "EUR_GBP", "USD_CHF", "USD_CAD",
    "EUR_AUD", "EUR_NZD", "EUR_CHF", "GBP_AUD", "GBP_CHF", "AUD_NZD",
)
MINI_CODES = ("USM_JPY", "EUM_JPY", "GBM_JPY", "AUM_JPY")
LARGE_CODES = ("USL_JPY", "EUL_JPY", "GBL_JPY", "AUL_JPY")

SPECIAL_CODE_PAIRS = {
    "USM_JPY": "USD/JPY",
    "EUM_JPY": "EUR/JPY",
    "GBM_JPY": "GBP/JPY",
    "AUM_JPY": "AUD/JPY",
    "USL_JPY": "USD/JPY",
    "EUL_JPY": "EUR/JPY",
    "GBL_JPY": "GBP/JPY",
    "AUL_JPY": "AUD/JPY",
}


def _number(value) -> float | None:
    if value is None:
        return None
    cleaned = str(value).replace(",", "").replace("−", "-").replace("－", "-").strip()
    if cleaned in {"", "-", "—", "―"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _pair_for_code(code: str, product_id: str | None) -> str:
    if code in SPECIAL_CODE_PAIRS:
        return SPECIAL_CODE_PAIRS[code]
    if product_id and "/" in product_id:
        return product_id.upper()
    left, right = code.split("_", 1)
    return f"{left}/{right}"


def parse_pair_payload(
    payload: dict,
    *,
    code: str,
    broker: str,
    today_jst: date | None = None,
    fetched_at: str | None = None,
    source_url: str = "fixture",
) -> list[SwapRecord]:
    if today_jst is None:
        today_jst = datetime.now(tz=JST).date()
    if fetched_at is None:
        fetched_at = datetime.now(tz=JST).isoformat(timespec="seconds")

    records: list[SwapRecord] = []
    for item in payload.get("body", {}).get("swap", []):
        raw_date = str(item.get("eventYmdDate") or "").strip()
        if len(raw_date) != 8 or not raw_date.isdigit():
            continue
        trade_date = datetime.strptime(raw_date, "%Y%m%d").date()
        effective_date = next_business_day_after(trade_date)

        long_swap = _number(item.get("buySwapAmount"))
        short_swap = _number(item.get("sellSwapAmount"))
        sp_days_raw = _number(item.get("givingDays"))
        unit_raw = _number(item.get("swapAmountUnit"))
        if sp_days_raw is None or unit_raw is None:
            continue

        amounts_present = long_swap is not None and short_swap is not None
        status = (
            "confirmed"
            if amounts_present and effective_date <= today_jst
            else "scheduled"
        )

        records.append(
            SwapRecord(
                broker=broker,
                pair=_pair_for_code(code, item.get("fxProductId")),
                trade_date=trade_date,
                effective_date=effective_date,
                sp_days=int(sp_days_raw),
                long_swap_jpy=long_swap,
                short_swap_jpy=short_swap,
                unit=int(unit_raw),
                status=status,
                source=source_url,
                fetched_at=fetched_at,
                swap_currency="JPY",
            )
        )

    deduped = {(record.pair, record.trade_date): record for record in records}
    return sorted(deduped.values(), key=lambda item: (item.pair, item.trade_date))


def collect_code(
    code: str,
    broker: str,
    *,
    session: requests.Session | None = None,
    timeout: int = 30,
    today_jst: date | None = None,
) -> list[SwapRecord]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://fx.dmm.com/fx/service/swapcalendar/",
        }
    )
    url = SOURCE_TEMPLATE.format(code=code)
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    return parse_pair_payload(
        response.json(),
        code=code,
        broker=broker,
        today_jst=today_jst,
        source_url=response.url,
    )


def collect_recent_products(
    *,
    session: requests.Session | None = None,
    timeout: int = 30,
    today_jst: date | None = None,
) -> tuple[list[SwapRecord], list[SwapRecord], list[SwapRecord]]:
    client = session or requests.Session()
    client.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://fx.dmm.com/fx/service/swapcalendar/",
        }
    )

    groups = (
        (STANDARD_CODES, BROKER_ID),
        (MINI_CODES, BROKER_MINI_ID),
        (LARGE_CODES, BROKER_LARGE_ID),
    )
    results: list[list[SwapRecord]] = []
    for codes, broker in groups:
        records: list[SwapRecord] = []
        for code in codes:
            records.extend(
                collect_code(
                    code,
                    broker,
                    session=client,
                    timeout=timeout,
                    today_jst=today_jst,
                )
            )
        results.append(records)

    return results[0], results[1], results[2]
