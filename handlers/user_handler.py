import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import get_setting, set_setting
from services.db_service import (
    upsert_user, get_user, get_user_orders, get_order, get_user_tickets,
    get_ticket, get_ticket_messages, create_ticket, add_ticket_message,
    get_admin_ids, is_admin, mark_free_test_used, create_order, activate_order,
    get_plans, get_panels
)
from services.panel_service import get_api
from keyboards.menus import (
    main_menu_kb, orders_kb, order_detail_kb, support_kb,
    my_tickets_kb, back_btn
)
from utils.helpers import fmt_rial, fmt_date, fmt_bytes, days_left, make_email, pct_bar
from handlers.common import require_not_banned, answer

logger = logging.getLogger(__name__)

# Conversation states
S_TICKET_SUBJECT = 300
S_TICKET_MSG = 301
S_TICKET_REPLY = 302


@require_not_banned
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    user = get_user(uid)
    if not user:
        return
    orders = get_user_orders(uid)
    active = sum(1 for o in orders if o["status"] == "active")
    total_spent = sum(o.get("price_paid", 0) for o in orders if o["status"] != "cancelled")

    from services.db_service import get_db
    from database import get_db as _db
    with _db() as db:
        ref_count = db.execute("SELECT COUNT(*) as c FROM referrals WHERE referrer_id=?", (uid,)).fetchone()["c"]

    text = (
        f"👤 *حساب کاربری*\n\n"
        f"🆔 آیدی: `{uid}`\n"
        f"👤 نام: {user.get('full_name') or '—'}\n"
        f"👛 موجودی: `{fmt_rial(user.get('balance_rial', 0))}`\n"
        f"🎁 تخفیف: `{user.get('discount_pct', 0)}%`\n"
        f"📦 سرویس فعال: `{active}`\n"
        f"💰 کل خرید: `{fmt_rial(total_spent)}`\n"
        f"👥 دعوت‌شده: `{ref_count}` نفر\n"
        f"📅 عضویت: {fmt_date(user.get('created_at', 0))}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 سرویس‌هایم", callback_data="my_orders"),
         InlineKeyboardButton("💳 کیف پول", callback_data="wallet")],
        [InlineKeyboardButton("🔙 منو اصلی", callback_data="main_menu")]
    ])
    await answer(update, text, kb)


@require_not_banned
async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    orders = get_user_orders(uid)
    if not orders:
        await answer(update, "📭 هنوز سرویسی ندارید.\nبرای خرید از منو اصلی اقدام کنید.", back_btn("main_menu"))
        return
    await answer(update, f"📦 *سرویس‌های من* ({len(orders)} سرویس):", orders_kb(orders))


@require_not_banned
async def order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    order = get_order(order_id)
    if not order or order["user_id"] != update.effective_user.id:
        await query.edit_message_text("❌ سفارش یافت نشد.", reply_markup=back_btn("my_orders"))
        return

    traffic_text = ""
    if order["status"] == "active" and order.get("client_uuid") and order.get("panel_id"):
        try:
            from services.db_service import get_panel
            panel = get_panel(order["panel_id"])
            if panel and panel["type"] == "xui":
                api = await get_api(panel)
                tr = await api.get_client_traffic(order["client_uuid"])
                if tr:
                    used = tr["up"] + tr["down"]
                    bar = pct_bar(used, tr["total"])
                    traffic_text = f"\n\n📊 مصرف: `{fmt_bytes(used)}` / `{fmt_bytes(tr['total'])}`\n`{bar}`"
        except Exception:
            pass

    e = {"active": "✅", "expired": "⏰", "pending": "⏳", "cancelled": "❌"}.get(order["status"], "❓")
    text = (
        f"{e} *سرویس #{order_id}*\n\n"
        f"📦 پلن: `{order.get('plan_name') or '—'}`\n"
        f"💾 حجم: `{order.get('gb', 0)} GB`\n"
        f"📅 مدت: `{order.get('days', 0)} روز`\n"
        f"⏰ انقضا: {days_left(order.get('expires_at', 0))}\n"
        f"💰 پرداخت: `{fmt_rial(order.get('price_paid', 0))}`"
        f"{traffic_text}"
    )
    if order.get("sub_link"):
        text += f"\n\n🔗 لینک اشتراک:\n`{order['sub_link']}`"

    await query.edit_message_text(
        text,
        reply_markup=order_detail_kb(order_id, order["status"] == "active"),
        parse_mode="Markdown"
    )


