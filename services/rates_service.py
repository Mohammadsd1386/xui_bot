"""نرخ دلار/تتر (تومان) از API عمومی — بدون نیاز به کلید."""
from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

from database import get_setting, set_setting

logger = logging.getLogger(__name__)

NOBITEX_ORDERBOOK = "https://api.nobitex.ir/v2/orderbook/USDTIRT"


def _toman_from_nobitex_price(price: float) -> int:
    """
    نوبیتکس قیمت USDT/IRT را معمولاً به ریال برمی‌گرداند.
    اگر عدد خیلی بزرگ بود (مثلاً > ۱ میلیون)، بر ۱۰ تقسیم می‌کنیم تا تومان شود.
    """
    p = float(price)
    if p > 1_000_000:
        return max(int(p / 10), 1)
    return max(int(p), 1)


async def fetch_usdt_toman_nobitex() -> int | None:
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(NOBITEX_ORDERBOOK) as r:
                if r.status != 200:
                    logger.warning("Nobitex orderbook HTTP %s", r.status)
                    return None
                data = await r.json(content_type=None)
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        if not bids or not asks:
            return None
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid = (best_bid + best_ask) / 2.0
        return _toman_from_nobitex_price(mid)
    except Exception as e:
        logger.warning("fetch_usdt_toman_nobitex: %s", e)
        return None


async def refresh_rates_once() -> tuple[bool, str]:
    """
    به‌روزرسانی usd_to_rial و usdt_to_rial از قیمت USDT (نزدیک به دلار در بازار ایران).
    """
    if get_setting("rates_auto_enabled", "1") != "1":
        return False, "به‌روزرسانی خودکار نرخ غیرفعال است."

    t = await fetch_usdt_toman_nobitex()
    if not t:
        return False, "دریافت نرخ از API ناموفق بود (اینترنت یا نوبیتکس)."

    set_setting("usd_to_rial", str(t))
    set_setting("usdt_to_rial", str(t))
    set_setting("rates_updated_at", str(int(time.time())))
    logger.info("Rates updated: %s toman/USDT", t)
    return True, f"نرخ به‌روز شد: `{t:,}` تومان (هر USDT)"


async def rates_refresh_loop() -> None:
    """حلقه پس‌زمینه — فاصله از تنظیمات rates_refresh_sec (ثانیه)."""
    while True:
        try:
            sec = int(get_setting("rates_refresh_sec", "3600") or "3600")
            sec = max(300, min(sec, 86400))
        except ValueError:
            sec = 3600
        await asyncio.sleep(sec)
        try:
            await refresh_rates_once()
        except Exception as e:
            logger.warning("rates_refresh_loop: %s", e)
