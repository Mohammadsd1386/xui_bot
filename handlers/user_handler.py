import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import get_setting, set_setting
from services.db_service import (
    upsert_user, get_user, get_user_orders, get_order, get_plan, get_user_tickets,
    get_ticket, get_ticket_messages, create_ticket, add_ticket_message,
    get_admin_ids, is_admin, mark_free_test_used, create_order, activate_order,
    get_plans, get_panels, create_wallet_request, create_payment
)
from services.panel_service import get_api
from keyboards.menus import (
    main_menu_kb, orders_kb, order_detail_kb, support_kb,
    my_tickets_kb, back_btn
)
from utils.helpers import (
    fmt_rial, fmt_date, fmt_bytes, days_left, make_email, pct_bar,
    gateway_label, effective_usdt_rate_toman,
)
from utils.service_delivery import send_activation_to_user
from handlers.common import require_not_banned, answer

logger = logging.getLogger(__name__)

# Conversation states
S_TICKET_SUBJECT = 300
S_TICKET_MSG = 301
S_TICKET_REPLY = 302
S_WALLET_REQ = 303
S_WALLET_DEST = 304


@require_not_banned
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    upsert_user(uid, update.effective_user.username, update.effective_user.full_name)
    user = get_user(uid)
    if not user:
        await answer(update, "❌ خطا در بارگذاری پروفایل. یک بار /start بزنید.", back_btn("main_menu"),
                     edit=bool(update.callback_query))
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
    last_online_text = "—"
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
                    lo = int((tr.get("last_online") or 0) / 1000)
                    if lo > 0:
                        last_online_text = fmt_date(lo)
        except Exception:
            pass

    e = {"active": "✅", "expired": "⏰", "pending": "⏳", "cancelled": "❌"}.get(order["status"], "❓")
    text = (
        f"{e} *سرویس #{order_id}*\n\n"
        f"📦 پلن: `{order.get('plan_name') or '—'}`\n"
        f"🏷 نام کانفیگ: `{order.get('config_name') or order.get('client_email') or '—'}`\n"
        f"💾 حجم: `{order.get('gb', 0)} GB`\n"
        f"📅 مدت: `{order.get('days', 0)} روز`\n"
        f"⏰ انقضا: {days_left(order.get('expires_at', 0))}\n"
        f"💰 پرداخت: `{fmt_rial(order.get('price_paid', 0))}`\n"
        f"🕒 آخرین اتصال: `{last_online_text}`"
        f"{traffic_text}"
    )
    if order.get("sub_link"):
        text += f"\n\n🔗 لینک اشتراک:\n`{order['sub_link']}`"

    await query.edit_message_text(
        text,
        reply_markup=order_detail_kb(order_id, order["status"] == "active"),
        parse_mode="Markdown"
    )
    if order.get("sub_link"):
        qr = f"https://api.qrserver.com/v1/create-qr-code/?size=512x512&data={order['sub_link']}"
        try:
            await query.message.reply_photo(qr, caption="📱 QR Code کانفیگ شما")
        except Exception:
            pass


@require_not_banned
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    upsert_user(uid, update.effective_user.username, update.effective_user.full_name)
    user = get_user(uid)
    balance = user.get("balance_rial", 0) if user else 0
    from database import get_db as _db
    with _db() as db:
        txs = db.execute(
            "SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (uid,)
        ).fetchall()
        wrs = db.execute(
            "SELECT type, amount_rial, status, created_at FROM wallet_requests "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT 5",
            (uid,),
        ).fetchall()
    hist = ""
    for t in txs:
        t = dict(t)
        e = "✅" if t["status"] == "confirmed" else "⏳" if t["status"] == "pending" else "❌"
        hist += f"\n{e} {fmt_rial(t['amount_rial'])} — {fmt_date(t['created_at'])}"
    wr_hist = ""
    for w in wrs:
        w = dict(w)
        lab = "شارژ" if w["type"] == "deposit" else "برداشت"
        e = "✅" if w["status"] == "approved" else "⏳" if w["status"] == "pending" else "❌"
        wr_hist += f"\n{e} {lab} {fmt_rial(w['amount_rial'])} — {fmt_date(w['created_at'])}"
    text = (
        f"💳 *کیف پول*\n\n"
        f"💰 موجودی: `{fmt_rial(balance)}`\n\n"
        f"*آخرین پرداخت‌ها (خرید):*{hist or chr(10) + '—'}"
        f"\n\n*درخواست‌های کیف:*{wr_hist or chr(10) + '—'}\n\n"
        f"برای شارژ/برداشت درخواست ثبت کنید:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ درخواست شارژ", callback_data="wallet_deposit"),
         InlineKeyboardButton("➖ درخواست برداشت", callback_data="wallet_withdraw")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="my_account")]
    ])
    if query:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


