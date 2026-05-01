import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import get_db, get_setting
from services.user_service import get_user
from services.order_service import create_order, create_payment, pay_with_balance, activate_order
from services.panel_service import get_panel_api
from keyboards.menus import plans_kb, payment_method_kb, back_kb
from utils.helpers import fmt_rial, apply_discount, make_email, gateway_name

logger = logging.getLogger(__name__)
CHOOSING_EXTEND = 100


def get_active_plans():
    with get_db() as db:
        rows = db.execute("""SELECT p.*,pn.name as panel_name,pn.type as panel_type
            FROM plans p LEFT JOIN panels pn ON p.panel_id=pn.id
            WHERE p.is_active=1 ORDER BY p.price_rial ASC""").fetchall()
        return [dict(r) for r in rows]

def get_plan(plan_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        return dict(row) if row else None

def get_panel(panel_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM panels WHERE id=? AND is_active=1", (panel_id,)).fetchone()
        return dict(row) if row else None

def _get_admin_ids():
    with get_db() as db:
        return [r["telegram_id"] for r in db.execute("SELECT telegram_id FROM admins").fetchall()]


async def shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    plans = get_active_plans()
    text = "🛍 *پلن‌های موجود*\n\nپلن مورد نظر را انتخاب کنید:"
    if not plans:
        text = "😔 در حال حاضر پلنی موجود نیست."
    if query:
        await query.edit_message_text(text, reply_markup=plans_kb(plans) if plans else back_kb("main_menu"), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=plans_kb(plans) if plans else None, parse_mode="Markdown")


async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[1])
    plan = get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ پلن یافت نشد.", reply_markup=back_kb("shop"))
        return
    user = get_user(query.from_user.id)
    discount = user.get("discount_pct", 0) if user else 0
    final_price = apply_discount(plan["price_rial"], discount)
    usd_rate = int(get_setting("usd_to_rial", "650000"))
    price_usd = round(final_price / usd_rate, 2)
    text = (f"📦 *{plan['name']}*\n\n"
            f"🔹 حجم: `{plan['gb']} GB`\n"
            f"🔹 مدت: `{plan['days']} روز`\n"
            f"🔹 قیمت: `{fmt_rial(plan['price_rial'])}`\n")
    if discount > 0:
        text += f"🎁 تخفیف: `{discount}%` → `{fmt_rial(final_price)}`\n"
    text += f"💱 معادل: `{price_usd} USDT`\n\n💳 روش پرداخت:"
    order_id = create_order(query.from_user.id, plan_id, plan["panel_id"], plan["gb"], plan["days"], final_price, "rial")
    balance = user.get("balance_rial", 0) if user else 0
    await query.edit_message_text(text, reply_markup=payment_method_kb(order_id, balance > 0, balance), parse_mode="Markdown")


async def pay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    gateway = parts[1]
    order_id = int(parts[2])
    with get_db() as db:
        order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        await query.edit_message_text("❌ سفارش یافت نشد.", reply_markup=back_kb("shop"))
        return
    order = dict(order)
    amount = order["price_paid"]
    if gateway == "balance":
        if not pay_with_balance(query.from_user.id, order_id, amount):
            await query.edit_message_text("❌ موجودی کافی نیست.", reply_markup=payment_method_kb(order_id))
            return
        payment_id = create_payment(query.from_user.id, order_id, amount, "rial", "balance")
        await _activate_order(query, context, order, payment_id)
        return
    if gateway == "zarinpal":
        await _zarinpal_pay(query, context, order, amount)
        return
    # Crypto
    usd_rate = int(get_setting("usd_to_rial", "650000"))
    price_usd = round(amount / usd_rate, 4)
    payment_id = create_payment(query.from_user.id, order_id, amount, gateway, gateway)
    wallets = {
        "usdt": (get_setting("usdt_bep20_address",""), "BEP20 (BSC)", "USDT", price_usd),
        "tron": (get_setting("tron_address",""), "TRC20 (Tron)", "USDT", price_usd),
        "ton":  (get_setting("ton_address",""), "TON Network", "TON",
                 round(price_usd / float(get_setting("ton_price_usd","3.5")), 4)),
    }
    addr, network, coin, amt = wallets.get(gateway, ("","","",0))
    if not addr:
        await query.edit_message_text("❌ این درگاه تنظیم نشده.", reply_markup=back_kb("shop"))
        return
    ton_memo = get_setting("ton_memo","")
    memo_text = f"\n📝 Memo: `{ton_memo}`" if gateway=="ton" and ton_memo else ""
    text = (f"💳 *پرداخت {gateway_name(gateway)}*\n\n"
            f"💰 مبلغ: `{amt} {coin}`\n"
            f"🌐 شبکه: `{network}`\n"
            f"📍 آدرس:\n`{addr}`{memo_text}\n\n"
            f"⚠️ پس از واریز، رسید یا هش تراکنش ارسال کنید.\n"
            f"🆔 شناسه پرداخت: `{payment_id}`")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ پرداخت کردم", callback_data=f"crypto_paid_{payment_id}")],
        [InlineKeyboardButton("🔙 لغو", callback_data="shop")]
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)


async def crypto_paid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_id = int(query.data.split("_")[2])
    await query.edit_message_text(
        f"📋 هش تراکنش یا تصویر رسید ارسال کنید:\n🆔 شناسه: `{payment_id}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 لغو", callback_data="shop")]]))
    context.user_data["awaiting_tx_hash"] = payment_id


