import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from database import get_db, get_setting, set_setting
from services.user_service import get_user, get_all_users, set_user_discount, ban_user
from services.order_service import get_sales_stats, get_pending_payments
from services.panel_service import get_panel_api
from services.payment_service import confirm_payment
from keyboards.menus import (admin_main_kb, admin_settings_kb, admin_user_detail_kb,
                               admin_plan_kb, admin_panel_action_kb, confirm_payment_kb,
                               free_test_admin_kb, back_kb)
from utils.helpers import fmt_rial, gateway_name, fmt_date, status_emoji

logger = logging.getLogger(__name__)

# Conversation states
(SET_VALUE, ADD_PLAN_NAME, ADD_PLAN_GB, ADD_PLAN_DAYS, ADD_PLAN_PRICE,
 ADD_PLAN_PANEL, ADD_PANEL_NAME, ADD_PANEL_TYPE, ADD_PANEL_URL, ADD_PANEL_PATH,
 ADD_PANEL_USER, ADD_PANEL_PASS, ADD_PANEL_IB, ADD_ADMIN_ID,
 BROADCAST_MSG, USER_TOPUP, USER_SEARCH) = range(17)


async def admin_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("⚙️ *پنل ادمین*\nعملیات مورد نظر را انتخاب کنید:",
                                      reply_markup=admin_main_kb(), parse_mode="Markdown")
    else:
        await update.message.reply_text("⚙️ *پنل ادمین*", reply_markup=admin_main_kb(), parse_mode="Markdown")


# ─── USERS ────────────────────────────────────────────────────────────────────
async def adm_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users = get_all_users(20, 0)
    total = _count_users()
    text = f"👥 *کاربران* — جمع: `{total}`\n\n"
    rows = []
    for u in users:
        name = u.get("full_name") or u.get("username") or str(u["telegram_id"])
        ban = " 🚫" if u.get("is_banned") else ""
        rows.append([(f"{name}{ban} ({u['order_count']} سفارش)", f"adm_user_{u['telegram_id']}")])
    rows.append([("🔍 جستجو کاربر", "adm_user_search"), ("🔙 بازگشت", "adm_main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]),
        parse_mode="Markdown")


async def adm_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[2])
    user = get_user(user_id)
    if not user:
        await query.edit_message_text("❌ کاربر یافت نشد.", reply_markup=back_kb("adm_users"))
        return
    with get_db() as db:
        orders = db.execute("SELECT COUNT(*) as c FROM orders WHERE user_id=?", (user_id,)).fetchone()
        spent = db.execute("SELECT SUM(amount_rial) as s FROM payments WHERE user_id=? AND status='confirmed'",
                           (user_id,)).fetchone()
    text = (
        f"👤 *اطلاعات کاربر*\n\n"
        f"🆔 آیدی: `{user['telegram_id']}`\n"
        f"👤 نام: {user.get('full_name') or '—'}\n"
        f"🔖 یوزرنیم: @{user.get('username') or '—'}\n"
        f"📦 تعداد سفارش: `{orders['c']}`\n"
        f"💰 کل خرید: `{fmt_rial(spent['s'] or 0)}`\n"
        f"👛 موجودی: `{fmt_rial(user.get('balance_rial', 0))}`\n"
        f"🎁 تخفیف: `{user.get('discount_pct', 0)}%`\n"
        f"🚫 مسدود: {'بله' if user.get('is_banned') else 'خیر'}\n"
        f"📅 عضویت: {fmt_date(user.get('created_at', 0))}"
    )
    await query.edit_message_text(text, reply_markup=admin_user_detail_kb(user_id), parse_mode="Markdown")


async def adm_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[2])
    context.user_data["discount_user_id"] = user_id
    await query.edit_message_text(
        f"🎁 درصد تخفیف برای کاربر `{user_id}` را وارد کنید (0-100):",
        parse_mode="Markdown",
        reply_markup=back_kb(f"adm_user_{user_id}")
    )
    return SET_VALUE


async def adm_discount_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pct = int(update.message.text.strip())
        if not 0 <= pct <= 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد 0 تا 100 وارد کنید:")
        return SET_VALUE
    user_id = context.user_data.pop("discount_user_id")
    set_user_discount(user_id, pct)
    await update.message.reply_text(f"✅ تخفیف `{pct}%` برای کاربر `{user_id}` ثبت شد.",
                                    parse_mode="Markdown", reply_markup=back_kb("adm_users"))
    return ConversationHandler.END