@require_not_banned
async def wallet_deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["wallet_req_type"] = "deposit"
    await query.edit_message_text(
        "➕ مبلغ شارژ درخواستی را به تومان وارد کنید:",
        reply_markup=back_btn("wallet")
    )
    return S_WALLET_REQ


@require_not_banned
async def wallet_withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["wallet_req_type"] = "withdraw"
    await query.edit_message_text(
        "➖ مبلغ برداشت درخواستی را به تومان وارد کنید:",
        reply_markup=back_btn("wallet")
    )
    return S_WALLET_REQ


@require_not_banned
async def wallet_req_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req_type = context.user_data.get("wallet_req_type", "")
    if req_type not in ("deposit", "withdraw"):
        await update.message.reply_text("❌ درخواست منقضی شده. دوباره از بخش کیف پول اقدام کنید.")
        return ConversationHandler.END
    try:
        amount = int((update.message.text or "").strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مبلغ معتبر وارد کنید:")
        return S_WALLET_REQ
    uid = update.effective_user.id
    if req_type == "withdraw":
        context.user_data["wallet_withdraw_amount"] = amount
        await update.message.reply_text(
            "💳 لطفا شماره کارت یا آدرس ولت مقصد را ارسال کنید:",
            reply_markup=back_btn("wallet"),
        )
        return S_WALLET_DEST

    req_id = create_wallet_request(uid, "deposit", amount, note="awaiting_payment")
    context.user_data.pop("wallet_req_type", None)
    await update.message.reply_text(
        f"🧾 درخواست شارژ ثبت شد.\n"
        f"🆔 شناسه درخواست: `{req_id}`\n"
        f"💰 مبلغ: `{fmt_rial(amount)}`\n\n"
        f"حالا روش پرداخت را انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 زرین‌پال", callback_data=f"wpay_zarinpal_{req_id}")],
            [InlineKeyboardButton("🏦 کارت به کارت", callback_data=f"wpay_card2card_{req_id}")],
            [InlineKeyboardButton("💎 تتر BEP20", callback_data=f"wpay_usdt_{req_id}"),
             InlineKeyboardButton("🔵 ترون TRC20", callback_data=f"wpay_tron_{req_id}")],
            [InlineKeyboardButton("🪙 تون کوین", callback_data=f"wpay_ton_{req_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet")],
        ]),
    )
    return ConversationHandler.END


@require_not_banned
async def wallet_req_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req_type = context.user_data.pop("wallet_req_type", "")
    amount = context.user_data.pop("wallet_withdraw_amount", None)
    if req_type != "withdraw" or not amount:
        await update.message.reply_text("❌ درخواست منقضی شده. دوباره از بخش کیف پول اقدام کنید.")
        return ConversationHandler.END
    destination = (update.message.text or "").strip()
    if len(destination) < 8:
        context.user_data["wallet_req_type"] = "withdraw"
        context.user_data["wallet_withdraw_amount"] = amount
        await update.message.reply_text("❌ شماره کارت/ولت معتبر وارد کنید:")
        return S_WALLET_DEST
    uid = update.effective_user.id
    req_id = create_wallet_request(uid, "withdraw", int(amount), note=f"destination:{destination}")
    await update.message.reply_text(
        f"✅ درخواست برداشت ثبت شد.\n"
        f"🆔 شناسه: `{req_id}`\n"
        f"💰 مبلغ: `{fmt_rial(amount)}`\n"
        f"🏦 مقصد: `{destination}`\n"
        f"پس از تایید ادمین انجام می‌شود.",
        parse_mode="Markdown",
        reply_markup=back_btn("wallet"),
    )
    for aid in get_admin_ids():
        try:
            await context.bot.send_message(
                aid,
                f"👛 درخواست برداشت جدید\n"
                f"🆔 `{req_id}` | کاربر `{uid}`\n"
                f"مبلغ: {fmt_rial(amount)}\n"
                f"مقصد: `{destination}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("مشاهده", callback_data=f"adm_wr_{req_id}")
                ]]),
            )
        except Exception:
            pass
    return ConversationHandler.END


