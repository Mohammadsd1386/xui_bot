from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def kb(*rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows])

def back_kb(data="main_menu"):
    return kb([(("🔙 بازگشت",data),)])

def main_menu_kb(is_admin=False):
    rows=[
        [("🛍 خرید سرویس","shop"),("👤 حساب کاربری","my_account")],
        [("📦 سرویس‌های من","my_orders"),("💳 کیف پول","wallet")],
        [("👥 دعوت دوستان","referral"),("🎫 تست رایگان","free_test")],
        [("📞 پشتیبانی","support")],
    ]
    if is_admin: rows.append([("⚙️ پنل ادمین","admin_main")])
    return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows])

def plans_kb(plans):
    rows=[]
    for p in plans:
        rows.append([(f"📦 {p['name']} | {p['gb']}GB / {p['days']}روز | {p['price_rial']:,}ت",f"plan_{p['id']}")])
    rows.append([("🔙 بازگشت","main_menu")])
    return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows])

def payment_method_kb(order_id, has_balance=False, balance=0):
    rows=[]
    if has_balance and balance>0:
        rows.append([(f"👛 موجودی ({balance:,}ت)",f"pay_balance_{order_id}")])
    rows.append([("💳 زرین‌پال",f"pay_zarinpal_{order_id}")])
    rows.append([("💎 تتر BEP20",f"pay_usdt_{order_id}"),("🔵 ترون TRC20",f"pay_tron_{order_id}")])
    rows.append([("🪙 تون کوین",f"pay_ton_{order_id}")])
    rows.append([("🔙 لغو","my_orders")])
    return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows])

def my_orders_kb(orders):
    rows=[]
    e={"active":"✅","expired":"⏰","pending":"⏳","cancelled":"❌"}
    for o in orders[:10]:
        rows.append([(f"{e.get(o['status'],'❓')} {o.get('plan_name') or 'سرویس'} — {o['status']}",f"order_{o['id']}")])
    rows.append([("🔙 بازگشت","main_menu")])
    return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows])

def order_detail_kb(order):
    rows=[]
    if order["status"]=="active":
        rows.append([("➕ افزایش حجم",f"extend_gb_{order['id']}"),("📅 تمدید",f"extend_days_{order['id']}")])
    rows.append([("🔙 بازگشت","my_orders")])
    return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows])

def support_kb():
    return kb([("🎫 تیکت جدید","new_ticket"),("📋 تیکت‌های من","my_tickets")],[("🔙 بازگشت","main_menu")])

def admin_main_kb():
    return kb(
        [("👥 کاربران","adm_users"),("📦 پلن‌ها","adm_plans")],
        [("🖥 پنل‌ها","adm_panels"),("📊 فروش","adm_sales")],
        [("💳 پرداخت‌های انتظار","adm_payments"),("⚙️ تنظیمات","adm_settings")],
        [("👨‍💼 ادمین‌ها","adm_admins"),("📢 ارسال همگانی","adm_broadcast")],
        [("🔙 منو اصلی","main_menu")]
    )

def admin_settings_kb():
    return kb(
        [("💱 نرخ دلار","set_usd_rate"),("🎁 پاداش رفرال","set_referral_reward")],
        [("🧪 تست رایگان","set_free_test"),("📢 کانال","set_channel")],
        [("💎 تتر BEP20","set_usdt_addr"),("🔵 ترون","set_tron_addr")],
        [("🪙 تون","set_ton_addr"),("🏦 زرین‌پال","set_zarinpal")],
        [("📱 پشتیبانی","set_support"),("🤖 نام ربات","set_bot_name")],
        [("🔙 بازگشت","adm_settings")]
    )

def admin_user_detail_kb(user_id):
    return kb(
        [("🎁 تخفیف",f"adm_discount_{user_id}"),("💰 شارژ کیف",f"adm_topup_{user_id}")],
        [("🚫 مسدود",f"adm_ban_{user_id}"),("✅ رفع مسدودی",f"adm_unban_{user_id}")],
        [("🔙 بازگشت","adm_users")]
    )

def admin_plan_kb(plan_id=None):
    rows=[[("➕ پلن جدید","adm_plan_add")]]
    if plan_id:
        rows.append([("✏️ ویرایش",f"adm_plan_edit_{plan_id}"),("🗑 حذف",f"adm_plan_del_{plan_id}")])
    rows.append([("🔙 بازگشت","adm_plans")])
    return InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in row] for row in rows])

def admin_panel_action_kb(panel_id):
    return kb(
        [("✏️ ویرایش",f"adm_panel_edit_{panel_id}"),("🗑 حذف",f"adm_panel_del_{panel_id}")],
        [("🔄 ریستارت",f"adm_panel_restart_{panel_id}"),("📋 کلاینت‌ها",f"adm_panel_clients_{panel_id}")],
        [("🔙 بازگشت","adm_panels")]
    )

def confirm_payment_kb(payment_id):
    return kb(
        [("✅ تأیید",f"adm_pay_confirm_{payment_id}"),("❌ رد",f"adm_pay_reject_{payment_id}")],
        [("🔙 بازگشت","adm_payments")]
    )

def free_test_admin_kb():
    return kb(
        [("✅ فعال","set_free_test_on"),("❌ غیرفعال","set_free_test_off")],
        [("📦 حجم","set_free_test_gb"),("📅 روز","set_free_test_days")],
        [("🔙 بازگشت","adm_settings")]
    )
