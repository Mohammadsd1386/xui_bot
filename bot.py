import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

from database import init_db, get_setting, set_setting
from services.db_service import upsert_user, is_admin, get_admin_ids
from keyboards.menus import main_menu_kb, back_btn

# ── Handler imports ────────────────────────────────────────────────────────────
from handlers.user_handler import (
    my_account, my_orders, order_detail, wallet, referral, free_test,
    support, new_ticket_start, ticket_subject, ticket_message,
    my_tickets, ticket_view,
    admin_ticket_reply_start, admin_ticket_reply_send,
    S_TICKET_SUBJECT, S_TICKET_MSG, S_TICKET_REPLY,
)
from handlers.shop_handler import (
    shop, plan_selected, pay_handler, crypto_paid, receive_hash,
    extend_start, extend_value, S_EXTEND_VAL,
)
from handlers.admin_handler import (
    adm_main, adm_users, adm_users_page, adm_user_detail, adm_ban,
    adm_discount_start, adm_discount_val,
    adm_topup_start, adm_topup_val,
    adm_plans, adm_plan_detail, adm_plan_toggle, adm_plan_del,
    adm_plan_add_start, adm_plan_name, adm_plan_gb, adm_plan_days,
    adm_plan_price, adm_plan_save_panel,
    adm_panels, adm_panel_detail, adm_panel_toggle, adm_panel_del,
    adm_panel_restart, adm_panel_clients,
    adm_panel_add_start, adm_panel_name, adm_panel_type_cb,
    adm_panel_url, adm_panel_path, adm_panel_user, adm_panel_pass, adm_panel_ib,
    adm_payments, adm_pay_detail, adm_pay_ok, adm_pay_no,
    adm_sales, adm_settings, adm_setting_start, adm_setting_val,
    adm_admins, adm_add_admin_start, adm_add_admin_val, adm_del_admin,
    adm_broadcast_start, adm_broadcast_send,
    cancel,
    S_SET_VAL,
    S_PLAN_NAME, S_PLAN_GB, S_PLAN_DAYS, S_PLAN_PRICE,
    S_PANEL_NAME, S_PANEL_URL, S_PANEL_PATH, S_PANEL_USER, S_PANEL_PASS, S_PANEL_IB,
    S_ADMIN_ID, S_BROADCAST, S_TOPUP, S_DISCOUNT,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ── START ──────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []

    referrer_id = None
    if args and args[0].startswith("ref"):
        try:
            referrer_id = int(args[0][3:])
            if referrer_id == user.id:
                referrer_id = None
        except ValueError:
            pass

    upsert_user(user.id, user.username, user.full_name, referrer_id)

    # Channel check
    ch = get_setting("channel_id")
    if ch and get_setting("channel_join_required") == "1":
        try:
            member = await context.bot.get_chat_member(ch, user.id)
            if member.status in ("left", "kicked"):
                ch_name = ch.lstrip("@")
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{ch_name}")],
                    [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")],
                ])
                await update.message.reply_text(
                    f"⚠️ برای استفاده از ربات باید در کانال عضو شوید:\n{ch}",
                    reply_markup=kb
                )
                return
        except Exception:
            pass

    adm = is_admin(user.id)
    bot_name = get_setting("bot_name", "ربات فروش VPN")
    await update.message.reply_text(
        f"👋 سلام *{user.first_name}*!\n\n🌐 *{bot_name}*\n\nاز منوی زیر استفاده کنید:",
        reply_markup=main_menu_kb(adm),
        parse_mode="Markdown"
    )


async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    adm = is_admin(user.id)
    bot_name = get_setting("bot_name", "ربات فروش VPN")
    await query.edit_message_text(
        f"🌐 *{bot_name}*\n\nاز منوی زیر استفاده کنید:",
        reply_markup=main_menu_kb(adm),
        parse_mode="Markdown"
    )


async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ch = get_setting("channel_id")
    if not ch:
        await query.edit_message_text("✅", reply_markup=main_menu_kb(is_admin(update.effective_user.id)))
        return
    try:
        member = await context.bot.get_chat_member(ch, update.effective_user.id)
        if member.status not in ("left", "kicked"):
            await query.edit_message_text(
                "✅ عضویت تأیید شد!",
                reply_markup=main_menu_kb(is_admin(update.effective_user.id))
            )
            return
    except Exception:
        pass
    await query.answer("❌ هنوز عضو نشده‌اید.", show_alert=True)


