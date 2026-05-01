import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

from database import get_db, get_setting
from services.user_service import get_user, get_user_orders, get_user_stats
from services.panel_service import get_panel_api
from keyboards.menus import (main_menu_kb, my_orders_kb, order_detail_kb,
                               support_kb, back_kb)
from utils.helpers import (fmt_rial, fmt_date, fmt_bytes, days_left,
                            status_emoji, pct_bar, make_email)
from config import Config

logger = logging.getLogger(__name__)

SUPPORT_SUBJECT = 200
SUPPORT_MSG = 201
TICKET_REPLY = 202


async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        return
    stats = get_user_stats(user_id)
    with get_db() as db:
        ref_count = db.execute(
            "SELECT COUNT(*) as c FROM referrals WHERE referrer_id=?", (user_id,)).fetchone()["c"]

    text = (
        f"👤 *حساب کاربری*\n\n"
        f"🆔 آیدی: `{user_id}`\n"
        f"👤 نام: {user.get('full_name') or '—'}\n"
        f"👛 موجودی: `{fmt_rial(user.get('balance_rial', 0))}`\n"
        f"🎁 تخفیف: `{user.get('discount_pct', 0)}%`\n"
        f"📦 سرویس‌های فعال: `{stats['active_orders']}`\n"
        f"💰 کل خرید: `{fmt_rial(stats['total_spent'])}`\n"
        f"👥 دعوت‌شدگان: `{ref_count}` نفر\n"
        f"📅 عضویت: {fmt_date(user.get('created_at', 0))}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 سرویس‌هایم", callback_data="my_orders"),
         InlineKeyboardButton("💳 کیف پول", callback_data="wallet")],
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]
    ])
    if query:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    orders = get_user_orders(user_id)
    if not orders:
        await query.edit_message_text(
            "📭 هنوز سرویسی خریداری نکرده‌اید.\nبرای خرید اولین سرویس، گزینه «خرید سرویس» را انتخاب کنید.",
            reply_markup=back_kb("main_menu"))
        return
    await query.edit_message_text(
        f"📦 *سرویس‌های من* ({len(orders)} سرویس)\n\nروی هر سرویس کلیک کنید:",
        reply_markup=my_orders_kb(orders), parse_mode="Markdown")


async def order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    with get_db() as db:
        order = db.execute("""SELECT o.*, p.name as plan_name, pn.name as panel_name, pn.type as panel_type
                               FROM orders o LEFT JOIN plans p ON o.plan_id=p.id
                               LEFT JOIN panels pn ON o.panel_id=pn.id
                               WHERE o.id=?""", (order_id,)).fetchone()
    if not order:
        await query.edit_message_text("❌ سفارش یافت نشد.", reply_markup=back_kb("my_orders"))
        return
    order = dict(order)
    status_e = status_emoji(order["status"])

    # Try to get live traffic
    traffic_text = ""
    if order["status"] == "active" and order.get("client_uuid") and order.get("panel_id"):
        try:
            with get_db() as db:
                panel = db.execute("SELECT * FROM panels WHERE id=?", (order["panel_id"],)).fetchone()
            if panel:
                api = await get_panel_api(dict(panel))
                if dict(panel)["type"] == "xui":
                    traffic = await api.get_client_traffic(order["client_uuid"])
                    if traffic:
                        used = traffic["up"] + traffic["down"]
                        total = traffic["total"]
                        bar = pct_bar(used, total)
                        traffic_text = (
                            f"\n📊 مصرف: `{fmt_bytes(used)}` از `{fmt_bytes(total)}`\n"
                            f"`{bar}`"
                        )
        except Exception:
            pass

    text = (
        f"{status_e} *سرویس #{order_id}*\n\n"
        f"📦 پلن: `{order.get('plan_name') or '—'}`\n"
        f"🖥 پنل: `{order.get('panel_name') or '—'}`\n"
        f"💾 حجم: `{order.get('gb', 0)} GB`\n"
        f"📅 مدت: `{order.get('days', 0)} روز`\n"
        f"⏰ انقضا: {days_left(order.get('expires_at', 0))}\n"
        f"💰 پرداخت: `{fmt_rial(order.get('price_paid', 0))}`"
        f"{traffic_text}\n"
    )
    if order.get("sub_link"):
        text += f"\n🔗 لینک اشتراک:\n`{order['sub_link']}`"

    await query.edit_message_text(text, reply_markup=order_detail_kb(order), parse_mode="Markdown")


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(update.effective_user.id)
    balance = user.get("balance_rial", 0) if user else 0
    with get_db() as db:
        payments = db.execute(
            "SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 5",
            (update.effective_user.id,)).fetchall()
    hist_text = "\n*آخرین تراکنش‌ها:*\n"
    for p in payments:
        p = dict(p)
        e = "✅" if p["status"] == "confirmed" else "⏳" if p["status"] == "pending" else "❌"
        hist_text += f"{e} {fmt_rial(p['amount_rial'])} — {fmt_date(p['created_at'])}\n"
    text = (
        f"💳 *کیف پول*\n\n"
        f"💰 موجودی: `{fmt_rial(balance)}`\n"
        f"{hist_text}"
    )
    await query.edit_message_text(text, reply_markup=back_kb("my_account"), parse_mode="Markdown")


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    bot_user = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_user.username}?start=ref{user_id}"
    reward = fmt_rial(int(get_setting("referral_reward_rial", "50000")))
    with get_db() as db:
        refs = db.execute("SELECT COUNT(*) as c, SUM(reward_rial) as s FROM referrals WHERE referrer_id=?",
                          (user_id,)).fetchone()

    text = (
        f"👥 *دعوت دوستان*\n\n"
        f"لینک دعوت شما:\n`{ref_link}`\n\n"
        f"🎁 به ازای هر دوست: `{reward}`\n"
        f"👤 تعداد دعوت‌شده: `{refs['c']}`\n"
        f"💰 کل درآمد رفرال: `{fmt_rial(refs['s'] or 0)}`\n\n"
        f"⚡ پاداش پس از اولین خرید دوست شما به حساب اضافه می‌شود."
    )
    await query.edit_message_text(text, reply_markup=back_kb("main_menu"), parse_mode="Markdown")


