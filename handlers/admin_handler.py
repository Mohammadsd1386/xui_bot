import logging
import sqlite3
import tempfile
import time
import shutil
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import get_db, get_setting, set_setting, DB_PATH
from services.db_service import (
    get_users_page, count_users, get_user, set_discount, add_balance, ban_user,
    get_plans, get_plan, get_order, add_plan, toggle_plan, delete_plan, update_plan_field,
    get_panels, get_panel, add_panel, delete_panel, toggle_panel,
    get_pending_crypto_payments, get_payment, confirm_payment, reject_payment,
    get_sales_stats, get_admins, add_admin, delete_admin, get_all_user_ids,
    get_user_financial_stats, get_pending_wallet_requests, approve_wallet_request, reject_wallet_request,
    get_user_orders_admin,
)
from services.panel_service import get_api
from keyboards.menus import (
    adm_main_kb, adm_settings_kb, adm_free_test_kb,
    adm_payment_methods_kb,
    adm_users_kb, adm_user_detail_kb,
    adm_plans_kb, adm_plan_detail_kb, adm_plan_select_panel_kb,
    adm_panels_kb, adm_panel_detail_kb, adm_panel_type_kb,
    adm_payments_kb, adm_pay_detail_kb,
    adm_wallet_reqs_kb, adm_wallet_req_detail_kb,
    adm_admins_kb, confirm_kb, back_btn
)
from utils.helpers import fmt_rial, fmt_date, days_left, gateway_label, make_email
from utils.service_delivery import send_activation_to_user
from handlers.common import require_admin

logger = logging.getLogger(__name__)

# Conversation states
(S_SET_VAL,
 S_PLAN_NAME, S_PLAN_GB, S_PLAN_DAYS, S_PLAN_PRICE,
 S_PANEL_NAME, S_PANEL_URL, S_PANEL_PATH, S_PANEL_USER, S_PANEL_PASS, S_PANEL_IB,
 S_ADMIN_ID, S_BROADCAST, S_TOPUP, S_DISCOUNT, S_SEARCH_USER,
 S_PLAN_EDIT_NAME, S_PLAN_EDIT_PRICE) = range(18)


# ── MAIN ──────────────────────────────────────────────────────────────────────

@require_admin
async def adm_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("⚙️ *پنل ادمین*", reply_markup=adm_main_kb(), parse_mode="Markdown")
    else:
        await update.message.reply_text("⚙️ *پنل ادمین*", reply_markup=adm_main_kb(), parse_mode="Markdown")


# ── USERS ─────────────────────────────────────────────────────────────────────

@require_admin
async def adm_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offset = 0
    users = get_users_page(20, offset)
    total = count_users()
    await query.edit_message_text(
        f"👥 *کاربران* — جمع: `{total}`",
        reply_markup=adm_users_kb(users, offset),
        parse_mode="Markdown"
    )


def _render_admin_user_text(uid: int, user: dict) -> str:
    st = get_user_financial_stats(uid)
    with get_db() as db:
        last_pay = db.execute(
            "SELECT MAX(confirmed_at) as t FROM payments WHERE user_id=? AND status='confirmed'", (uid,)
        ).fetchone()
    return (
        f"👤 *اطلاعات کاربر*\n\n"
        f"🆔 آیدی: `{uid}`\n"
        f"👤 نام: {user.get('full_name') or '—'}\n"
        f"🔖 یوزرنیم: @{user.get('username') or '—'}\n"
        f"📦 سفارش‌ها: `{st['orders_count']}`\n"
        f"💳 مجموع پرداخت تاییدشده: `{fmt_rial(st['total_paid_rial'])}`\n"
        f"🛍 مجموع خرید: `{fmt_rial(st['total_buy_rial'])}`\n"
        f"💾 مجموع حجم خریداری‌شده: `{round(st['total_gb'], 2)} GB`\n"
        f"➕ شارژ کیف تاییدشده: `{fmt_rial(st['wallet_deposit_rial'])}`\n"
        f"➖ برداشت کیف تاییدشده: `{fmt_rial(st['wallet_withdraw_rial'])}`\n"
        f"👛 موجودی: `{fmt_rial(user.get('balance_rial', 0))}`\n"
        f"🎁 تخفیف: `{user.get('discount_pct', 0)}%`\n"
        f"🚫 مسدود: {'بله' if user.get('is_banned') else 'خیر'}\n"
        f"📅 عضویت: {fmt_date(user.get('created_at', 0))}\n"
        f"🕒 آخرین پرداخت تاییدشده: {fmt_date((last_pay['t'] if last_pay else 0) or 0)}"
    )


@require_admin
async def adm_user_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 آیدی کاربر را با دستور زیر بفرستید:\n\n`/user 123456789`\n\n"
        "یا فقط آیدی عددی را ارسال کنید.",
        parse_mode="Markdown",
        reply_markup=back_btn("adm_users"),
    )
    return S_SEARCH_USER


