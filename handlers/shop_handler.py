import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import get_setting
from services.db_service import (
    get_plans, get_plan, get_panel, create_order, activate_order,
    create_payment, confirm_payment, pay_from_balance, get_admin_ids, get_user
)
from services.panel_service import get_api
from keyboards.menus import plans_kb, payment_kb, back_btn, crypto_paid_kb
from utils.helpers import fmt_rial, apply_discount, make_email, gateway_label

logger = logging.getLogger(__name__)

S_EXTEND_VAL = 400


async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    plans = get_plans(active_only=True)
    text = "🛍 *پلن‌های موجود*\n\nپلن مورد نظر را انتخاب کنید:"
    kb = plans_kb(plans) if plans else back_btn("main_menu")
    if not plans:
        text = "😔 پلنی موجود نیست."
    if query:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[1])
    plan = get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ پلن یافت نشد.", reply_markup=back_btn("shop"))
        return

    user = get_user(query.from_user.id)
    discount = user.get("discount_pct", 0) if user else 0
    final_price = apply_discount(plan["price_rial"], discount)
    usd = round(final_price / int(get_setting("usd_to_rial", "650000")), 2)

    text = (
        f"📦 *{plan['name']}*\n\n"
        f"🔹 حجم: `{plan['gb']} GB`\n"
        f"🔹 مدت: `{plan['days']} روز`\n"
        f"🔹 قیمت: `{fmt_rial(plan['price_rial'])}`\n"
    )
    if discount > 0:
        text += f"🎁 تخفیف `{discount}%` → قیمت نهایی: `{fmt_rial(final_price)}`\n"
    text += f"💱 معادل: `{usd} USDT`\n\n💳 روش پرداخت را انتخاب کنید:"

    order_id = create_order(
        query.from_user.id, plan_id, plan["panel_id"],
        plan["gb"], plan["days"], final_price
    )
    context.user_data["pending_order"] = order_id
    balance = user.get("balance_rial", 0) if user else 0
    await query.edit_message_text(text, reply_markup=payment_kb(order_id, balance), parse_mode="Markdown")


async def pay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # parse: pay_<gateway>_<order_id>
    parts = query.data.split("_")
    gateway = parts[1]
    order_id = int(parts[2])

    from database import get_db
    with get_db() as db:
        order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        await query.edit_message_text("❌ سفارش یافت نشد.", reply_markup=back_btn("shop"))
        return
    order = dict(order)
    if order["user_id"] != query.from_user.id:
        await query.edit_message_text("❌ دسترسی ندارید.", reply_markup=back_btn("shop"))
        return

    amount = order["price_paid"]

    # Balance payment
    if gateway == "balance":
        if not pay_from_balance(query.from_user.id, amount):
            await query.edit_message_text("❌ موجودی کیف پول کافی نیست.",
                                          reply_markup=payment_kb(order_id))
            return
        pay_id = create_payment(query.from_user.id, order_id, amount, "balance")
        await _do_activate(query, context, order, pay_id)
        return

    # ZarinPal
    if gateway == "zarinpal":
        await _zarinpal(query, context, order, amount)
        return

    # Crypto
    usd_rate = int(get_setting("usd_to_rial", "650000"))
    price_usd = round(amount / usd_rate, 4)

    wallets = {
        "usdt": (get_setting("usdt_bep20_address"), "BEP20 (BSC)", "USDT", price_usd),
        "tron": (get_setting("tron_address"), "TRC20 (Tron)", "USDT", price_usd),
        "ton": (
            get_setting("ton_address"), "TON Network", "TON",
            round(price_usd / float(get_setting("ton_price_usd", "3.5")), 4)
        ),
    }
    addr, network, coin, amt = wallets.get(gateway, ("", "", "", 0))
    if not addr:
        await query.edit_message_text("❌ این درگاه تنظیم نشده است.", reply_markup=back_btn("shop"))
        return

    pay_id = create_payment(query.from_user.id, order_id, amount, gateway)

    memo = get_setting("ton_memo", "")
    memo_text = f"\n📝 Memo: `{memo}`" if gateway == "ton" and memo else ""

    text = (
        f"💳 *{gateway_label(gateway)}*\n\n"
        f"💰 مبلغ: `{amt} {coin}`\n"
        f"🌐 شبکه: `{network}`\n"
        f"📍 آدرس واریز:\n`{addr}`{memo_text}\n\n"
        f"⚠️ پس از واریز، هش تراکنش یا رسید ارسال کنید.\n"
        f"🆔 شناسه پرداخت: `{pay_id}`"
    )
    await query.edit_message_text(text, reply_markup=crypto_paid_kb(pay_id), parse_mode="Markdown")
    context.user_data[f"pay_{pay_id}_order"] = order_id


async def crypto_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pay_id = int(query.data.split("_")[2])
    context.user_data["awaiting_hash_for"] = pay_id
    await query.edit_message_text(
        f"📋 هش تراکنش یا تصویر رسید را ارسال کنید:\n🆔 شناسه: `{pay_id}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 لغو", callback_data="shop")]])
    )