async def setup_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import os
    args = context.args or []
    expected = os.getenv("SETUP_TOKEN", "")
    if not expected:
        await update.message.reply_text("❌ SETUP_TOKEN تنظیم نشده.")
        return
    if not args or args[0] != expected:
        await update.message.reply_text("❌ توکن اشتباه است.")
        return
    set_setting("owner_id", str(update.effective_user.id))
    await update.message.reply_text(
        f"✅ شما مالک ربات هستید!\n🆔 `{update.effective_user.id}`",
        parse_mode="Markdown"
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception:", exc_info=context.error)


# ── BUILD ──────────────────────────────────────────────────────────────────────

def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()

    # ─── Conversations ─────────────────────────────────────────────────────────

    # Add plan (multi-step)
    plan_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_plan_add_start, pattern="^adm_plan_add$")],
        states={
            S_PLAN_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_name)],
            S_PLAN_GB:    [
                MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_gb),
                # panel selection callback arrives here too
                CallbackQueryHandler(adm_plan_save_panel, pattern="^adm_plan_panel_"),
            ],
            S_PLAN_DAYS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_days)],
            S_PLAN_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, adm_plan_price),
                CallbackQueryHandler(adm_plan_save_panel, pattern="^adm_plan_panel_"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^adm_plans$"),
            CommandHandler("cancel", cancel),
        ],
        per_message=False,
    )

    # Add panel (multi-step)
    panel_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_panel_add_start, pattern="^adm_panel_add$")],
        states={
            S_PANEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_name)],
            S_PANEL_URL:  [
                CallbackQueryHandler(adm_panel_type_cb, pattern="^pt_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_url),
            ],
            S_PANEL_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_path)],
            S_PANEL_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_user)],
            S_PANEL_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_pass)],
            S_PANEL_IB:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_panel_ib)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^adm_panels$"),
            CommandHandler("cancel", cancel),
        ],
        per_message=False,
    )

    # Settings value input
    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(
            adm_setting_start,
            pattern="^(set_usd_rate|set_referral|set_usdt_addr|set_tron_addr|set_ton_addr"
                    "|set_zarinpal|set_support|set_bot_name|set_channel"
                    "|set_free_test|ft_on|ft_off|ft_set_gb|ft_set_days)$"
        )],
        states={
            S_SET_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_setting_val)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^adm_settings$"),
            CommandHandler("cancel", cancel),
        ],
        per_message=False,
    )

    # Discount
    discount_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_discount_start, pattern="^adm_discount_\\d+$")],
        states={S_DISCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_discount_val)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # Top-up
    topup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_topup_start, pattern="^adm_topup_\\d+$")],
        states={S_TOPUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_topup_val)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # Add admin
    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_add_admin_start, pattern="^adm_add_admin$")],
        states={S_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_admin_val)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # Broadcast
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_broadcast_start, pattern="^adm_broadcast$")],
        states={S_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_broadcast_send)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # Ticket (user)
    ticket_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(new_ticket_start, pattern="^new_ticket$")],
        states={
            S_TICKET_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_subject)],
            S_TICKET_MSG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_message)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^support$"),
            CommandHandler("cancel", cancel),
        ],
        per_message=False,
    )

    # Ticket reply (admin)
    ticket_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_ticket_reply_start, pattern="^ticket_reply_\\d+$")],
        states={S_TICKET_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ticket_reply_send)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # Extend order
    extend_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(extend_start, pattern="^extend_(gb|days)_\\d+$")],
        states={S_EXTEND_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, extend_value)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    # ─── Register conversations first ─────────────────────────────────────────
    for conv in [
        plan_add_conv, panel_add_conv, settings_conv,
        discount_conv, topup_conv, add_admin_conv, broadcast_conv,
        ticket_conv, ticket_reply_conv, extend_conv,
    ]:
        app.add_handler(conv)

    # ─── Commands ─────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu",  start))
    app.add_handler(CommandHandler("setup", setup_owner))

    # ─── Callback handlers ────────────────────────────────────────────────────
    # Global nav
    app.add_handler(CallbackQueryHandler(main_menu_cb, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(check_join,   pattern="^check_join$"))

    # User
    app.add_handler(CallbackQueryHandler(shop,          pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(plan_selected, pattern="^plan_\\d+$"))
    app.add_handler(CallbackQueryHandler(pay_handler,   pattern="^pay_(balance|zarinpal|usdt|tron|ton)_\\d+$"))
    app.add_handler(CallbackQueryHandler(crypto_paid,   pattern="^crypto_paid_\\d+$"))
    app.add_handler(CallbackQueryHandler(my_account,    pattern="^my_account$"))
    app.add_handler(CallbackQueryHandler(my_orders,     pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(order_detail,  pattern="^order_\\d+$"))
    app.add_handler(CallbackQueryHandler(wallet,        pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(referral,      pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(free_test,     pattern="^free_test$"))
    app.add_handler(CallbackQueryHandler(support,       pattern="^support$"))
    app.add_handler(CallbackQueryHandler(my_tickets,    pattern="^my_tickets$"))
    app.add_handler(CallbackQueryHandler(ticket_view,   pattern="^ticket_view_\\d+$"))

    # Admin nav
    app.add_handler(CallbackQueryHandler(adm_main,          pattern="^adm_main$"))
    app.add_handler(CallbackQueryHandler(adm_users,         pattern="^adm_users$"))
    app.add_handler(CallbackQueryHandler(adm_users,         pattern="^adm_user_search$"))
    app.add_handler(CallbackQueryHandler(adm_users_page,    pattern="^adm_users_page_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_user_detail,   pattern="^adm_user_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_ban,           pattern="^adm_(ban|unban)_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_plans,         pattern="^adm_plans$"))
    app.add_handler(CallbackQueryHandler(adm_plan_detail,   pattern="^adm_plan_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_plan_toggle,   pattern="^adm_plan_(enable|disable)_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_plan_del,      pattern="^adm_plan_del_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_panels,        pattern="^adm_panels$"))
    app.add_handler(CallbackQueryHandler(adm_panel_detail,  pattern="^adm_panel_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_panel_toggle,  pattern="^adm_panel_toggle_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_panel_del,     pattern="^adm_panel_del_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_panel_restart, pattern="^adm_panel_restart_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_panel_clients, pattern="^adm_panel_clients_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_payments,      pattern="^adm_payments$"))
    app.add_handler(CallbackQueryHandler(adm_pay_detail,    pattern="^adm_pay_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_pay_ok,        pattern="^adm_pay_ok_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_pay_no,        pattern="^adm_pay_no_\\d+$"))
    app.add_handler(CallbackQueryHandler(adm_sales,         pattern="^adm_sales$"))
    app.add_handler(CallbackQueryHandler(adm_settings,      pattern="^adm_settings$"))
    app.add_handler(CallbackQueryHandler(adm_admins,        pattern="^adm_admins$"))
    app.add_handler(CallbackQueryHandler(adm_del_admin,     pattern="^adm_del_admin_\\d+$"))

    # ─── Catch-all for tx hash: text OR photo ──────────────────────────────────
    # Must come LAST so ConversationHandlers get priority
    hash_filter = (filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.IMAGE
    app.add_handler(MessageHandler(hash_filter, receive_hash))

    app.add_error_handler(error_handler)
    return app


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    import os

    # ── LICENSE CHECK ──────────────────────────────────────────────────────────
    from license import load_and_verify
    print("\n🔑 بررسی لایسنس...")
    ok, info = load_and_verify()
    if not ok:
        print("\n" + "=" * 60)
        print("❌  لایسنس نامعتبر یا یافت نشد")
        print("=" * 60)
        print(info)
        print("=" * 60 + "\n")
        sys.exit(1)

    from datetime import datetime
    exp = info.get("exp", 0)
    exp_str = "مادام‌العمر" if exp == 0 else datetime.fromtimestamp(exp).strftime("%Y/%m/%d")
    print(f"✅ لایسنس معتبر | {info.get('name') or '—'} | انقضا: {exp_str}")
    if exp > 0:
        import time
        left = int((exp - time.time()) / 86400)
        if left <= 7:
            print(f"⚠️  لایسنس {left} روز دیگر منقضی می‌شود!")
    print()
    # ──────────────────────────────────────────────────────────────────────────

    init_db()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("❌ BOT_TOKEN در فایل .env تنظیم نشده!")
        sys.exit(1)

    owner = os.getenv("OWNER_ID", "").strip()
    if owner:
        set_setting("owner_id", owner)

    logger.info("🚀 ربات در حال اجرا...")
    app = build_app(token)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