@require_admin
async def adm_user_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip()
    if raw.startswith("/user"):
        parts = raw.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ فرمت صحیح: /user <telegram_id>")
            return S_SEARCH_USER
        raw = parts[1].strip()
    try:
        uid = int(raw)
    except ValueError:
        await update.message.reply_text("❌ آیدی عددی معتبر بفرستید.")
        return S_SEARCH_USER
    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد.", reply_markup=back_btn("adm_users"))
        return ConversationHandler.END
    text = _render_admin_user_text(uid, user)
    await update.message.reply_text(text, reply_markup=adm_user_detail_kb(uid), parse_mode="Markdown")
    return ConversationHandler.END


@require_admin
async def adm_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await update.message.reply_text("❌ فرمت صحیح: /user <telegram_id>")
        return
    try:
        uid = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ آیدی عددی معتبر بفرستید.")
        return
    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        return
    text = _render_admin_user_text(uid, user)
    await update.message.reply_text(text, reply_markup=adm_user_detail_kb(uid), parse_mode="Markdown")


@require_admin
async def adm_users_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offset = int(query.data.split("_")[3])
    users = get_users_page(20, offset)
    total = count_users()
    await query.edit_message_text(
        f"👥 *کاربران* — جمع: `{total}`",
        reply_markup=adm_users_kb(users, offset),
        parse_mode="Markdown"
    )


@require_admin
async def adm_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[2])
    user = get_user(uid)
    if not user:
        await query.edit_message_text("❌ کاربر یافت نشد.", reply_markup=back_btn("adm_users"))
        return
    text = _render_admin_user_text(uid, user)
    await query.edit_message_text(text, reply_markup=adm_user_detail_kb(uid), parse_mode="Markdown")


@require_admin
async def adm_user_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[3])
    user = get_user(uid)
    if not user:
        await query.edit_message_text("❌ کاربر یافت نشد.", reply_markup=back_btn("adm_users"))
        return
    orders = get_user_orders_admin(uid)
    if not orders:
        await query.edit_message_text("📭 این کاربر سفارشی ندارد.", reply_markup=back_btn(f"adm_user_{uid}"))
        return
    lines = [f"📦 *سفارش‌های کاربر* `{uid}`\n"]
    st_emoji = {"active": "✅", "expired": "⏰", "pending": "⏳", "cancelled": "❌", "merged": "🔗"}
    for o in orders[:20]:
        e = st_emoji.get(o["status"], "❓")
        ext = " (تمدید)" if o.get("extends_order_id") else ""
        lines.append(
            f"{e} `#{o['id']}`{ext} {o.get('plan_name') or '—'} — `{fmt_rial(o.get('price_paid', 0))}`"
        )
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=back_btn(f"adm_user_{uid}"),
        parse_mode="Markdown",
    )


@require_admin
async def adm_sync_rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from services.rates_service import refresh_rates_once
    ok, msg = await refresh_rates_once()
    icon = "✅" if ok else "⚠️"
    await query.edit_message_text(f"{icon} {msg}", reply_markup=back_btn("adm_settings"), parse_mode="Markdown")


@require_admin
async def adm_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    action = parts[1]  # ban or unban
    uid = int(parts[2])
    ban_user(uid, action == "ban")
    label = "مسدود" if action == "ban" else "رفع مسدودی"
    await query.edit_message_text(f"✅ کاربر `{uid}` {label} شد.", parse_mode="Markdown",
                                  reply_markup=back_btn("adm_users"))


# Discount conversation
@require_admin
async def adm_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[2])
    context.user_data["disc_uid"] = uid
    await query.edit_message_text(
        f"🎁 درصد تخفیف کاربر `{uid}` (عدد 0 تا 100):",
        parse_mode="Markdown", reply_markup=back_btn("adm_users")
    )
    return S_DISCOUNT


async def adm_discount_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pct = int(update.message.text.strip())
        if not 0 <= pct <= 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد 0 تا 100 وارد کنید:")
        return S_DISCOUNT
    uid = context.user_data.pop("disc_uid")
    set_discount(uid, pct)
    await update.message.reply_text(f"✅ تخفیف `{pct}%` برای `{uid}` ثبت شد.",
                                    parse_mode="Markdown", reply_markup=back_btn("adm_users"))
    return ConversationHandler.END


# Topup conversation
@require_admin
async def adm_topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[2])
    context.user_data["topup_uid"] = uid
    await query.edit_message_text(
        f"💰 مبلغ شارژ کیف کاربر `{uid}` (تومان):",
        parse_mode="Markdown", reply_markup=back_btn("adm_users")
    )
    return S_TOPUP