async def adm_topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[2])
    context.user_data["topup_user_id"] = user_id
    await query.edit_message_text(
        f"💰 مبلغ شارژ کیف پول کاربر `{user_id}` (تومان):",
        parse_mode="Markdown", reply_markup=back_kb(f"adm_user_{user_id}"))
    return USER_TOPUP


async def adm_topup_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مبلغ معتبر وارد کنید:")
        return USER_TOPUP
    user_id = context.user_data.pop("topup_user_id")
    with get_db() as db:
        db.execute("UPDATE users SET balance_rial=balance_rial+? WHERE telegram_id=?", (amount, user_id))
    await update.message.reply_text(f"✅ `{fmt_rial(amount)}` به کیف پول کاربر `{user_id}` اضافه شد.",
                                    parse_mode="Markdown")
    try:
        await context.bot.send_message(user_id,
                                       f"💰 `{fmt_rial(amount)}` به کیف پول شما اضافه شد.",
                                       parse_mode="Markdown")
    except Exception:
        pass
    return ConversationHandler.END


async def adm_ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    action = parts[1]  # ban or unban
    user_id = int(parts[2])
    ban_user(user_id, action == "ban")
    status = "مسدود" if action == "ban" else "رفع مسدودی"
    await query.edit_message_text(f"✅ کاربر `{user_id}` {status} شد.",
                                  parse_mode="Markdown", reply_markup=back_kb("adm_users"))


# ─── PLANS ────────────────────────────────────────────────────────────────────
async def adm_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    with get_db() as db:
        plans = db.execute("""SELECT p.*, pn.name as panel_name FROM plans p
                               LEFT JOIN panels pn ON p.panel_id=pn.id ORDER BY p.price_rial""").fetchall()
    text = "📦 *پلن‌ها*\n\n"
    rows = []
    for p in plans:
        status = "✅" if p["is_active"] else "❌"
        rows.append([(f"{status} {p['name']} — {p['gb']}GB/{p['days']}روز — {fmt_rial(p['price_rial'])}",
                      f"adm_plan_detail_{p['id']}")])
    rows.append([("➕ پلن جدید", "adm_plan_add"), ("🔙 بازگشت", "adm_main")])
    await query.edit_message_text(text + (f"تعداد: {len(plans)}" if plans else "پلنی موجود نیست"),
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]),
                                  parse_mode="Markdown")


async def adm_plan_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[3])
    with get_db() as db:
        p = db.execute("SELECT p.*, pn.name as panel_name FROM plans p LEFT JOIN panels pn ON p.panel_id=pn.id WHERE p.id=?",
                       (plan_id,)).fetchone()
    if not p:
        await query.edit_message_text("❌ پلن یافت نشد.", reply_markup=back_kb("adm_plans"))
        return
    p = dict(p)
    text = (
        f"📦 *{p['name']}*\n\n"
        f"💾 حجم: `{p['gb']} GB`\n"
        f"📅 مدت: `{p['days']} روز`\n"
        f"💰 قیمت: `{fmt_rial(p['price_rial'])}`\n"
        f"🖥 پنل: `{p.get('panel_name') or '—'}`\n"
        f"وضعیت: {'✅ فعال' if p['is_active'] else '❌ غیرفعال'}"
    )
    await query.edit_message_text(text, reply_markup=admin_plan_kb(plan_id), parse_mode="Markdown")


async def adm_plan_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_plan"] = {}
    await query.edit_message_text("📦 *پلن جدید*\n\nنام پلن را وارد کنید:",
                                  parse_mode="Markdown", reply_markup=back_kb("adm_plans"))
    return ADD_PLAN_NAME


async def adm_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_plan"]["name"] = update.message.text.strip()
    await update.message.reply_text("حجم (GB) را وارد کنید:")
    return ADD_PLAN_GB


async def adm_plan_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_plan"]["gb"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ عدد وارد کنید:")
        return ADD_PLAN_GB
    await update.message.reply_text("مدت (روز) را وارد کنید:")
    return ADD_PLAN_DAYS


async def adm_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_plan"]["days"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return ADD_PLAN_DAYS
    await update.message.reply_text("قیمت (تومان) را وارد کنید:")
    return ADD_PLAN_PRICE


