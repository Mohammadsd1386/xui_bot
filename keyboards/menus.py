from telegram import (
    InlineKeyboardButton as Btn,
    InlineKeyboardMarkup as Markup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from database import get_setting


def _kb(rows):
    return Markup([[Btn(text, callback_data=data) for text, data in row] for row in rows])


def back_btn(target="main_menu"):
    return _kb([[("🔙 بازگشت", target)]])


# ═══════════════════════════════════════════════════════════
# USER KEYBOARDS
# ═══════════════════════════════════════════════════════════

def main_menu_kb(is_admin=False):
    rows = [
        [("🛍 خرید سرویس", "shop"), ("👤 حساب کاربری", "my_account")],
        [("📦 سرویس‌های من", "my_orders"), ("💳 کیف پول", "wallet")],
        [("👥 دعوت دوستان", "referral"), ("🎫 تست رایگان", "free_test")],
        [("📞 پشتیبانی", "support")],
    ]
    if is_admin:
        rows.append([("⚙️ پنل ادمین", "adm_main")])
    return _kb(rows)

def main_menu_reply_kb(is_admin=False):
    rows = [
        [KeyboardButton("🛍 خرید سرویس"), KeyboardButton("👤 حساب کاربری")],
        [KeyboardButton("📦 سرویس‌های من"), KeyboardButton("💳 کیف پول")],
        [KeyboardButton("👥 دعوت دوستان"), KeyboardButton("🎫 تست رایگان")],
        [KeyboardButton("📞 پشتیبانی")],
    ]
    if is_admin:
        rows.append([KeyboardButton("⚙️ پنل ادمین")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def plans_kb(plans: list):
    rows = []
    for p in plans:
        label = f"📦 {p['name']} | {p['gb']}GB / {p['days']}روز | {int(p['price_rial']):,}ت"
        rows.append([(label, f"plan_{p['id']}")])
    rows.append([("🔙 بازگشت", "main_menu")])
    return _kb(rows)


def payment_kb(order_id: int, balance: int = 0):
    rows = []
    if balance > 0 and get_setting("pay_balance_enabled", "1") == "1":
        rows.append([(f"👛 کیف پول ({balance:,}ت)", f"pay_balance_{order_id}")])
    if get_setting("pay_zarinpal_enabled", "1") == "1":
        rows.append([("💳 زرین‌پال (ریال)", f"pay_zarinpal_{order_id}")])
    if get_setting("pay_card2card_enabled", "1") == "1":
        rows.append([("🏦 کارت به کارت", f"pay_card2card_{order_id}")])
    crypto_row = []
    if get_setting("pay_usdt_enabled", "1") == "1":
        crypto_row.append(("💎 تتر BEP20", f"pay_usdt_{order_id}"))
    if get_setting("pay_tron_enabled", "1") == "1":
        crypto_row.append(("🔵 ترون TRC20", f"pay_tron_{order_id}"))
    if crypto_row:
        rows.append(crypto_row)
    if get_setting("pay_ton_enabled", "1") == "1":
        rows.append([("🪙 تون کوین", f"pay_ton_{order_id}")])
    rows.append([("🚫 لغو", "my_orders")])
    return _kb(rows)


def orders_kb(orders: list):
    emoji = {"active": "✅", "expired": "⏰", "pending": "⏳", "cancelled": "❌"}
    rows = []
    for o in orders[:15]:
        e = emoji.get(o["status"], "❓")
        name = o.get("plan_name") or "سرویس"
        rows.append([(f"{e} {name}", f"order_{o['id']}")])
    rows.append([("🔙 بازگشت", "main_menu")])
    return _kb(rows)


def order_detail_kb(order_id: int, is_active: bool):
    rows = []
    if is_active:
        rows.append([
            ("➕ افزایش حجم", f"extend_gb_{order_id}"),
            ("📅 تمدید", f"extend_days_{order_id}")
        ])
    rows.append([("🔙 بازگشت", "my_orders")])
    return _kb(rows)


def support_kb():
    return _kb([
        [("🎫 تیکت جدید", "new_ticket"), ("📋 تیکت‌های من", "my_tickets")],
        [("🔙 بازگشت", "main_menu")]
    ])


def my_tickets_kb(tickets: list):
    e = {"open": "🟡", "answered": "🟢", "closed": "⚫"}
    rows = [[( f"{e.get(t['status'],'❓')} #{t['id']} {t['subject'] or '—'}", f"ticket_view_{t['id']}")] for t in tickets[:10]]
    rows.append([("🔙 بازگشت", "support")])
    return _kb(rows)


def crypto_paid_kb(payment_id: int):
    return _kb([
        [("✅ پرداخت کردم", f"crypto_paid_{payment_id}")],
        [("🚫 لغو", "shop")]
    ])


# ═══════════════════════════════════════════════════════════
# ADMIN KEYBOARDS
# ═══════════════════════════════════════════════════════════

def adm_main_kb():
    return _kb([
        [("👥 کاربران", "adm_users"), ("📦 پلن‌ها", "adm_plans")],
        [("🖥 پنل‌ها", "adm_panels"), ("📊 گزارش فروش", "adm_sales")],
        [("💳 پرداخت‌های انتظار", "adm_payments"), ("👛 درخواست‌های کیف", "adm_wallet_reqs")],
        [("⚙️ تنظیمات", "adm_settings")],
        [("👨‍💼 مدیریت ادمین‌ها", "adm_admins"), ("📢 ارسال همگانی", "adm_broadcast")],
        [("🔙 منوی اصلی", "main_menu")]
    ])


def adm_settings_kb():
    return _kb([
        [("💱 نرخ دلار", "set_usd_rate"), ("🎁 پاداش رفرال", "set_referral")],
        [("🧪 تست رایگان", "set_free_test"), ("📢 کانال اجباری", "set_channel")],
        [("💳 روش‌های پرداخت", "set_payment_methods"), ("🏦 کارت‌به‌کارت", "set_card_info")],
        [("💎 آدرس تتر BEP20", "set_usdt_addr"), ("🔵 آدرس ترون", "set_tron_addr")],
        [("🪙 آدرس تون", "set_ton_addr"), ("🏦 زرین‌پال", "set_zarinpal")],
        [("📱 یوزر پشتیبانی", "set_support"), ("🤖 نام ربات", "set_bot_name")],
        [("🔙 بازگشت", "adm_main")]
    ])


def adm_free_test_kb():
    return _kb([
        [("✅ فعال کردن", "ft_on"), ("❌ غیرفعال", "ft_off")],
        [("📦 تنظیم حجم", "ft_set_gb"), ("📅 تنظیم روز", "ft_set_days")],
        [("🔙 بازگشت", "adm_settings")]
    ])


def adm_payment_methods_kb():
    def s(key: str) -> str:
        return "✅" if get_setting(key, "1") == "1" else "❌"
    return _kb([
        [(f"{s('pay_balance_enabled')} کیف پول", "pay_toggle_balance"),
         (f"{s('pay_zarinpal_enabled')} زرین‌پال", "pay_toggle_zarinpal")],
        [(f"{s('pay_card2card_enabled')} کارت‌به‌کارت", "pay_toggle_card2card"),
         (f"{s('pay_usdt_enabled')} تتر", "pay_toggle_usdt")],
        [(f"{s('pay_tron_enabled')} ترون", "pay_toggle_tron"),
         (f"{s('pay_ton_enabled')} تون", "pay_toggle_ton")],
        [("🔙 بازگشت", "adm_settings")]
    ])


def adm_users_kb(users: list, offset: int = 0):
    rows = []
    for u in users:
        name = u.get("full_name") or u.get("username") or str(u["telegram_id"])
        ban = " 🚫" if u.get("is_banned") else ""
        rows.append([(f"{name}{ban}", f"adm_user_{u['telegram_id']}")])
    nav = []
    if offset > 0:
        nav.append(("◀️ قبلی", f"adm_users_page_{max(0, offset-20)}"))
    if len(users) == 20:
        nav.append(("▶️ بعدی", f"adm_users_page_{offset+20}"))
    if nav:
        rows.append(nav)
    rows.append([("🔍 جستجو", "adm_user_search"), ("🔙 بازگشت", "adm_main")])
    return _kb(rows)


def adm_user_detail_kb(user_id: int):
    uid = str(user_id)
    return _kb([
        [("🎁 تخفیف", f"adm_discount_{uid}"), ("💰 شارژ کیف", f"adm_topup_{uid}")],
        [("🚫 مسدود", f"adm_ban_{uid}"), ("✅ رفع مسدودی", f"adm_unban_{uid}")],
        [("📦 سرویس‌ها", f"adm_user_orders_{uid}")],
        [("🔙 بازگشت", "adm_users")]
    ])


def adm_plans_kb(plans: list):
    rows = []
    for p in plans:
        e = "✅" if p["is_active"] else "❌"
        rows.append([(f"{e} {p['name']} | {p['gb']}GB/{p['days']}روز", f"adm_plan_{p['id']}")])
    rows.append([("➕ پلن جدید", "adm_plan_add"), ("🔙 بازگشت", "adm_main")])
    return _kb(rows)


def adm_plan_detail_kb(plan_id: int):
    pid = str(plan_id)
    return _kb([
        [("✏️ ویرایش نام", f"adm_plan_edit_name_{pid}"), ("💰 ویرایش قیمت", f"adm_plan_edit_price_{pid}")],
        [("✅ فعال", f"adm_plan_enable_{pid}"), ("❌ غیرفعال", f"adm_plan_disable_{pid}")],
        [("🗑 حذف", f"adm_plan_del_{pid}")],
        [("🔙 بازگشت", "adm_plans")]
    ])


def adm_panels_kb(panels: list):
    rows = []
    for p in panels:
        e = "✅" if p["is_active"] else "❌"
        t = "سنایی" if p["type"] == "xui" else "مرزبان"
        rows.append([(f"{e} {p['name']} ({t})", f"adm_panel_{p['id']}")])
    rows.append([("➕ پنل جدید", "adm_panel_add"), ("🔙 بازگشت", "adm_main")])
    return _kb(rows)


def adm_panel_detail_kb(panel_id: int):
    pid = str(panel_id)
    return _kb([
        [("🔄 ریستارت", f"adm_panel_restart_{pid}"), ("📋 کلاینت‌ها", f"adm_panel_clients_{pid}")],
        [("🗑 حذف", f"adm_panel_del_{pid}"), ("✅/❌ فعال/غیرفعال", f"adm_panel_toggle_{pid}")],
        [("🔙 بازگشت", "adm_panels")]
    ])


def adm_panel_type_kb():
    return _kb([
        [("🖥 سنایی (3x-ui)", "pt_xui"), ("🔷 مرزبان", "pt_marzban")],
        [("🚫 لغو", "adm_panels")]
    ])


def adm_payments_kb(payments: list):
    rows = []
    for p in payments[:10]:
        name = p.get("full_name") or p.get("username") or str(p["user_id"])
        rows.append([(f"💳 {name} | {int(p['amount_rial']):,}ت", f"adm_pay_{p['id']}")])
    rows.append([("🔙 بازگشت", "adm_main")])
    return _kb(rows)


def adm_wallet_reqs_kb(reqs: list):
    rows = []
    for r in reqs[:15]:
        name = r.get("full_name") or r.get("username") or str(r["user_id"])
        typ = "➕ شارژ" if r["type"] == "deposit" else "➖ برداشت"
        rows.append([(f"{typ} | {name} | {int(r['amount_rial']):,}ت", f"adm_wr_{r['id']}")])
    rows.append([("🔙 بازگشت", "adm_main")])
    return _kb(rows)


def adm_wallet_req_detail_kb(req_id: int):
    return _kb([
        [("✅ تایید", f"adm_wr_ok_{req_id}"), ("❌ رد", f"adm_wr_no_{req_id}")],
        [("🔙 بازگشت", "adm_wallet_reqs")]
    ])


def adm_pay_detail_kb(pay_id: int):
    pid = str(pay_id)
    return _kb([
        [("✅ تأیید پرداخت", f"adm_pay_ok_{pid}"), ("❌ رد پرداخت", f"adm_pay_no_{pid}")],
        [("🔙 بازگشت", "adm_payments")]
    ])


def adm_admins_kb(admins: list):
    rows = []
    for a in admins:
        name = a.get("full_name") or a.get("username") or str(a["telegram_id"])
        rows.append([(f"🔴 حذف {name}", f"adm_del_admin_{a['telegram_id']}")])
    rows.append([("➕ ادمین جدید", "adm_add_admin"), ("🔙 بازگشت", "adm_main")])
    return _kb(rows)


def adm_plan_select_panel_kb(panels: list):
    rows = []
    for p in panels:
        rows.append([(p["name"], f"adm_plan_panel_{p['id']}")])
    rows.append([("🚫 لغو", "adm_plans")])
    return _kb(rows)


def confirm_kb(yes_data: str, no_data: str):
    return _kb([[("✅ بله", yes_data), ("❌ خیر", no_data)]])
