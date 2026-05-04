import time
from datetime import datetime


def fmt_rial(amount) -> str:
    return f"{int(amount or 0):,} تومان"


def fmt_bytes(b) -> str:
    if not b or b <= 0:
        return "نامحدود"
    gb = b / (1024 ** 3)
    return f"{gb:.2f} GB" if gb >= 1 else f"{b / (1024 ** 2):.0f} MB"


def fmt_date(ts) -> str:
    if not ts or ts == 0:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return "—"


def days_left(expires_at) -> str:
    if not expires_at or expires_at == 0:
        return "نامحدود"
    left = int(expires_at) - time.time()
    if left <= 0:
        return "⏰ منقضی شده"
    d = int(left / 86400)
    h = int((left % 86400) / 3600)
    return f"{d} روز" if d > 0 else f"{h} ساعت"


def gateway_label(gw: str) -> str:
    return {
        "zarinpal": "💳 زرین‌پال",
        "usdt": "💎 تتر BEP20",
        "usdt_bep20": "💎 تتر BEP20",
        "tron": "🔵 ترون TRC20",
        "ton": "🪙 تون کوین",
        "balance": "👛 کیف پول",
    }.get(gw, gw)


def status_emoji(s: str) -> str:
    return {"active": "✅", "expired": "⏰", "pending": "⏳",
            "cancelled": "❌", "confirmed": "✅", "failed": "❌"}.get(s, "❓")


def make_email(user_id: int, tag: str) -> str:
    slug = ''.join(c for c in str(tag).lower() if c.isalnum())[:6]
    ts = str(int(time.time()))[-4:]
    return f"u{user_id}{slug}{ts}"


def pct_bar(used: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "▓" * width
    filled = int(min(used / total, 1.0) * width)
    return "▓" * filled + "░" * (width - filled)


def apply_discount(price: int, pct: int) -> int:
    if pct <= 0:
        return int(price)
    return int(price * (100 - pct) / 100)