async def adm_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_plan"]["price_rial"] = int(update.message.text.strip().replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return ADD_PLAN_PRICE
    # Show panels
    with get_db() as db:
        panels = db.execute("SELECT id, name FROM panels WHERE is_active=1").fetchall()
    if not panels:
        await update.message.reply_text("❌ هیچ پنلی موجود نیست. ابتدا پنل اضافه کنید.",
                                        reply_markup=back_kb("adm_plans"))
        return ConversationHandler.END
    rows = [[InlineKeyboardButton(p["name"], callback_data=f"new_plan_panel_{p['id']}")] for p in panels]
    await update.message.reply_text("پنل را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(rows))
    return ADD_PLAN_PANEL


async def adm_plan_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    plan = context.user_data.pop("new_plan", {})
    plan["panel_id"] = panel_id
    with get_db() as db:
        db.execute("INSERT INTO plans(name,gb,days,price_rial,panel_id) VALUES(?,?,?,?,?)",
                   (plan["name"], plan["gb"], plan["days"], plan["price_rial"], plan["panel_id"]))
    await query.edit_message_text(f"✅ پلن *{plan['name']}* ایجاد شد!", parse_mode="Markdown",
                                  reply_markup=back_kb("adm_plans"))
    return ConversationHandler.END


async def adm_plan_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[3])
    with get_db() as db:
        db.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    await query.edit_message_text("✅ پلن حذف شد.", reply_markup=back_kb("adm_plans"))


# ─── PANELS ───────────────────────────────────────────────────────────────────
async def adm_panels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    with get_db() as db:
        panels = db.execute("SELECT * FROM panels ORDER BY id").fetchall()
    text = "🖥 *پنل‌ها*\n\n"
    rows = []
    for p in panels:
        status = "✅" if p["is_active"] else "❌"
        ptype = "سنایی" if p["type"] == "xui" else "مرزبان"
        rows.append([(f"{status} {p['name']} ({ptype})", f"adm_panel_detail_{p['id']}")])
    rows.append([("➕ پنل جدید", "adm_panel_add"), ("🔙 بازگشت", "adm_main")])
    await query.edit_message_text(text + (f"تعداد: {len(panels)}" if panels else "پنلی موجود نیست"),
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]),
                                  parse_mode="Markdown")


async def adm_panel_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    with get_db() as db:
        p = db.execute("SELECT * FROM panels WHERE id=?", (panel_id,)).fetchone()
    if not p:
        await query.edit_message_text("❌ پنل یافت نشد.", reply_markup=back_kb("adm_panels"))
        return
    p = dict(p)
    text = (
        f"🖥 *{p['name']}*\n\n"
        f"نوع: `{'سنایی (3x-ui)' if p['type']=='xui' else 'مرزبان'}`\n"
        f"آدرس: `{p['url']}`\n"
        f"مسیر: `{p.get('path') or '—'}`\n"
        f"وضعیت: {'✅ فعال' if p['is_active'] else '❌ غیرفعال'}"
    )
    await query.edit_message_text(text, reply_markup=admin_panel_action_kb(panel_id), parse_mode="Markdown")


async def adm_panel_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_panel"] = {}
    await query.edit_message_text("🖥 *پنل جدید*\n\nنام پنل را وارد کنید:",
                                  parse_mode="Markdown", reply_markup=back_kb("adm_panels"))
    return ADD_PANEL_NAME