async def free_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not Config.free_test_enabled():
        await query.edit_message_text("❌ تست رایگان در حال حاضر غیرفعال است.",
                                      reply_markup=back_kb("main_menu"))
        return

    user = get_user(user_id)
    if user and user.get("free_test_used"):
        await query.edit_message_text("⚠️ شما قبلاً از تست رایگان استفاده کرده‌اید.",
                                      reply_markup=back_kb("main_menu"))
        return

    gb = Config.free_test_gb()
    days = Config.free_test_days()

    # Get first active panel
    with get_db() as db:
        panel = db.execute("SELECT * FROM panels WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
    if not panel:
        await query.edit_message_text("❌ در حال حاضر پنلی موجود نیست.",
                                      reply_markup=back_kb("main_menu"))
        return

    await query.edit_message_text("⏳ در حال ساخت حساب تست...")
    try:
        api = await get_panel_api(dict(panel))
        email = make_email(user_id, "test")
        if dict(panel)["type"] == "xui":
            ok, result = await api.add_client(email, gb, days, dict(panel).get("inbound_id", 1))
        else:
            ok, result = await api.add_user(email, gb, days)

        if ok:
            with get_db() as db:
                db.execute("UPDATE users SET free_test_used=1 WHERE telegram_id=?", (user_id,))
                db.execute("""INSERT INTO orders(user_id, panel_id, client_uuid, client_email, sub_link,
                                                  gb, days, price_paid, currency, status)
                               VALUES(?,?,?,?,?,?,?,0,'free','active')""",
                           (user_id, dict(panel)["id"], result.get("uuid", email), email,
                            result.get("sub_link", ""), gb, days))
            text = (
                f"🎉 *تست رایگان فعال شد!*\n\n"
                f"📦 حجم: `{gb} GB`\n"
                f"📅 مدت: `{days} روز`\n\n"
                f"🔗 لینک اشتراک:\n`{result.get('sub_link', '')}`"
            )
        else:
            text = f"❌ خطا در ساخت حساب تست:\n{result}"
    except Exception as e:
        text = f"❌ خطا: {e}"

    await query.edit_message_text(text, reply_markup=back_kb("main_menu"), parse_mode="Markdown")


# ─── SUPPORT ──────────────────────────────────────────────────────────────────
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    support_user = get_setting("support_username", "")
    text = "📞 *پشتیبانی*\n\n"
    if support_user:
        text += f"تماس مستقیم: @{support_user}\n\n"
    text += "یا تیکت جدید باز کنید:"
    await query.edit_message_text(text, reply_markup=support_kb(), parse_mode="Markdown")


async def new_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎫 *تیکت جدید*\n\nموضوع تیکت را وارد کنید:",
        parse_mode="Markdown", reply_markup=back_kb("support"))
    return SUPPORT_SUBJECT


