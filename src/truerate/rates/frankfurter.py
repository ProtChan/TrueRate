from __future__ import annotations

from datetime import date

import requests

API_URL = "https://api.frankfurter.dev/v2/rates"
PROVIDER_ID = "frankfurter_blend"


def fetch_usd_cross(
    currency: str,
    start: date,
    end: date,
    *,
    session: requests.Session | None = None,
    timeout: int = 45,
) -> list[dict[str, str]]:
    """Fetch daily units-of-currency per USD.

    Frankfurter v2 returns a flat time-series array. USD itself is synthetic
    here and always equals 1, so no network request is required.
    """
    currency = currency.upper()
    if currency == "USD":
        return []

    client = session or requests.Session()
    client.headers.setdefault(
        "User-Agent",
        "TrueRate/0.1 (+https://github.com/ProtChan/TrueRate)",
    )
    response = client.get(
        API_URL,
        params={
            "base": "USD",
            "quotes": currency,
            "from": start.isoformat(),
            "to": end.isoformat(),
        },
        timeout=timeout,
    )

    # Some broker currencies may not exist in the public reference-rate
    # provider. A missing reference rate should not break swap collection.
    if response.status_code == 422:
        return []

    response.raise_for_status()
    payload = response.json()
    rows: list[dict[str, str]] = []
    for item in payload:
        if str(item.get("quote", "")).upper() != currency:
            continue
        rows.append(
            {
                "date": str(item["date"]),
                "currency": currency,
                "per_usd": str(item["rate"]),
                "provider": PROVIDER_ID,
            }
        )
    return rows