async def adm_panel_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["name"] = update.message.text.strip()
    rows = [[InlineKeyboardButton("🖥 سنایی (3x-ui)", callback_data="ptype_xui"),
             InlineKeyboardButton("🔷 مرزبان", callback_data="ptype_marzban")]]
    await update.message.reply_text("نوع پنل را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(rows))
    return ADD_PANEL_TYPE


async def adm_panel_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ptype = query.data.split("_")[1]
    context.user_data["new_panel"]["type"] = ptype
    await query.edit_message_text("آدرس پنل را وارد کنید:\n_(مثال: http://1.2.3.4:8080)_",
                                  parse_mode="Markdown")
    return ADD_PANEL_URL


async def adm_panel_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["url"] = update.message.text.strip()
    ptype = context.user_data["new_panel"]["type"]
    if ptype == "xui":
        await update.message.reply_text("مسیر پنل را وارد کنید (Path):\n_(مثال: /secret123 یا خالی برای /)_")
        return ADD_PANEL_PATH
    else:
        context.user_data["new_panel"]["path"] = ""
        await update.message.reply_text("نام کاربری ادمین پنل:")
        return ADD_PANEL_USER


async def adm_panel_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["path"] = update.message.text.strip()
    await update.message.reply_text("نام کاربری ادمین پنل:")
    return ADD_PANEL_USER


async def adm_panel_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["username"] = update.message.text.strip()
    await update.message.reply_text("رمز عبور ادمین پنل:")
    return ADD_PANEL_PASS


async def adm_panel_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["password"] = update.message.text.strip()
    ptype = context.user_data["new_panel"]["type"]
    if ptype == "xui":
        await update.message.reply_text("شناسه Inbound (معمولاً 1):")
        return ADD_PANEL_IB
    else:
        await _save_panel(update, context)
        return ConversationHandler.END


async def adm_panel_ib(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_panel"]["inbound_id"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return ADD_PANEL_IB
    await _save_panel(update, context)
    return ConversationHandler.END


async def _save_panel(update, context):
    panel = context.user_data.pop("new_panel", {})
    with get_db() as db:
        db.execute("""INSERT INTO panels(name,type,url,path,username,password,inbound_id)
                      VALUES(?,?,?,?,?,?,?)""",
                   (panel["name"], panel["type"], panel["url"],
                    panel.get("path", ""), panel["username"], panel["password"],
                    panel.get("inbound_id", 1)))
    await update.message.reply_text(f"✅ پنل *{panel['name']}* اضافه شد!",
                                    parse_mode="Markdown", reply_markup=back_kb("adm_panels"))


async def adm_panel_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    with get_db() as db:
        panel = db.execute("SELECT * FROM panels WHERE id=?", (panel_id,)).fetchone()
    if not panel:
        await query.edit_message_text("❌ پنل یافت نشد.", reply_markup=back_kb("adm_panels"))
        return
    await query.edit_message_text("⏳ در حال ریستارت...")
    try:
        api = await get_panel_api(dict(panel))
        ok, msg = await api.restart()
        result = "✅ پنل ریستارت شد!" if ok else f"❌ خطا: {msg}"
    except Exception as e:
        result = f"❌ خطا: {e}"
    await query.edit_message_text(result, reply_markup=back_kb("adm_panels"))


async def adm_panel_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    with get_db() as db:
        db.execute("DELETE FROM panels WHERE id=?", (panel_id,))
    await query.edit_message_text("✅ پنل حذف شد.", reply_markup=back_kb("adm_panels"))


# ─── SALES ────────────────────────────────────────────────────────────────────
async def adm_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stats = get_sales_stats()
    text = (
        f"📊 *گزارش فروش*\n\n"
        f"💰 کل درآمد: `{fmt_rial(stats['total_rial'])}`\n"
        f"📦 کل سفارش: `{stats['total_count']}`\n"
        f"📅 امروز: `{fmt_rial(stats['today_rial'])}`\n"
        f"📆 این ماه: `{fmt_rial(stats['month_rial'])}`\n\n"
        f"*به تفکیک درگاه:*\n"
    )
    for gw in stats["by_gateway"]:
        text += f"• {gateway_name(gw['gateway'])}: `{fmt_rial(gw['total'])}` ({gw['cnt']} فقره)\n"
    await query.edit_message_text(text, reply_markup=back_kb("adm_main"), parse_mode="Markdown")


# ─── PAYMENTS ─────────────────────────────────────────────────────────────────
async def adm_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payments = get_pending_payments()
    if not payments:
        await query.edit_message_text("✅ هیچ پرداخت در انتظاری وجود ندارد.",
                                      reply_markup=back_kb("adm_main"))
        return
    rows = []
    for p in payments[:10]:
        name = p.get("full_name") or p.get("username") or str(p["user_id"])
        rows.append([(f"💳 {name} — {fmt_rial(p['amount_rial'])} — {gateway_name(p['gateway'])}",
                      f"adm_pay_detail_{p['id']}")])
    rows.append([("🔙 بازگشت", "adm_main")])
    await query.edit_message_text(f"💳 *پرداخت‌های در انتظار* ({len(payments)} مورد)",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]),
                                  parse_mode="Markdown")