async def ticket_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ticket_subject"] = update.message.text.strip()
    await update.message.reply_text("پیام خود را وارد کنید:")
    return SUPPORT_MSG


async def ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = context.user_data.pop("ticket_subject", "—")
    msg = update.message.text.strip()
    user_id = update.effective_user.id
    with get_db() as db:
        cur = db.execute("INSERT INTO tickets(user_id, subject) VALUES(?,?)", (user_id, subject))
        ticket_id = cur.lastrowid
        db.execute("INSERT INTO ticket_messages(ticket_id, sender_id, message) VALUES(?,?,?)",
                   (ticket_id, user_id, msg))
    await update.message.reply_text(
        f"✅ تیکت #{ticket_id} ثبت شد!\nبه زودی پاسخ داده می‌شود.",
        reply_markup=back_kb("support"))
    # Notify admins
    with get_db() as db:
        admins = db.execute("SELECT telegram_id FROM admins").fetchall()
    user = update.effective_user
    notify = (
        f"🎫 *تیکت جدید #{ticket_id}*\n"
        f"👤 [{user.full_name}](tg://user?id={user.id})\n"
        f"📋 موضوع: {subject}\n"
        f"💬 {msg}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"💬 پاسخ #{ticket_id}", callback_data=f"ticket_reply_{ticket_id}")]])
    for a in admins:
        try:
            await context.bot.send_message(a["telegram_id"], notify, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass
    return ConversationHandler.END


async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    with get_db() as db:
        tickets = db.execute(
            "SELECT * FROM tickets WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
            (user_id,)).fetchall()
    if not tickets:
        await query.edit_message_text("📭 تیکتی ندارید.", reply_markup=back_kb("support"))
        return
    rows = []
    for t in tickets:
        e = {"open": "🟡", "answered": "🟢", "closed": "⚫"}.get(t["status"], "❓")
        rows.append([(f"{e} #{t['id']} — {t['subject']}", f"ticket_view_{t['id']}")])
    rows.append([("🔙 بازگشت", "support")])
    await query.edit_message_text("🎫 *تیکت‌های من*",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]),
                                  parse_mode="Markdown")


async def ticket_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split("_")[2])
    with get_db() as db:
        ticket = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        messages = db.execute(
            "SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY created_at", (ticket_id,)).fetchall()
    if not ticket:
        await query.edit_message_text("❌ تیکت یافت نشد.", reply_markup=back_kb("my_tickets"))
        return
    text = f"🎫 *تیکت #{ticket_id}*\nموضوع: {ticket['subject']}\n\n"
    for m in messages:
        sender = "پشتیبانی 👨‍💼" if m["is_admin"] else "شما 👤"
        text += f"*{sender}:*\n{m['message']}\n\n"
    await query.edit_message_text(text, reply_markup=back_kb("my_tickets"), parse_mode="Markdown")


# ─── ADMIN TICKET REPLY ────────────────────────────────────────────────────────
async def admin_ticket_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split("_")[2])
    context.user_data["reply_ticket_id"] = ticket_id
    await query.edit_message_text(f"💬 پاسخ به تیکت #{ticket_id}:\n\nپیام خود را وارد کنید:")
    return TICKET_REPLY


async def admin_ticket_reply_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = context.user_data.pop("reply_ticket_id", None)
    if not ticket_id:
        return ConversationHandler.END
    reply_msg = update.message.text.strip()
    with get_db() as db:
        ticket = dict(db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone())
        db.execute("INSERT INTO ticket_messages(ticket_id, sender_id, is_admin, message) VALUES(?,?,1,?)",
                   (ticket_id, update.effective_user.id, reply_msg))
        db.execute("UPDATE tickets SET status='answered' WHERE id=?", (ticket_id,))
    await update.message.reply_text(f"✅ پاسخ به تیکت #{ticket_id} ارسال شد.")
    try:
        await context.bot.send_message(
            ticket["user_id"],
            f"📩 *پاسخ تیکت #{ticket_id}*\n\n{reply_msg}",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    return ConversationHandler.END
