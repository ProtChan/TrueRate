from __future__ import annotations

from datetime import date

import requests

from truerate.brokers.minfx import parse_calendar_html
from truerate.models import SwapRecord

BROKER_ID = "lightfx"
LIGHT_BROKER_ID = "lightfx_light"
BROKER_NAME = "LIGHT FX"
LIGHT_BROKER_NAME = "LIGHT FX LIGHT"
SOURCE_URL = "https://lightfx.jp/market/swap/"


def collect_recent_products(
    *,
    session: requests.Session | None = None,
    timeout: int = 30,
    today_jst: date | None = None,
) -> tuple[list[SwapRecord], list[SwapRecord]]:
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

    standard = parse_calendar_html(
        response.text,
        today_jst=today_jst,
        source_url=response.url,
        broker_id=BROKER_ID,
        light_only=False,
    )
    light = parse_calendar_html(
        response.text,
        today_jst=today_jst,
        source_url=response.url,
        broker_id=LIGHT_BROKER_ID,
        light_only=True,
    )
    return standard, light