async def adm_pay_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_id = int(query.data.split("_")[3])
    with get_db() as db:
        p = db.execute("""SELECT p.*, u.username, u.full_name FROM payments p
                           JOIN users u ON p.user_id=u.telegram_id WHERE p.id=?""", (payment_id,)).fetchone()
    if not p:
        await query.edit_message_text("❌ پرداخت یافت نشد.", reply_markup=back_kb("adm_payments"))
        return
    p = dict(p)
    text = (
        f"💳 *پرداخت #{payment_id}*\n\n"
        f"👤 کاربر: `{p['user_id']}` — {p.get('full_name') or '—'}\n"
        f"💰 مبلغ: `{fmt_rial(p['amount_rial'])}`\n"
        f"🌐 درگاه: {gateway_name(p['gateway'])}\n"
        f"📝 هش: `{p.get('tx_hash') or '—'}`\n"
        f"📅 تاریخ: {fmt_date(p['created_at'])}"
    )
    await query.edit_message_text(text, reply_markup=confirm_payment_kb(payment_id), parse_mode="Markdown")


async def adm_pay_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_id = int(query.data.split("_")[3])
    with get_db() as db:
        payment = dict(db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone())
        order = dict(db.execute("SELECT * FROM orders WHERE id=?", (payment["order_id"],)).fetchone())
        panel = dict(db.execute("SELECT * FROM panels WHERE id=?", (order["panel_id"],)).fetchone())

    from utils.helpers import make_email
    from services.order_service import activate_order
    email = make_email(order["user_id"], str(order.get("plan_id", "vpn")))
    try:
        api = await get_panel_api(panel)
        if panel["type"] == "xui":
            ok, result = await api.add_client(email, order["gb"], order["days"], panel.get("inbound_id", 1))
        else:
            ok, result = await api.add_user(email, order["gb"], order["days"])
        if ok:
            activate_order(order["id"], result.get("uuid", email), email, result.get("sub_link", ""))
            await confirm_payment(payment_id, payment.get("tx_hash"))
            sub_link = result.get("sub_link", "")
            await query.edit_message_text("✅ پرداخت تأیید و سرویس فعال شد.", reply_markup=back_kb("adm_payments"))
            try:
                await context.bot.send_message(
                    order["user_id"],
                    f"🎉 *سرویس شما فعال شد!*\n\n🔗 لینک اشتراک:\n`{sub_link}`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await query.edit_message_text(f"❌ خطا در پنل: {result}", reply_markup=back_kb("adm_payments"))
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {e}", reply_markup=back_kb("adm_payments"))


async def adm_pay_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_id = int(query.data.split("_")[3])
    with get_db() as db:
        p = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        db.execute("UPDATE payments SET status='failed' WHERE id=?", (payment_id,))
        if p:
            db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (p["order_id"],))
    await query.edit_message_text("❌ پرداخت رد شد.", reply_markup=back_kb("adm_payments"))
    if p:
        try:
            await context.bot.send_message(dict(p)["user_id"],
                                           "❌ متأسفانه پرداخت شما تأیید نشد.\nبا پشتیبانی تماس بگیرید.")
        except Exception:
            pass


# ─── SETTINGS ─────────────────────────────────────────────────────────────────
async def adm_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    usd = get_setting("usd_to_rial", "650000")
    ref = get_setting("referral_reward_rial", "50000")
    test = "✅" if get_setting("free_test_enabled") == "1" else "❌"
    text = (
        f"⚙️ *تنظیمات ربات*\n\n"
        f"💱 نرخ دلار: `{int(usd):,}` تومان\n"
        f"🎁 پاداش رفرال: `{fmt_rial(int(ref))}`\n"
        f"🧪 تست رایگان: {test}\n"
        f"📱 پشتیبانی: @{get_setting('support_username', '—')}\n"
    )
    await query.edit_message_text(text, reply_markup=admin_settings_kb(), parse_mode="Markdown")


_setting_keys = {
    "set_usd_rate": ("usd_to_rial", "💱 نرخ دلار به تومان را وارد کنید:"),
    "set_referral_reward": ("referral_reward_rial", "🎁 مبلغ پاداش رفرال (تومان):"),
    "set_usdt_addr": ("usdt_bep20_address", "💎 آدرس کیف USDT BEP20:"),
    "set_tron_addr": ("tron_address", "🔵 آدرس کیف USDT TRC20:"),
    "set_ton_addr": ("ton_address", "💎 آدرس کیف TON:"),
    "set_zarinpal": ("zarinpal_merchant", "🏦 کد مرچنت زرین‌پال:"),
    "set_support": ("support_username", "📱 یوزرنیم پشتیبانی (بدون @):"),
    "set_bot_name": ("bot_name", "🤖 نام ربات:"),
    "set_channel": ("channel_id", "📢 آیدی کانال (مثال: @channel):"),
    "set_free_test_gb": ("free_test_gb", "📦 حجم تست رایگان (GB):"),
    "set_free_test_days": ("free_test_days", "📅 مدت تست رایگان (روز):"),
}