async def adm_topup_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مبلغ معتبر وارد کنید:")
        return S_TOPUP
    uid = context.user_data.pop("topup_uid")
    add_balance(uid, amount)
    await update.message.reply_text(f"✅ `{fmt_rial(amount)}` به کیف `{uid}` اضافه شد.",
                                    parse_mode="Markdown")
    try:
        await context.bot.send_message(uid, f"💰 `{fmt_rial(amount)}` به کیف پول شما اضافه شد.",
                                       parse_mode="Markdown")
    except Exception:
        pass
    return ConversationHandler.END


# ── PLANS ─────────────────────────────────────────────────────────────────────

@require_admin
async def adm_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plans = get_plans()
    text = f"📦 *پلن‌ها* — تعداد: `{len(plans)}`"
    await query.edit_message_text(text, reply_markup=adm_plans_kb(plans), parse_mode="Markdown")


@require_admin
async def adm_plan_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[2])
    plan = get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ پلن یافت نشد.", reply_markup=back_btn("adm_plans"))
        return
    text = (
        f"📦 *{plan['name']}*\n\n"
        f"💾 حجم: `{plan['gb']} GB`\n"
        f"📅 مدت: `{plan['days']} روز`\n"
        f"💰 قیمت: `{fmt_rial(plan['price_rial'])}`\n"
        f"🖥 پنل: `{plan.get('panel_name') or '—'}`\n"
        f"وضعیت: {'✅ فعال' if plan['is_active'] else '❌ غیرفعال'}"
    )
    await query.edit_message_text(text, reply_markup=adm_plan_detail_kb(plan_id), parse_mode="Markdown")


@require_admin
async def adm_plan_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    action = parts[3]   # enable or disable
    plan_id = int(parts[4])
    with get_db() as db:
        db.execute("UPDATE plans SET is_active=? WHERE id=?", (1 if action == "enable" else 0, plan_id))
    label = "فعال" if action == "enable" else "غیرفعال"
    await query.edit_message_text(f"✅ پلن {label} شد.", reply_markup=back_btn("adm_plans"))


@require_admin
async def adm_plan_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[3])
    delete_plan(plan_id)
    await query.edit_message_text("✅ پلن حذف شد.", reply_markup=back_btn("adm_plans"))


# Add plan conversation
@require_admin
async def adm_plan_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_plan"] = {}
    await query.edit_message_text("📦 *پلن جدید*\n\nنام پلن را وارد کنید:",
                                  parse_mode="Markdown", reply_markup=back_btn("adm_plans"))
    return S_PLAN_NAME


async def adm_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_plan"]["name"] = update.message.text.strip()
    await update.message.reply_text("💾 حجم (GB) را وارد کنید:")
    return S_PLAN_GB


async def adm_plan_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_plan"]["gb"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ عدد وارد کنید:")
        return S_PLAN_GB
    await update.message.reply_text("📅 مدت (روز) را وارد کنید:")
    return S_PLAN_DAYS


async def adm_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_plan"]["days"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return S_PLAN_DAYS
    await update.message.reply_text("💰 قیمت (تومان) را وارد کنید:")
    return S_PLAN_PRICE


async def adm_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_plan"]["price_rial"] = int(update.message.text.strip().replace(",", ""))
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return S_PLAN_PRICE
    panels = get_panels(active_only=True)
    if not panels:
        await update.message.reply_text("❌ هیچ پنل فعالی وجود ندارد. ابتدا پنل اضافه کنید.",
                                        reply_markup=back_btn("adm_plans"))
        context.user_data.pop("new_plan", None)
        return ConversationHandler.END
    await update.message.reply_text("🖥 پنل را انتخاب کنید:", reply_markup=adm_plan_select_panel_kb(panels))
    return S_PLAN_GB  # we reuse state — actually wait for callback


async def adm_plan_save_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    plan = context.user_data.pop("new_plan", {})
    plan_id = add_plan(plan["name"], plan["gb"], plan["days"], plan["price_rial"], panel_id)
    await query.edit_message_text(f"✅ پلن *{plan['name']}* ایجاد شد! (ID: {plan_id})",
                                  parse_mode="Markdown", reply_markup=back_btn("adm_plans"))
    return ConversationHandler.END


# ── PANELS ────────────────────────────────────────────────────────────────────

@require_admin
async def adm_panels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panels = get_panels()
    await query.edit_message_text(
        f"🖥 *پنل‌ها* — تعداد: `{len(panels)}`",
        reply_markup=adm_panels_kb(panels), parse_mode="Markdown"
    )


@require_admin
async def adm_panel_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[2])
    p = get_panel(panel_id)
    if not p:
        await query.edit_message_text("❌ پنل یافت نشد.", reply_markup=back_btn("adm_panels"))
        return
    t = "سنایی (3x-ui)" if p["type"] == "xui" else "مرزبان"
    text = (
        f"🖥 *{p['name']}*\n\n"
        f"نوع: `{t}`\n"
        f"آدرس: `{p['url']}`\n"
        f"مسیر: `{p.get('path') or '—'}`\n"
        f"Inbound ID: `{p.get('inbound_id', 1)}`\n"
        f"وضعیت: {'✅ فعال' if p['is_active'] else '❌ غیرفعال'}"
    )
    await query.edit_message_text(text, reply_markup=adm_panel_detail_kb(panel_id), parse_mode="Markdown")