@require_not_banned
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    user = get_user(uid)
    balance = user.get("balance_rial", 0) if user else 0
    from database import get_db as _db
    with _db() as db:
        txs = db.execute(
            "SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (uid,)
        ).fetchall()
    hist = ""
    for t in txs:
        t = dict(t)
        e = "✅" if t["status"] == "confirmed" else "⏳" if t["status"] == "pending" else "❌"
        hist += f"\n{e} {fmt_rial(t['amount_rial'])} — {fmt_date(t['created_at'])}"
    text = f"💳 *کیف پول*\n\n💰 موجودی: `{fmt_rial(balance)}`\n\n*آخرین تراکنش‌ها:*{hist or chr(10) + '—'}"
    await query.edit_message_text(text, reply_markup=back_btn("my_account"), parse_mode="Markdown")


@require_not_banned
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref{uid}"
    reward = fmt_rial(int(get_setting("referral_reward_rial", "50000")))
    from database import get_db as _db
    with _db() as db:
        r = db.execute("SELECT COUNT(*) as c, SUM(reward_rial) as s FROM referrals WHERE referrer_id=?", (uid,)).fetchone()
    text = (
        f"👥 *دعوت دوستان*\n\n"
        f"🔗 لینک شما:\n`{link}`\n\n"
        f"🎁 پاداش هر دعوت: `{reward}`\n"
        f"👤 دعوت‌شده: `{r['c']}`\n"
        f"💰 کل پاداش: `{fmt_rial(r['s'] or 0)}`\n\n"
        f"⚡ پاداش پس از اولین خرید دوست شما ثبت می‌شود."
    )
    await query.edit_message_text(text, reply_markup=back_btn("main_menu"), parse_mode="Markdown")


@require_not_banned
async def free_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id

    if get_setting("free_test_enabled", "0") != "1":
        await query.edit_message_text("❌ تست رایگان غیرفعال است.", reply_markup=back_btn("main_menu"))
        return

    user = get_user(uid)
    if user and user.get("free_test_used"):
        await query.edit_message_text("⚠️ قبلاً از تست رایگان استفاده کرده‌اید.", reply_markup=back_btn("main_menu"))
        return

    panels = get_panels(active_only=True)
    if not panels:
        await query.edit_message_text("❌ پنلی فعال نیست.", reply_markup=back_btn("main_menu"))
        return

    gb = float(get_setting("free_test_gb", "1"))
    days = int(get_setting("free_test_days", "3"))
    panel = panels[0]

    await query.edit_message_text("⏳ در حال ساخت حساب تست...")
    try:
        api = await get_api(panel)
        email = make_email(uid, "test")
        if panel["type"] == "xui":
            ok, result = await api.add_client(email, gb, days, panel.get("inbound_id", 1))
        else:
            ok, result = await api.add_user(email, gb, days)

        if ok:
            mark_free_test_used(uid)
            order_id = create_order(uid, None, panel["id"], gb, days, 0)
            activate_order(order_id, result.get("uuid", email), email, result.get("sub_link", ""))
            sub = result.get("sub_link", "")
            text = (f"🎉 *تست رایگان فعال شد!*\n\n"
                    f"📦 حجم: `{gb} GB` | ⏱ مدت: `{days} روز`\n\n"
                    f"🔗 لینک اشتراک:\n`{sub}`")
        else:
            text = f"❌ خطا در پنل: {result}"
    except Exception as e:
        text = f"❌ خطا: {e}"

    await query.edit_message_text(text, reply_markup=back_btn("main_menu"), parse_mode="Markdown")


