import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from database import init_db, get_setting
from config import Config
from services.user_service import get_or_create_user, is_admin
from keyboards.menus import main_menu_kb, back_kb
from handlers.shop_handler import (
    shop_handler, plan_selected, pay_handler, crypto_paid_handler,
    tx_hash_received, extend_order_handler, extend_amount_handler, CHOOSING_EXTEND
)
from handlers.user_handler import (
    my_account, my_orders, order_detail, wallet, referral,
    free_test, support, new_ticket_start, ticket_subject, ticket_message,
    my_tickets, ticket_view, admin_ticket_reply_start, admin_ticket_reply_send,
    SUPPORT_SUBJECT, SUPPORT_MSG, TICKET_REPLY
)
from handlers.admin_handler import (
    admin_main, adm_users, adm_user_detail, adm_discount_start, adm_discount_set,
    adm_topup_start, adm_topup_set, adm_ban_handler,
    adm_plans, adm_plan_detail, adm_plan_add_start, adm_plan_name, adm_plan_gb,
    adm_plan_days, adm_plan_price, adm_plan_panel, adm_plan_del,
    adm_panels, adm_panel_detail, adm_panel_add_start, adm_panel_name, adm_panel_type,
    adm_panel_url, adm_panel_path, adm_panel_user, adm_panel_pass, adm_panel_ib,
    adm_panel_restart, adm_panel_del,
    adm_sales, adm_payments, adm_pay_detail, adm_pay_confirm, adm_pay_reject,
    adm_settings, adm_setting_start, adm_setting_value,
    adm_admins, adm_add_admin_start, adm_add_admin_id, adm_del_admin,
    adm_broadcast_start, adm_broadcast_send,
    cancel_conv,
    SET_VALUE, ADD_PLAN_NAME, ADD_PLAN_GB, ADD_PLAN_DAYS, ADD_PLAN_PRICE, ADD_PLAN_PANEL,
    ADD_PANEL_NAME, ADD_PANEL_TYPE, ADD_PANEL_URL, ADD_PANEL_PATH,
    ADD_PANEL_USER, ADD_PANEL_PASS, ADD_PANEL_IB, ADD_ADMIN_ID,
    BROADCAST_MSG, USER_TOPUP
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def admin_guard(func):
    """Decorator: only allow admins"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        owner_id = int(get_setting("owner_id") or Config.OWNER_ID or 0)
        if not is_admin(user_id, owner_id):
            query = update.callback_query
            if query:
                await query.answer("⛔ دسترسی ندارید.", show_alert=True)
            else:
                await update.message.reply_text("⛔ دسترسی ندارید.")
            return
        return await func(update, context)
    return wrapper


def ban_guard(func):
    """Decorator: block banned users"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        from services.user_service import get_user
        user = get_user(update.effective_user.id)
        if user and user.get("is_banned"):
            msg = "🚫 حساب شما مسدود شده است."
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            else:
                await update.message.reply_text(msg)
            return
        return await func(update, context)
    return wrapper


# ─── START / MENU ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # Handle referral link
    referrer_id = None
    if args and args[0].startswith("ref"):
        try:
            referrer_id = int(args[0][3:])
            if referrer_id == user.id:
                referrer_id = None
        except ValueError:
            pass

    get_or_create_user(user.id, user.username, user.full_name, referrer_id)

    # Check channel membership
    channel_id = get_setting("channel_id", "")
    channel_required = get_setting("channel_join_required", "0") == "1"
    if channel_id and channel_required:
        try:
            member = await context.bot.get_chat_member(channel_id, user.id)
            if member.status in ("left", "kicked"):
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{channel_id.lstrip('@')}")],
                    [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]
                ])
                await update.message.reply_text(
                    f"⚠️ برای استفاده از ربات باید در کانال عضو شوید:\n{channel_id}",
                    reply_markup=kb)
                return
        except Exception:
            pass

    owner_id = int(get_setting("owner_id") or Config.OWNER_ID or 0)
    is_adm = is_admin(user.id, owner_id)
    bot_name = get_setting("bot_name", "ربات فروش VPN")

    text = (
        f"👋 سلام *{user.first_name}*!\n\n"
        f"🌐 *{bot_name}*\n\n"
        f"از منوی زیر استفاده کنید:"
    )
    await update.message.reply_text(text, reply_markup=main_menu_kb(is_adm), parse_mode="Markdown")


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    owner_id = int(get_setting("owner_id") or Config.OWNER_ID or 0)
    is_adm = is_admin(user.id, owner_id)
    bot_name = get_setting("bot_name", "ربات فروش VPN")
    await query.edit_message_text(
        f"🌐 *{bot_name}*\n\nاز منوی زیر استفاده کنید:",
        reply_markup=main_menu_kb(is_adm), parse_mode="Markdown")