@require_admin
async def adm_panel_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    toggle_panel(panel_id)
    await query.edit_message_text("✅ وضعیت پنل تغییر کرد.", reply_markup=back_btn("adm_panels"))


@require_admin
async def adm_panel_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    try:
        delete_panel(panel_id)
    except ValueError as e:
        await query.edit_message_text(f"❌ {e}", reply_markup=back_btn("adm_panels"))
        return
    await query.edit_message_text("✅ پنل حذف شد.", reply_markup=back_btn("adm_panels"))


@require_admin
async def adm_panel_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    await query.edit_message_text("⏳ در حال ریستارت پنل...")
    p = get_panel(panel_id)
    if not p:
        await query.edit_message_text("❌ پنل یافت نشد.", reply_markup=back_btn("adm_panels"))
        return
    try:
        api = await get_api(p)
        ok, msg = await api.restart()
        result = "✅ پنل ریستارت شد!" if ok else f"❌ خطا: {msg}"
    except Exception as e:
        result = f"❌ خطا: {e}"
    await query.edit_message_text(result, reply_markup=back_btn("adm_panels"))


@require_admin
async def adm_panel_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    panel_id = int(query.data.split("_")[3])
    await query.edit_message_text("⏳ در حال دریافت کلاینت‌ها...")
    p = get_panel(panel_id)
    if not p or p["type"] != "xui":
        await query.edit_message_text("❌ فقط برای پنل سنایی پشتیبانی می‌شود.",
                                      reply_markup=back_btn("adm_panels"))
        return
    try:
        api = await get_api(p)
        clients = await api.list_clients()
        if not clients:
            await query.edit_message_text("📭 کلاینتی یافت نشد.", reply_markup=back_btn("adm_panels"))
            return
        text = f"📋 *کلاینت‌های پنل* ({len(clients)} کاربر)\n\n"
        for i, c in enumerate(clients[:20], 1):
            e = "✅" if c.get("enable") else "❌"
            gb = round(c.get("totalGB", 0) / (1024 ** 3), 1)
            text += f"{i}. {e} `{c.get('email','—')}` — {gb}GB\n"
        if len(clients) > 20:
            text += f"\n... و {len(clients) - 20} کلاینت دیگر"
        await query.edit_message_text(text, reply_markup=back_btn("adm_panels"), parse_mode="Markdown")
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {e}", reply_markup=back_btn("adm_panels"))


# Add panel conversation
@require_admin
async def adm_panel_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_panel"] = {}
    await query.edit_message_text("🖥 *پنل جدید*\n\nنام پنل را وارد کنید:",
                                  parse_mode="Markdown", reply_markup=back_btn("adm_panels"))
    return S_PANEL_NAME


async def adm_panel_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["name"] = update.message.text.strip()
    await update.message.reply_text("نوع پنل را انتخاب کنید:", reply_markup=adm_panel_type_kb())
    return S_PANEL_URL  # wait for callback (type selection)


async def adm_panel_type_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ptype = query.data.split("_")[1]   # xui or marzban
    context.user_data["new_panel"]["type"] = ptype
    await query.edit_message_text(
        "آدرس پنل را وارد کنید:\n_(مثال: http://1.2.3.4:8080)_",
        parse_mode="Markdown"
    )
    return S_PANEL_URL


async def adm_panel_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["url"] = update.message.text.strip()
    ptype = context.user_data["new_panel"].get("type", "xui")
    if ptype == "xui":
        await update.message.reply_text("مسیر (Path) پنل را وارد کنید:\n_(مثال: /secret  یا خالی برای /)_",
                                        parse_mode="Markdown")
        return S_PANEL_PATH
    else:
        context.user_data["new_panel"]["path"] = ""
        await update.message.reply_text("نام کاربری ادمین مرزبان:")
        return S_PANEL_USER


async def adm_panel_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["path"] = update.message.text.strip()
    await update.message.reply_text("نام کاربری ادمین پنل:")
    return S_PANEL_USER


async def adm_panel_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["username"] = update.message.text.strip()
    await update.message.reply_text("رمز عبور ادمین پنل:")
    return S_PANEL_PASS


async def adm_panel_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_panel"]["password"] = update.message.text.strip()
    ptype = context.user_data["new_panel"].get("type", "xui")
    if ptype == "xui":
        await update.message.reply_text("شناسه Inbound (معمولاً 1):")
        return S_PANEL_IB
    else:
        context.user_data["new_panel"]["inbound_id"] = 1
        return await _save_panel(update, context)