@require_not_banned
async def wallet_conv_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خروج تمیز از state کیف پول و هدایت به مقصد انتخابی."""
    context.user_data.pop("wallet_req_type", None)
    context.user_data.pop("wallet_withdraw_amount", None)
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    target = query.data or "wallet"
    if target == "wallet":
        await wallet(update, context)
    elif target == "my_account":
        await my_account(update, context)
    else:
        await query.answer()
    return ConversationHandler.END


@require_not_banned
async def wallet_req_text_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    اگر کاربر در حالت دریافت مبلغ/مقصد کیف پول روی دکمه‌های متنی منوی اصلی زد،
    کانورسیشن را تمیز ببند تا دیگر خطای «مبلغ معتبر» تکرار نشود.
    """
    context.user_data.pop("wallet_req_type", None)
    context.user_data.pop("wallet_withdraw_amount", None)
    await update.message.reply_text("↩️ عملیات کیف پول لغو شد. از منو ادامه دهید.")
    return ConversationHandler.END


@require_not_banned
async def wallet_pay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    gateway = parts[1]
    req_id = int(parts[2])
    uid = query.from_user.id
    from database import get_db
    with get_db() as db:
        req = db.execute(
            "SELECT * FROM wallet_requests WHERE id=? AND user_id=? AND status='pending'",
            (req_id, uid),
        ).fetchone()
    if not req:
        await query.edit_message_text("❌ درخواست معتبر نیست یا قبلا رسیدگی شده.", reply_markup=back_btn("wallet"))
        return
    req = dict(req)
    amount = int(req["amount_rial"])
    if gateway == "zarinpal":
        merchant = get_setting("zarinpal_merchant", "")
        if not merchant:
            await query.edit_message_text("❌ زرین‌پال هنوز تنظیم نشده.", reply_markup=back_btn("wallet"))
            return
        from services.payment_service import ZarinPalService
        zp = ZarinPalService(merchant)
        callback = get_setting("zarinpal_callback", "https://t.me/your_bot")
        ok, url_or_err, authority = await zp.request(amount, f"شارژ کیف #{req_id}", callback)
        if not ok:
            await query.edit_message_text(f"❌ خطای زرین‌پال:\n{url_or_err}", reply_markup=back_btn("wallet"))
            return
        pay_id = create_payment(uid, None, amount, "zarinpal")
        with get_db() as db:
            db.execute("UPDATE payments SET currency='wallet_deposit', tx_hash=? WHERE id=?",
                       (f"WR:{req_id}|AUTH:{authority}", pay_id))
        await query.edit_message_text(
            f"🏦 *زرین‌پال شارژ کیف*\n"
            f"💰 مبلغ: `{fmt_rial(amount)}`\n\n"
            f"پس از پرداخت، اگر خودکار ثبت نشد رسید را ارسال کنید.\n"
            f"🆔 شناسه پرداخت: `{pay_id}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 پرداخت آنلاین", url=url_or_err)],
                [InlineKeyboardButton("✅ پرداخت کردم", callback_data=f"crypto_paid_{pay_id}")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet")],
            ]),
        )
        return

    enabled_map = {
        "card2card": "pay_card2card_enabled",
        "usdt": "pay_usdt_enabled",
        "tron": "pay_tron_enabled",
        "ton": "pay_ton_enabled",
    }
    if get_setting(enabled_map.get(gateway, ""), "1") != "1":
        await query.edit_message_text("❌ این روش پرداخت غیرفعال است.", reply_markup=back_btn("wallet"))
        return

    pay_id = create_payment(uid, None, amount, gateway)
    with get_db() as db:
        db.execute("UPDATE payments SET currency='wallet_deposit', tx_hash=? WHERE id=?", (f"WR:{req_id}", pay_id))

    if gateway == "card2card":
        card_no = get_setting("card2card_number", "")
        card_holder = get_setting("card2card_holder", "")
        if not card_no:
            await query.edit_message_text("❌ شماره کارت هنوز تنظیم نشده.", reply_markup=back_btn("wallet"))
            return
        await query.edit_message_text(
            "🏦 *شارژ کیف با کارت‌به‌کارت*\n\n"
            f"💰 مبلغ: `{fmt_rial(amount)}`\n"
            f"💳 شماره کارت: `{card_no}`\n"
            f"👤 صاحب کارت: `{card_holder or '—'}`\n\n"
            f"🆔 شناسه پرداخت: `{pay_id}`\n"
            "پس از واریز، رسید یا شماره پیگیری را ارسال کنید.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ پرداخت کردم", callback_data=f"crypto_paid_{pay_id}")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet")],
            ]),
        )
        return

    usd_rate = effective_usdt_rate_toman()
    price_usd = round(amount / usd_rate, 4)
    wallets = {
        "usdt": (get_setting("usdt_bep20_address"), "BEP20 (BSC)", "USDT", price_usd),
        "tron": (get_setting("tron_address"), "TRC20 (Tron)", "USDT", price_usd),
        "ton": (
            get_setting("ton_address"), "TON Network", "TON",
            round(price_usd / float(get_setting("ton_price_usd", "3.5")), 4),
        ),
    }
    addr, network, coin, amt = wallets.get(gateway, ("", "", "", 0))
    if not addr:
        await query.edit_message_text("❌ این درگاه تنظیم نشده است.", reply_markup=back_btn("wallet"))
        return
    memo = get_setting("ton_memo", "")
    memo_text = f"\n📝 Memo: `{memo}`" if gateway == "ton" and memo else ""
    await query.edit_message_text(
        f"💳 *{gateway_label(gateway)} — شارژ کیف*\n\n"
        f"💰 مبلغ: `{amt} {coin}`\n"
        f"🌐 شبکه: `{network}`\n"
        f"📍 آدرس واریز:\n`{addr}`{memo_text}\n\n"
        f"🆔 شناسه پرداخت: `{pay_id}`\n"
        "پس از پرداخت، هش یا رسید را ارسال کنید.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ پرداخت کردم", callback_data=f"crypto_paid_{pay_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet")],
        ]),
    )