async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channel_id = get_setting("channel_id", "")
    try:
        member = await context.bot.get_chat_member(channel_id, update.effective_user.id)
        if member.status not in ("left", "kicked"):
            user = update.effective_user
            owner_id = int(get_setting("owner_id") or Config.OWNER_ID or 0)
            is_adm = is_admin(user.id, owner_id)
            await query.edit_message_text(
                "✅ عضویت تأیید شد!\nاز منوی زیر استفاده کنید:",
                reply_markup=main_menu_kb(is_adm))
            return
    except Exception:
        pass
    await query.answer("❌ هنوز عضو نشده‌اید.", show_alert=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)


# ─── SETUP OWNER ──────────────────────────────────────────────────────────────

async def setup_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """First-time owner setup via /setup <token>"""
    args = context.args
    if not args:
        await update.message.reply_text("استفاده: /setup <OWNER_TOKEN>")
        return
    expected = os.getenv("SETUP_TOKEN", "")
    if not expected or args[0] != expected:
        await update.message.reply_text("❌ توکن اشتباه است.")
        return
    from database import set_setting
    set_setting("owner_id", str(update.effective_user.id))
    await update.message.reply_text(
        f"✅ شما به عنوان مالک ربات ثبت شدید!\nآیدی: `{update.effective_user.id}`",
        parse_mode="Markdown")


# ─── BUILD APP ────────────────────────────────────────────────────────────────