# ── SUPPORT / TICKETS ─────────────────────────────────────────────────────────

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sup = get_setting("support_username", "")
    text = "📞 *پشتیبانی*\n\n"
    if sup:
        text += f"تماس مستقیم: @{sup}\n\n"
    text += "یا تیکت باز کنید:"
    await query.edit_message_text(text, reply_markup=support_kb(), parse_mode="Markdown")


async def new_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎫 *تیکت جدید*\n\nموضوع را وارد کنید:",
        reply_markup=back_btn("support"), parse_mode="Markdown"
    )
    return S_TICKET_SUBJECT


async def ticket_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ticket_subject"] = update.message.text.strip()
    await update.message.reply_text("✏️ پیام خود را بنویسید:")
    return S_TICKET_MSG


async def ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = context.user_data.pop("ticket_subject", "—")
    msg = update.message.text.strip()
    uid = update.effective_user.id
    ticket_id = create_ticket(uid, subject)
    add_ticket_message(ticket_id, uid, msg, is_admin=False)
    await update.message.reply_text(
        f"✅ تیکت #{ticket_id} ثبت شد!\nبه زودی پاسخ می‌گیرید.",
        reply_markup=back_btn("support")
    )
    user = update.effective_user
    notify = (f"🎫 *تیکت جدید #{ticket_id}*\n"
              f"👤 [{user.full_name}](tg://user?id={user.id})\n"
              f"📋 موضوع: {subject}\n💬 {msg}")
    reply_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"💬 پاسخ به #{ticket_id}", callback_data=f"ticket_reply_{ticket_id}")
    ]])
    for aid in get_admin_ids():
        try:
            await context.bot.send_message(aid, notify, parse_mode="Markdown", reply_markup=reply_kb)
        except Exception:
            pass
    return ConversationHandler.END


async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    tickets = get_user_tickets(uid)
    if not tickets:
        await query.edit_message_text("📭 تیکتی ندارید.", reply_markup=back_btn("support"))
        return
    await query.edit_message_text("🎫 *تیکت‌های من*", reply_markup=my_tickets_kb(tickets), parse_mode="Markdown")


async def ticket_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split("_")[2])
    ticket = get_ticket(ticket_id)
    if not ticket or ticket["user_id"] != update.effective_user.id:
        await query.edit_message_text("❌ تیکت یافت نشد.", reply_markup=back_btn("my_tickets"))
        return
    msgs = get_ticket_messages(ticket_id)
    text = f"🎫 *تیکت #{ticket_id}*\n📋 موضوع: {ticket['subject']}\n\n"
    for m in msgs:
        sender = "👨‍💼 پشتیبانی" if m["is_admin"] else "👤 شما"
        text += f"*{sender}:*\n{m['message']}\n\n"
    await query.edit_message_text(text, reply_markup=back_btn("my_tickets"), parse_mode="Markdown")


async def admin_ticket_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split("_")[2])
    context.user_data["reply_ticket_id"] = ticket_id
    await query.edit_message_text(f"💬 پاسخ به تیکت #{ticket_id}:\n\nپیام را بنویسید:")
    return S_TICKET_REPLY


async def admin_ticket_reply_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = context.user_data.pop("reply_ticket_id", None)
    if not ticket_id:
        return ConversationHandler.END
    msg = update.message.text.strip()
    uid = update.effective_user.id
    add_ticket_message(ticket_id, uid, msg, is_admin=True)
    await update.message.reply_text(f"✅ پاسخ به تیکت #{ticket_id} ارسال شد.")
    ticket = get_ticket(ticket_id)
    if ticket:
        try:
            await context.bot.send_message(
                ticket["user_id"],
                f"📩 *پاسخ تیکت #{ticket_id}*\n\n{msg}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    return ConversationHandler.END