async def adm_panel_ib(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["new_panel"]["inbound_id"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return S_PANEL_IB
    return await _save_panel(update, context)


async def _save_panel(update, context):
    p = context.user_data.pop("new_panel", {})
    panel_id = add_panel(p["name"], p["type"], p["url"],
                         p.get("path", ""), p["username"], p["password"],
                         p.get("inbound_id", 1))
    await update.message.reply_text(
        f"✅ پنل *{p['name']}* اضافه شد! (ID: {panel_id})",
        parse_mode="Markdown", reply_markup=back_btn("adm_panels")
    )
    return ConversationHandler.END


# ── PAYMENTS ──────────────────────────────────────────────────────────────────

@require_admin
async def adm_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pays = get_pending_crypto_payments()
    if not pays:
        await query.edit_message_text("✅ پرداخت در انتظاری وجود ندارد.",
                                      reply_markup=back_btn("adm_main"))
        return
    await query.edit_message_text(
        f"💳 *پرداخت‌های در انتظار* ({len(pays)} مورد)",
        reply_markup=adm_payments_kb(pays), parse_mode="Markdown"
    )


@require_admin
async def adm_pay_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pay_id = int(query.data.split("_")[2])
    with get_db() as db:
        p = db.execute(
            "SELECT p.*, u.username, u.full_name FROM payments p "
            "JOIN users u ON p.user_id=u.telegram_id WHERE p.id=?", (pay_id,)
        ).fetchone()
    if not p:
        await query.edit_message_text("❌ پرداخت یافت نشد.", reply_markup=back_btn("adm_payments"))
        return
    p = dict(p)
    text = (
        f"💳 *پرداخت #{pay_id}*\n\n"
        f"👤 کاربر: `{p['user_id']}` — {p.get('full_name') or '—'}\n"
        f"💰 مبلغ: `{fmt_rial(p['amount_rial'])}`\n"
        f"🌐 درگاه: {gateway_label(p['gateway'])}\n"
        f"📝 هش: `{p.get('tx_hash') or '—'}`\n"
        f"📅 تاریخ: {fmt_date(p['created_at'])}"
    )
    await query.edit_message_text(text, reply_markup=adm_pay_detail_kb(pay_id), parse_mode="Markdown")


@require_admin
async def adm_pay_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pay_id = int(query.data.split("_")[3])
    with get_db() as db:
        prow = db.execute("SELECT * FROM payments WHERE id=?", (pay_id,)).fetchone()
        pay = dict(prow) if prow else None
        order = None
        if pay and pay.get("order_id"):
            orow = db.execute("SELECT * FROM orders WHERE id=?", (pay["order_id"],)).fetchone()
            order = dict(orow) if orow else None

    if not pay:
        await query.edit_message_text("❌ پرداخت یافت نشد.", reply_markup=back_btn("adm_payments"))
        return

    # Wallet top-up payment (order-less)
    if pay.get("currency") == "wallet_deposit" and not order:
        raw = pay.get("tx_hash") or ""
        wr_id = None
        if raw.startswith("WR:"):
            try:
                wr_id = int(raw.split("|")[0].split(":", 1)[1])
            except Exception:
                wr_id = None
        if not wr_id:
            await query.edit_message_text("❌ شناسه درخواست شارژ در پرداخت مشخص نیست.", reply_markup=back_btn("adm_payments"))
            return
        res = approve_wallet_request(wr_id, update.effective_user.id)
        if not res or res.get("error"):
            err = (res or {}).get("error") or "درخواست شارژ معتبر نیست."
            await query.edit_message_text(f"❌ {err}", reply_markup=back_btn("adm_payments"))
            return
        confirm_payment(pay_id, pay.get("tx_hash"))
        await query.edit_message_text(
            f"✅ شارژ کیف پول تایید شد.\n"
            f"🆔 درخواست: `{wr_id}`\n"
            f"💰 مبلغ: `{fmt_rial(pay['amount_rial'])}`",
            parse_mode="Markdown",
            reply_markup=back_btn("adm_payments"),
        )
        try:
            await context.bot.send_message(
                pay["user_id"],
                f"✅ شارژ کیف پول شما تایید شد.\n💰 مبلغ: {fmt_rial(pay['amount_rial'])}",
            )
        except Exception:
            pass
        return

    if not order:
        await query.edit_message_text("❌ سفارش مرتبط با این پرداخت یافت نشد.", reply_markup=back_btn("adm_payments"))
        return

    await query.edit_message_text("⏳ در حال فعال‌سازی سرویس...")
    from handlers.shop_handler import finalize_paid_order

    try:
        await finalize_paid_order(context, query, order, pay_id, pay.get("tx_hash"))
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {e}", reply_markup=back_btn("adm_payments"))


@require_admin
async def adm_pay_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pay_id = int(query.data.split("_")[3])
    with get_db() as db:
        p = db.execute("SELECT user_id, currency, tx_hash FROM payments WHERE id=?", (pay_id,)).fetchone()
    pdata = dict(p) if p else {}
    if pdata.get("currency") == "wallet_deposit":
        raw = pdata.get("tx_hash") or ""
        if raw.startswith("WR:"):
            try:
                wr_id = int(raw.split("|")[0].split(":", 1)[1])
                reject_wallet_request(wr_id, update.effective_user.id)
            except Exception:
                pass
    reject_payment(pay_id)
    await query.edit_message_text("❌ پرداخت رد شد.", reply_markup=back_btn("adm_payments"))
    if p:
        try:
            await context.bot.send_message(
                dict(p)["user_id"],
                "❌ پرداخت شما تأیید نشد.\nبا پشتیبانی تماس بگیرید."
            )
        except Exception:
            pass


@require_admin
async def adm_wallet_reqs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reqs = get_pending_wallet_requests()
    if not reqs:
        await query.edit_message_text("✅ درخواست کیف پولی در انتظار نیست.", reply_markup=back_btn("adm_main"))
        return
    await query.edit_message_text(
        f"👛 *درخواست‌های کیف پول* ({len(reqs)} مورد)",
        reply_markup=adm_wallet_reqs_kb(reqs),
        parse_mode="Markdown"
    )


@require_admin
async def adm_wallet_req_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    req_id = int(query.data.split("_")[2])
    reqs = get_pending_wallet_requests()
    req = next((r for r in reqs if r["id"] == req_id), None)
    if not req:
        await query.edit_message_text("❌ درخواست یافت نشد یا رسیدگی شده است.", reply_markup=back_btn("adm_wallet_reqs"))
        return
    typ = "شارژ کیف پول" if req["type"] == "deposit" else "برداشت از کیف پول"
    destination = "—"
    note = req.get("note") or ""
    if note.startswith("destination:"):
        destination = note.split("destination:", 1)[1].strip() or "—"
    text = (
        f"👛 *درخواست #{req_id}*\n\n"
        f"نوع: `{typ}`\n"
        f"کاربر: `{req['user_id']}` - {req.get('full_name') or '—'}\n"
        f"مبلغ: `{fmt_rial(req['amount_rial'])}`\n"
        f"مقصد برداشت: `{destination}`\n"
        f"توضیح: {req.get('note') or '—'}\n"
        f"زمان: {fmt_date(req['created_at'])}"
    )
    await query.edit_message_text(text, reply_markup=adm_wallet_req_detail_kb(req_id), parse_mode="Markdown")


@require_admin
async def adm_wallet_req_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    req_id = int(query.data.split("_")[3])
    res = approve_wallet_request(req_id, update.effective_user.id)
    if not res:
        await query.edit_message_text("❌ درخواست معتبر نیست.", reply_markup=back_btn("adm_wallet_reqs"))
        return
    if res.get("error"):
        await query.edit_message_text(f"❌ {res['error']}", reply_markup=back_btn("adm_wallet_reqs"))
        return
    await query.edit_message_text("✅ درخواست کیف پول تایید شد.", reply_markup=back_btn("adm_wallet_reqs"))
    try:
        await context.bot.send_message(
            res["user_id"],
            f"✅ درخواست کیف پول شما تایید شد.\n💰 مبلغ: {fmt_rial(res['amount_rial'])}"
        )
    except Exception:
        pass


@require_admin
async def adm_wallet_req_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    req_id = int(query.data.split("_")[3])
    res = reject_wallet_request(req_id, update.effective_user.id)
    if not res:
        await query.edit_message_text("❌ درخواست معتبر نیست.", reply_markup=back_btn("adm_wallet_reqs"))
        return
    await query.edit_message_text("❌ درخواست کیف پول رد شد.", reply_markup=back_btn("adm_wallet_reqs"))
    try:
        await context.bot.send_message(
            res["user_id"],
            f"❌ درخواست کیف پول شما رد شد.\n💰 مبلغ: {fmt_rial(res['amount_rial'])}"
        )
    except Exception:
        pass


# ── SALES ─────────────────────────────────────────────────────────────────────

@require_admin
async def adm_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    s = get_sales_stats()
    text = (
        f"📊 *گزارش فروش*\n\n"
        f"💰 کل درآمد: `{fmt_rial(s['total_rial'])}`\n"
        f"📦 کل سفارش: `{s['total_count']}`\n"
        f"📅 امروز: `{fmt_rial(s['today_rial'])}`\n"
        f"📆 این ماه: `{fmt_rial(s['month_rial'])}`\n\n"
        f"*به تفکیک درگاه:*\n"
    )
    for gw in s["by_gateway"]:
        text += f"• {gateway_label(gw['gateway'])}: `{fmt_rial(gw['t'])}` ({gw['c']} فقره)\n"
    await query.edit_message_text(text, reply_markup=back_btn("adm_main"), parse_mode="Markdown")


@require_admin
async def adm_backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ در حال آماده‌سازی بکاپ دیتابیس...")
    ts = int(time.time())
    backup_name = f"vpnbot-backup-{ts}.db"
    tmp_file = Path(tempfile.gettempdir()) / backup_name
    try:
        # مسیر اصلی: بکاپ استاندارد SQLite (امن برای دیتابیس‌های WAL)
        src = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
        dst = sqlite3.connect(tmp_file)
        try:
            src.backup(dst)
        except Exception:
            # مسیر جایگزین: کپی مستقیم فایل دیتابیس در صورت خطای غیرمنتظره
            dst.close()
            src.close()
            shutil.copy2(DB_PATH, tmp_file)
        else:
            dst.close()
            src.close()
        with tmp_file.open("rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=f,
                filename=backup_name,
                caption="✅ بکاپ دیتابیس آماده شد.",
            )
        await query.edit_message_text("✅ بکاپ ارسال شد.", reply_markup=back_btn("adm_main"))
    except Exception as e:
        await query.edit_message_text(f"❌ خطا در بکاپ: {e}", reply_markup=back_btn("adm_main"))
    finally:
        try:
            if tmp_file.exists():
                tmp_file.unlink()
        except Exception:
            pass


# ── SETTINGS ──────────────────────────────────────────────────────────────────

@require_admin
async def adm_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ru = int(get_setting("rates_updated_at", "0") or "0")
    text = (
        f"⚙️ *تنظیمات*\n\n"
        f"💱 نرخ (USDT/دلار بازار): `{int(get_setting('usd_to_rial','650000')):,}` تومان\n"
        f"🕒 آخرین به‌روزرسانی خودکار: {fmt_date(ru)}\n"
        f"🎁 پاداش رفرال: `{fmt_rial(int(get_setting('referral_reward_rial','50000')))}`\n"
        f"🧪 تست رایگان: {'✅' if get_setting('free_test_enabled','0')=='1' else '❌'}\n"
        f"📢 جوین اجباری: {'✅' if get_setting('channel_join_required','0')=='1' else '❌'}\n"
        f"🏦 کارت مقصد: `{get_setting('card2card_number') or '—'}`\n"
        f"👤 صاحب کارت: `{get_setting('card2card_holder') or '—'}`\n"
        f"💎 تتر BEP20: `{get_setting('usdt_bep20_address') or '—'}`\n"
        f"🔵 ترون: `{get_setting('tron_address') or '—'}`\n"
        f"🪙 تون: `{get_setting('ton_address') or '—'}`\n"
        f"📱 پشتیبانی: @{get_setting('support_username') or '—'}"
    )
    await query.edit_message_text(text, reply_markup=adm_settings_kb(), parse_mode="Markdown")


_SETTING_MAP = {
    "set_usd_rate":    ("usd_to_rial",            "💱 نرخ دلار به تومان:"),
    "set_referral":    ("referral_reward_rial",    "🎁 مبلغ پاداش رفرال (تومان):"),
    "set_usdt_addr":   ("usdt_bep20_address",      "💎 آدرس کیف USDT BEP20:"),
    "set_tron_addr":   ("tron_address",            "🔵 آدرس کیف USDT TRC20:"),
    "set_ton_addr":    ("ton_address",             "🪙 آدرس کیف TON:"),
    "set_zarinpal":    ("zarinpal_merchant",       "🏦 کد مرچنت زرین‌پال:"),
    "set_support":     ("support_username",        "📱 یوزرنیم پشتیبانی (بدون @):"),
    "set_bot_name":    ("bot_name",                "🤖 نام ربات:"),
    "set_channel":     ("channel_id",              "📢 آیدی کانال (مثال @channel):"),
    "set_card_number": ("card2card_number",        "🏦 شماره کارت مقصد را وارد کنید:"),
    "set_card_holder": ("card2card_holder",        "👤 نام صاحب کارت را وارد کنید:"),
    "ft_set_gb":       ("free_test_gb",            "📦 حجم تست رایگان (GB):"),
    "ft_set_days":     ("free_test_days",          "📅 مدت تست رایگان (روز):"),
}


@require_admin
async def adm_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data

    if key == "set_free_test":
        await query.edit_message_text("🧪 *تست رایگان*", reply_markup=adm_free_test_kb(), parse_mode="Markdown")
        return ConversationHandler.END

    if key == "set_channel":
        await query.edit_message_text(
            "📢 *جوین اجباری کانال*\n\n"
            "آیدی کانال را بفرستید (مثال: `@channel` یا `-100...`).\n"
            "برای روشن/خاموش کردن از دکمه‌های پایین استفاده کنید.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ روشن", callback_data="ch_on"),
                 InlineKeyboardButton("❌ خاموش", callback_data="ch_off")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="adm_settings")]
            ])
        )
        context.user_data["setting_key"] = "channel_id"
        return S_SET_VAL

    if key == "set_payment_methods":
        await query.edit_message_text(
            "💳 *مدیریت روش‌های پرداخت*\nروی هر مورد بزنید تا فعال/غیرفعال شود.",
            reply_markup=adm_payment_methods_kb(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if key == "set_card_info":
        await query.edit_message_text(
            "🏦 *تنظیم کارت‌به‌کارت*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ شماره کارت", callback_data="set_card_number"),
                 InlineKeyboardButton("👤 نام صاحب کارت", callback_data="set_card_holder")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="adm_settings")]
            ])
        )
        return ConversationHandler.END

    if key == "ch_on":
        set_setting("channel_join_required", "1")
        await query.edit_message_text("✅ جوین اجباری فعال شد.", reply_markup=back_btn("adm_settings"))
        return ConversationHandler.END

    if key == "ch_off":
        set_setting("channel_join_required", "0")
        await query.edit_message_text("❌ جوین اجباری غیرفعال شد.", reply_markup=back_btn("adm_settings"))
        return ConversationHandler.END

    if key.startswith("pay_toggle_"):
        gw = key.split("pay_toggle_")[1]
        db_key = f"pay_{gw}_enabled"
        new_val = "0" if get_setting(db_key, "1") == "1" else "1"
        set_setting(db_key, new_val)
        await query.edit_message_text(
            "💳 *مدیریت روش‌های پرداخت*\nروی هر مورد بزنید تا فعال/غیرفعال شود.",
            reply_markup=adm_payment_methods_kb(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if key == "ft_on":
        set_setting("free_test_enabled", "1")
        await query.edit_message_text("✅ تست رایگان فعال شد.", reply_markup=back_btn("adm_settings"))
        return ConversationHandler.END

    if key == "ft_off":
        set_setting("free_test_enabled", "0")
        await query.edit_message_text("❌ تست رایگان غیرفعال شد.", reply_markup=back_btn("adm_settings"))
        return ConversationHandler.END

    if key not in _SETTING_MAP:
        return ConversationHandler.END

    db_key, prompt = _SETTING_MAP[key]
    context.user_data["setting_key"] = db_key
    await query.edit_message_text(prompt, reply_markup=back_btn("adm_settings"))
    return S_SET_VAL


async def adm_setting_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_key = context.user_data.pop("setting_key", None)
    if not db_key:
        return ConversationHandler.END
    value = update.message.text.strip()
    set_setting(db_key, value)
    await update.message.reply_text(f"✅ ذخیره شد.", reply_markup=back_btn("adm_settings"))
    return ConversationHandler.END


# ── ADMINS ────────────────────────────────────────────────────────────────────

@require_admin
async def adm_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admins = get_admins()
    await query.edit_message_text(
        f"👨‍💼 *ادمین‌ها* — تعداد: `{len(admins)}`",
        reply_markup=adm_admins_kb(admins), parse_mode="Markdown"
    )


@require_admin
async def adm_add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ آیدی عددی تلگرام ادمین جدید را وارد کنید:",
        reply_markup=back_btn("adm_admins")
    )
    return S_ADMIN_ID


async def adm_add_admin_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ آیدی عددی وارد کنید:")
        return S_ADMIN_ID
    add_admin(new_id, update.effective_user.id)
    await update.message.reply_text(f"✅ ادمین `{new_id}` اضافه شد.", parse_mode="Markdown",
                                    reply_markup=back_btn("adm_admins"))
    try:
        await context.bot.send_message(new_id, "🎉 شما به عنوان ادمین ربات اضافه شدید!")
    except Exception:
        pass
    return ConversationHandler.END


@require_admin
async def adm_del_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    adm_id = int(query.data.split("_")[3])
    delete_admin(adm_id)
    await query.edit_message_text(f"✅ ادمین `{adm_id}` حذف شد.", parse_mode="Markdown",
                                  reply_markup=back_btn("adm_admins"))


# ── BROADCAST ─────────────────────────────────────────────────────────────────

@require_admin
async def adm_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 *ارسال همگانی*\n\nپیام را وارد کنید:",
                                  parse_mode="Markdown", reply_markup=back_btn("adm_main"))
    return S_BROADCAST


async def adm_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    uids = get_all_user_ids()
    sent = failed = 0
    for uid in uids:
        try:
            await context.bot.send_message(uid, msg)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📢 تمام!\n✅ موفق: {sent}\n❌ ناموفق: {failed}",
        reply_markup=back_btn("adm_main")
    )
    return ConversationHandler.END


# ── CANCEL ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🚫 لغو شد.", reply_markup=back_btn("adm_main"))
    else:
        await update.message.reply_text("🚫 لغو شد.")
    return ConversationHandler.END