@require_not_banned
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
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
    if query:
        await query.edit_message_text(text, reply_markup=back_btn("main_menu"), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=back_btn("main_menu"), parse_mode="Markdown")


@require_not_banned
async def free_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id

    async def _out(msg: str, kb=back_btn("main_menu")):
        if query:
            await query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")

    if query:
        await query.answer()

    if get_setting("free_test_enabled", "0") != "1":
        await _out("❌ تست رایگان غیرفعال است.")
        return

    user = get_user(uid)
    if user and user.get("free_test_used"):
        await _out("⚠️ قبلاً از تست رایگان استفاده کرده‌اید.")
        return

    panels = get_panels(active_only=True)
    if not panels:
        await _out("❌ پنلی فعال نیست.")
        return

    gb = float(get_setting("free_test_gb", "1"))
    days = int(get_setting("free_test_days", "3"))
    panel = panels[0]

    await _out("⏳ در حال ساخت حساب تست...")
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
            refreshed = get_order(order_id) or {}
            cli_uuid = result.get("uuid", email)
            tr = None
            if panel["type"] == "xui" and cli_uuid:
                tr = await api.get_client_traffic(cli_uuid)
            await _out("✅ تست رایگان فعال شد.\n📩 جزئیات کامل + QR در پیام بعدی ارسال شد.")
            await send_activation_to_user(
                context.bot, uid, refreshed,
                plan_name="🧪 تست رایگان",
                sub_link=sub or "",
                client_uuid=str(cli_uuid),
                traffic=tr,
                title="تست رایگان فعال شد ✨",
            )
            return
        else:
            text = f"❌ خطا در پنل: {result}"
    except Exception as e:
        text = f"❌ خطا: {e}"

    await _out(text)


# ── SUPPORT / TICKETS ─────────────────────────────────────────────────────────

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    sup = get_setting("support_username", "")
    text = "📞 *پشتیبانی*\n\n"
    if sup:
        text += f"تماس مستقیم: @{sup}\n\n"
    text += "یا تیکت باز کنید:"
    if query:
        await query.edit_message_text(text, reply_markup=support_kb(), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=support_kb(), parse_mode="Markdown")


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