async def adm_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data
    if key in ("set_free_test_on", "set_free_test_off"):
        val = "1" if key == "set_free_test_on" else "0"
        set_setting("free_test_enabled", val)
        await query.edit_message_text(f"{'✅ تست رایگان فعال شد' if val=='1' else '❌ تست رایگان غیرفعال شد'}",
                                      reply_markup=back_kb("adm_settings"))
        return ConversationHandler.END
    if key == "set_free_test":
        await query.edit_message_text("🧪 *تست رایگان*", reply_markup=free_test_admin_kb(), parse_mode="Markdown")
        return ConversationHandler.END
    if key not in _setting_keys:
        return ConversationHandler.END
    setting_key, prompt = _setting_keys[key]
    context.user_data["setting_key"] = setting_key
    await query.edit_message_text(prompt, reply_markup=back_kb("adm_settings"))
    return SET_VALUE


async def adm_setting_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.pop("setting_key", None)
    if not key:
        return ConversationHandler.END
    value = update.message.text.strip()
    set_setting(key, value)
    await update.message.reply_text(f"✅ تنظیم `{key}` ذخیره شد: `{value}`",
                                    parse_mode="Markdown", reply_markup=back_kb("adm_settings"))
    return ConversationHandler.END


# ─── ADMINS ───────────────────────────────────────────────────────────────────
async def adm_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    with get_db() as db:
        admins = db.execute("SELECT * FROM admins ORDER BY created_at").fetchall()
    text = "👨‍💼 *ادمین‌ها*\n\n"
    rows = []
    for a in admins:
        name = a["full_name"] or a["username"] or str(a["telegram_id"])
        rows.append([(f"🔴 حذف {name}", f"adm_del_admin_{a['telegram_id']}")])
    rows.append([("➕ افزودن ادمین", "adm_add_admin"), ("🔙 بازگشت", "adm_main")])
    await query.edit_message_text(
        text + (f"تعداد: {len(admins)}" if admins else "ادمینی موجود نیست"),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]),
        parse_mode="Markdown")


async def adm_add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ آیدی عددی تلگرام ادمین جدید را وارد کنید:",
        reply_markup=back_kb("adm_admins"))
    return ADD_ADMIN_ID


async def adm_add_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        admin_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ آیدی عددی وارد کنید:")
        return ADD_ADMIN_ID
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO admins(telegram_id, added_by) VALUES(?,?)",
                   (admin_id, update.effective_user.id))
    await update.message.reply_text(f"✅ ادمین `{admin_id}` اضافه شد.", parse_mode="Markdown",
                                    reply_markup=back_kb("adm_admins"))
    try:
        await context.bot.send_message(admin_id, "🎉 شما به عنوان ادمین ربات اضافه شدید!")
    except Exception:
        pass
    return ConversationHandler.END


async def adm_del_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = int(query.data.split("_")[3])
    with get_db() as db:
        db.execute("DELETE FROM admins WHERE telegram_id=?", (admin_id,))
    await query.edit_message_text(f"✅ ادمین `{admin_id}` حذف شد.", parse_mode="Markdown",
                                  reply_markup=back_kb("adm_admins"))


# ─── BROADCAST ────────────────────────────────────────────────────────────────
async def adm_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📢 *ارسال همگانی*\n\nپیام مورد نظر را وارد کنید:",
        parse_mode="Markdown", reply_markup=back_kb("adm_main"))
    return BROADCAST_MSG


async def adm_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    with get_db() as db:
        users = db.execute("SELECT telegram_id FROM users WHERE is_banned=0").fetchall()
    sent = failed = 0
    for u in users:
        try:
            await context.bot.send_message(u["telegram_id"], msg)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📢 ارسال همگانی تمام شد!\n✅ موفق: {sent}\n❌ ناموفق: {failed}",
        reply_markup=back_kb("adm_main"))
    return ConversationHandler.END


def _count_users():
    with get_db() as db:
        return db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🚫 لغو شد.", reply_markup=back_kb("adm_main"))
    else:
        await update.message.reply_text("🚫 لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END
