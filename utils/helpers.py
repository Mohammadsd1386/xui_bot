import time
from datetime import datetime

def fmt_rial(amount):
    return f"{int(amount):,} تومان"

def fmt_bytes(b):
    if not b or b <= 0: return "نامحدود"
    gb = b / (1024**3)
    return f"{gb:.2f} GB" if gb >= 1 else f"{b/(1024**2):.0f} MB"

def fmt_date(ts):
    if not ts or ts == 0: return "نامحدود"
    return datetime.fromtimestamp(ts).strftime("%Y/%m/%d %H:%M")

def days_left(expires_at):
    if not expires_at or expires_at == 0: return "نامحدود"
    left = expires_at - time.time()
    if left <= 0: return "منقضی شده"
    days = int(left / 86400)
    hours = int((left % 86400) / 3600)
    return f"{days} روز و {hours} ساعت" if days > 0 else f"{hours} ساعت"

def gateway_name(gw):
    return {"zarinpal":"زرین‌پال","usdt_bep20":"تتر BEP20","tron":"ترون TRC20",
            "ton":"تون کوین","balance":"کیف پول"}.get(gw, gw)

def status_emoji(s):
    return {"active":"✅","expired":"⏰","pending":"⏳","cancelled":"❌",
            "confirmed":"✅","failed":"❌"}.get(s, "❓")

def make_email(user_id, plan_name):
    import random, string
    slug = ''.join(c for c in str(plan_name).lower() if c.isalnum())[:6]
    ts = str(int(time.time()))[-4:]
    return f"u{user_id}_{slug}_{ts}"

def pct_bar(used, total, width=10):
    if total <= 0: return "▓" * width
    filled = int(min(used/total, 1.0) * width)
    return "▓" * filled + "░" * (width - filled)

def apply_discount(price, discount_pct):
    if discount_pct <= 0: return price
    return int(price * (100 - discount_pct) / 100)

def rial_to_usd(rial, rate):
    return round(rial / rate, 4)

async def notify_admins(bot, message, admin_ids):
    for aid in admin_ids:
        try:
            await bot.send_message(aid, message, parse_mode="Markdown")
        except Exception:
            pass