def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()

    # ── Admin conversations ──────────────────────────────────────────────────
    plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_plan_add_start, pattern="^adm_plan_add$")],
        states={
            ADD_PLAN_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_name)],
            ADD_PLAN_GB:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_gb)],
            ADD_PLAN_DAYS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_days)],
            ADD_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_price)],
            ADD_PLAN_PANEL: [CallbackQueryHandler(adm_plan_panel, pattern="^new_plan_panel_")],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel$"),
                   CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    panel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_panel_add_start, pattern="^adm_panel_add$")],
        states={
            ADD_PANEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_name)],
            ADD_PANEL_TYPE: [CallbackQueryHandler(adm_panel_type, pattern="^ptype_")],
            ADD_PANEL_URL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_url)],
            ADD_PANEL_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_path)],
            ADD_PANEL_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_user)],
            ADD_PANEL_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_pass)],
            ADD_PANEL_IB:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_ib)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel$"),
                   CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_setting_start,
                                           pattern="^set_usd_rate|set_referral_reward|set_usdt_addr|"
                                                   "set_tron_addr|set_ton_addr|set_zarinpal|set_support|"
                                                   "set_bot_name|set_channel|set_free_test|"
                                                   "set_free_test_on|set_free_test_off|"
                                                   "set_free_test_gb|set_free_test_days$")],
        states={
            SET_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_setting_value)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel$"),
                   CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    discount_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_discount_start, pattern="^adm_discount_")],
        states={SET_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_discount_set)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    topup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_topup_start, pattern="^adm_topup_")],
        states={USER_TOPUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_topup_set)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_add_admin_start, pattern="^adm_add_admin$")],
        states={ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_admin_id)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_broadcast_start, pattern="^adm_broadcast$")],
        states={BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_broadcast_send)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    # ── User conversations ───────────────────────────────────────────────────
    ticket_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(new_ticket_start, pattern="^new_ticket$")],
        states={
            SUPPORT_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_subject)],
            SUPPORT_MSG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_message)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel$"),
                   CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    ticket_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_ticket_reply_start, pattern="^ticket_reply_")],
        states={
            TICKET_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ticket_reply_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    extend_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(extend_order_handler, pattern="^extend_")],
        states={
            CHOOSING_EXTEND: [MessageHandler(filters.TEXT & ~filters.COMMAND, extend_amount_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        per_message=False,
    )

    # ── Register all handlers ─────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("setup", setup_owner))

    # Conversations first
    app.add_handler(plan_conv)
    app.add_handler(panel_conv)
    app.add_handler(settings_conv)
    app.add_handler(discount_conv)
    app.add_handler(topup_conv)
    app.add_handler(add_admin_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(ticket_conv)
    app.add_handler(ticket_reply_conv)
    app.add_handler(extend_conv)

    # ── Callback handlers ────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(main_menu,           pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(check_join,          pattern="^check_join$"))

    # User
    app.add_handler(CallbackQueryHandler(shop_handler,        pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(plan_selected,       pattern="^plan_"))
    app.add_handler(CallbackQueryHandler(pay_handler,         pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(crypto_paid_handler, pattern="^crypto_paid_"))
    app.add_handler(CallbackQueryHandler(my_account,          pattern="^my_account$"))
    app.add_handler(CallbackQueryHandler(my_orders,           pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(order_detail,        pattern="^order_"))
    app.add_handler(CallbackQueryHandler(wallet,              pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(referral,            pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(free_test,           pattern="^free_test$"))
    app.add_handler(CallbackQueryHandler(support,             pattern="^support$"))
    app.add_handler(CallbackQueryHandler(my_tickets,          pattern="^my_tickets$"))
    app.add_handler(CallbackQueryHandler(ticket_view,         pattern="^ticket_view_"))

    # Admin
    app.add_handler(CallbackQueryHandler(admin_main,          pattern="^admin_main$|^adm_main$"))
    app.add_handler(CallbackQueryHandler(adm_users,           pattern="^adm_users$"))
    app.add_handler(CallbackQueryHandler(adm_user_detail,     pattern="^adm_user_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_ban_handler,     pattern="^adm_ban_|^adm_unban_"))
    app.add_handler(CallbackQueryHandler(adm_plans,           pattern="^adm_plans$"))
    app.add_handler(CallbackQueryHandler(adm_plan_detail,     pattern="^adm_plan_detail_"))
    app.add_handler(CallbackQueryHandler(adm_plan_del,        pattern="^adm_plan_del_"))
    app.add_handler(CallbackQueryHandler(adm_panels,          pattern="^adm_panels$"))
    app.add_handler(CallbackQueryHandler(adm_panel_detail,    pattern="^adm_panel_detail_"))
    app.add_handler(CallbackQueryHandler(adm_panel_restart,   pattern="^adm_panel_restart_"))
    app.add_handler(CallbackQueryHandler(adm_panel_del,       pattern="^adm_panel_del_"))
    app.add_handler(CallbackQueryHandler(adm_sales,           pattern="^adm_sales$"))
    app.add_handler(CallbackQueryHandler(adm_payments,        pattern="^adm_payments$"))
    app.add_handler(CallbackQueryHandler(adm_pay_detail,      pattern="^adm_pay_detail_"))
    app.add_handler(CallbackQueryHandler(adm_pay_confirm,     pattern="^adm_pay_confirm_"))
    app.add_handler(CallbackQueryHandler(adm_pay_reject,      pattern="^adm_pay_reject_"))
    app.add_handler(CallbackQueryHandler(adm_settings,        pattern="^adm_settings$"))
    app.add_handler(CallbackQueryHandler(adm_admins,          pattern="^adm_admins$"))
    app.add_handler(CallbackQueryHandler(adm_del_admin,       pattern="^adm_del_admin_"))

    # Message handlers (catch-all for tx hash)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, tx_hash_received))

    app.add_error_handler(error_handler)
    return app


def main():
    init_db()
    token = Config.BOT_TOKEN or get_setting("bot_token", "")
    if not token or token == "YOUR_BOT_TOKEN":
        raise ValueError("❌ BOT_TOKEN تنظیم نشده! فایل .env را ویرایش کنید.")
    # Sync owner_id to DB if set in env
    if Config.OWNER_ID:
        from database import set_setting
        set_setting("owner_id", str(Config.OWNER_ID))
    logger.info("🚀 ربات شروع به کار کرد...")
    app = build_app(token)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