async def receive_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pay_id = context.user_data.pop("awaiting_hash_for", None)
    if not pay_id:
        return
    tx = update.message.text.strip() if update.message.text else "رسید تصویری"
    from database import get_db
    with get_db() as db:
        db.execute("UPDATE payments SET tx_hash=? WHERE id=?", (tx, pay_id))
        pay = dict(db.execute("SELECT * FROM payments WHERE id=?", (pay_id,)).fetchone())

    await update.message.reply_text(
        f"✅ رسید دریافت شد!\n🆔 شناسه: `{pay_id}`\nپس از تأیید ادمین، سرویس فعال می‌شود.",
        parse_mode="Markdown"
    )
    user = update.effective_user
    notify = (
        f"💳 *پرداخت جدید — شناسه #{pay_id}*\n\n"
        f"👤 [{user.full_name}](tg://user?id={user.id}) (`{user.id}`)\n"
        f"💰 مبلغ: `{fmt_rial(pay['amount_rial'])}`\n"
        f"🌐 درگاه: {gateway_label(pay['gateway'])}\n"
        f"📝 هش: `{tx}`"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"adm_pay_ok_{pay_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"adm_pay_no_{pay_id}")
    ]])
    for aid in get_admin_ids():
        try:
            await context.bot.send_message(aid, notify, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass


async def _zarinpal(query, context, order, amount):
    merchant = get_setting("zarinpal_merchant", "")
    if not merchant:
        await query.edit_message_text("❌ زرین‌پال هنوز تنظیم نشده.", reply_markup=back_btn("shop"))
        return
    from services.payment_service import ZarinPalService
    zp = ZarinPalService(merchant)
    callback = get_setting("zarinpal_callback", "https://t.me/your_bot")
    ok, url_or_err, authority = await zp.request(amount, f"خرید VPN #{order['id']}", callback)
    if ok:
        pay_id = create_payment(query.from_user.id, order["id"], amount, "zarinpal")
        from database import get_db
        with get_db() as db:
            db.execute("UPDATE payments SET tx_hash=? WHERE id=?", (authority, pay_id))
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 پرداخت آنلاین", url=url_or_err)],
            [InlineKeyboardButton("🚫 لغو", callback_data="shop")]
        ])
        await query.edit_message_text(
            f"🏦 *زرین‌پال*\nمبلغ: `{fmt_rial(amount)}`\n\nروی دکمه زیر کلیک کنید:",
            reply_markup=kb, parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(f"❌ خطای زرین‌پال:\n{url_or_err}", reply_markup=back_btn("shop"))


async def _do_activate(query_or_ctx, context, order, pay_id):
    """Create client on panel and finalize order."""
    panel = get_panel(order["panel_id"])
    if not panel:
        text = "❌ پنل یافت نشد. با پشتیبانی تماس بگیرید."
        if hasattr(query_or_ctx, "edit_message_text"):
            await query_or_ctx.edit_message_text(text)
        return

    email = make_email(order["user_id"], str(order.get("plan_id", "vpn")))
    try:
        api = await get_api(panel)
        if panel["type"] == "xui":
            ok, result = await api.add_client(email, order["gb"], order["days"], panel.get("inbound_id", 1))
        else:
            ok, result = await api.add_user(email, order["gb"], order["days"])

        if ok:
            activate_order(order["id"], result.get("uuid", email), email, result.get("sub_link", ""))
            confirm_payment(pay_id)
            sub = result.get("sub_link", "")
            text = (
                f"🎉 *سرویس فعال شد!*\n\n"
                f"📦 حجم: `{order['gb']} GB` | ⏱ `{order['days']} روز`\n\n"
                f"🔗 لینک اشتراک:\n`{sub}`"
            )
        else:
            text = f"❌ خطا در پنل: {result}"
    except Exception as e:
        text = f"❌ خطا: {e}"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📦 سرویس‌هایم", callback_data="my_orders"),
        InlineKeyboardButton("🏠 منو", callback_data="main_menu")
    ]])
    if hasattr(query_or_ctx, "edit_message_text"):
        await query_or_ctx.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await query_or_ctx.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


# ── EXTEND (تمدید / افزایش حجم) ──────────────────────────────────────────────

async def extend_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    extend_type = parts[1]   # gb or days
    order_id = int(parts[2])
    context.user_data["ext_type"] = extend_type
    context.user_data["ext_order"] = order_id
    label = "حجم (GB)" if extend_type == "gb" else "تعداد روز"
    await query.edit_message_text(
        f"{'➕ افزایش حجم' if extend_type == 'gb' else '📅 تمدید'}\n\n"
        f"مقدار {label} را وارد کنید:",
        reply_markup=back_btn("my_orders")
    )
    return S_EXTEND_VAL


async def extend_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد مثبت وارد کنید:")
        return S_EXTEND_VAL

    order_id = context.user_data.get("ext_order")
    ext_type = context.user_data.get("ext_type")
    from database import get_db
    with get_db() as db:
        order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        plan = db.execute("SELECT * FROM plans WHERE id=?", (dict(order)["plan_id"],)).fetchone() if order else None
    if not order or not plan:
        await update.message.reply_text("❌ خطا.", reply_markup=back_btn("my_orders"))
        return ConversationHandler.END

    order, plan = dict(order), dict(plan)
    if ext_type == "gb":
        price = int((plan["price_rial"] / plan["gb"]) * val)
    else:
        price = int((plan["price_rial"] / plan["days"]) * val)

    user = get_user(update.effective_user.id)
    discount = user.get("discount_pct", 0) if user else 0
    final = apply_discount(price, discount)
    balance = user.get("balance_rial", 0) if user else 0

    context.user_data["ext_val"] = val
    context.user_data["ext_price"] = final
    await update.message.reply_text(
        f"💰 قیمت: `{fmt_rial(final)}`\n\nروش پرداخت:",
        reply_markup=payment_kb(order_id, balance),
        parse_mode="Markdown"
    )
    return ConversationHandler.END