async def tx_hash_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment_id = context.user_data.pop("awaiting_tx_hash", None)
    if not payment_id:
        return
    tx = update.message.text.strip() if update.message.text else "رسید تصویری"
    with get_db() as db:
        db.execute("UPDATE payments SET tx_hash=? WHERE id=?", (tx, payment_id))
    await update.message.reply_text(
        f"✅ رسید دریافت شد! پس از بررسی ادمین، سرویس فعال می‌شود.\n🆔 شناسه: `{payment_id}`",
        parse_mode="Markdown")
    user = update.effective_user
    notify = (f"💳 *پرداخت جدید #{payment_id}*\n\n"
              f"👤 [{user.full_name}](tg://user?id={user.id})\n"
              f"📝 هش: `{tx}`")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"adm_pay_confirm_{payment_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"adm_pay_reject_{payment_id}")
    ]])
    for admin_id in _get_admin_ids():
        try:
            await update.get_bot().send_message(admin_id, notify, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass


async def _zarinpal_pay(query, context, order, amount):
    from services.payment_service import ZarinPalService
    merchant = get_setting("zarinpal_merchant","")
    if not merchant:
        await query.edit_message_text("❌ زرین‌پال تنظیم نشده.", reply_markup=back_kb("shop"))
        return
    zp = ZarinPalService(merchant)
    callback = get_setting("zarinpal_callback","https://t.me/your_bot")
    ok, url_or_err, authority = await zp.request(amount, f"خرید سرویس VPN #{order['id']}", callback)
    if ok:
        payment_id = create_payment(query.from_user.id, order["id"], amount, "rial", "zarinpal")
        with get_db() as db:
            db.execute("UPDATE payments SET tx_hash=? WHERE id=?", (authority, payment_id))
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 پرداخت آنلاین", url=url_or_err)],
                                   [InlineKeyboardButton("🔙 لغو", callback_data="shop")]])
        await query.edit_message_text(f"🏦 *زرین‌پال*\nمبلغ: `{fmt_rial(amount)}`",
                                      reply_markup=kb, parse_mode="Markdown")
    else:
        await query.edit_message_text(f"❌ خطا: {url_or_err}", reply_markup=back_kb("shop"))


async def _activate_order(query_or_msg, context, order, payment_id):
    panel = get_panel(order["panel_id"])
    if not panel:
        txt = "❌ پنل یافت نشد. با پشتیبانی تماس بگیرید."
        if hasattr(query_or_msg, 'edit_message_text'): await query_or_msg.edit_message_text(txt)
        else: await query_or_msg.message.reply_text(txt)
        return
    email = make_email(order["user_id"], str(order.get("plan_id","vpn")))
    try:
        api = await get_panel_api(panel)
        if panel["type"] == "xui":
            ok, result = await api.add_client(email, order["gb"], order["days"], panel.get("inbound_id",1))
        else:
            ok, result = await api.add_user(email, order["gb"], order["days"])
        if ok:
            activate_order(order["id"], result.get("uuid",email), email, result.get("sub_link",""))
            with get_db() as db:
                db.execute("UPDATE payments SET status='confirmed' WHERE id=?", (payment_id,))
            sub_link = result.get("sub_link","")
            text = (f"🎉 *سرویس فعال شد!*\n\n"
                    f"📦 حجم: `{order['gb']} GB`\n"
                    f"📅 مدت: `{order['days']} روز`\n\n"
                    f"🔗 لینک اشتراک:\n`{sub_link}`")
        else:
            text = f"❌ خطا در پنل: {result}"
    except Exception as e:
        text = f"❌ خطا: {e}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📦 سرویس‌هایم", callback_data="my_orders"),
                                InlineKeyboardButton("🏠 منو", callback_data="main_menu")]])
    if hasattr(query_or_msg,'edit_message_text'):
        await query_or_msg.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await query_or_msg.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


async def extend_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    extend_type = parts[1]
    order_id = int(parts[2])
    context.user_data["extend_order_id"] = order_id
    context.user_data["extend_type"] = extend_type
    label = "حجم (GB)" if extend_type=="gb" else "روز"
    await query.edit_message_text(
        f"{'➕ افزایش حجم' if extend_type=='gb' else '📅 تمدید'}\n\nمقدار {label} را وارد کنید:",
        reply_markup=back_kb("my_orders"))
    return CHOOSING_EXTEND


async def extend_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.strip())
        if val <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد مثبت وارد کنید:")
        return CHOOSING_EXTEND
    order_id = context.user_data.get("extend_order_id")
    extend_type = context.user_data.get("extend_type")
    with get_db() as db:
        order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        plan = db.execute("SELECT * FROM plans WHERE id=?", (dict(order)["plan_id"],)).fetchone() if order else None
    if not order or not plan:
        await update.message.reply_text("❌ خطا.", reply_markup=back_kb("my_orders"))
        return ConversationHandler.END
    order, plan = dict(order), dict(plan)
    price = int((plan["price_rial"]/plan["gb"])*val) if extend_type=="gb" else int((plan["price_rial"]/plan["days"])*val)
    user = get_user(update.effective_user.id)
    discount = user.get("discount_pct",0) if user else 0
    final = apply_discount(price, discount)
    context.user_data["extend_val"] = val
    context.user_data["extend_price"] = final
    balance = user.get("balance_rial",0) if user else 0
    await update.message.reply_text(
        f"💰 قیمت: `{fmt_rial(final)}`\n\nروش پرداخت:",
        reply_markup=payment_method_kb(order_id, balance>0, balance), parse_mode="Markdown")
    return ConversationHandler.END
