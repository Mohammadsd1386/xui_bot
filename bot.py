import asyncio
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from config import Config
from xui_api import XUIApi

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(WAITING_CLIENT_EMAIL, WAITING_CLIENT_GB, WAITING_CLIENT_DAYS,
 WAITING_UPDATE_UUID, WAITING_UPDATE_FIELD, WAITING_UPDATE_VALUE,
 WAITING_DELETE_UUID) = range(7)

config = Config()
api = XUIApi(config)


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if config.ADMIN_IDS and user_id not in config.ADMIN_IDS:
            await update.effective_message.reply_text("⛔ دسترسی ندارید.")
            return
        return await func(update, context)
    return wrapper


def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ افزودن کلاینت", callback_data="add_client"),
         InlineKeyboardButton("📋 لیست کلاینت‌ها", callback_data="list_clients")],
        [InlineKeyboardButton("✏️ ویرایش کلاینت", callback_data="update_client"),
         InlineKeyboardButton("🗑 حذف کلاینت", callback_data="delete_client")],
        [InlineKeyboardButton("📊 آمار مصرف", callback_data="stats"),
         InlineKeyboardButton("🔄 ریستارت پنل", callback_data="restart_panel")],
        [InlineKeyboardButton("ℹ️ وضعیت پنل", callback_data="panel_status")],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]])


def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚫 لغو", callback_data="cancel_conv")]])


@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام ادمین!\n\n"
        "🖥 *ربات مدیریت پنل 3x-ui*\n"
        "از منوی زیر عملیات مورد نظر را انتخاب کنید:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )


@admin_only
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📌 *منوی اصلی*\nعملیات مورد نظر را انتخاب کنید:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )


# ─────────────── LIST CLIENTS ───────────────
@admin_only
async def list_clients_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ در حال دریافت اطلاعات...")

    success, data = await api.get_inbounds()
    if not success:
        await query.edit_message_text(f"❌ خطا: {data}", reply_markup=back_keyboard())
        return

    clients = api.extract_all_clients(data)
    if not clients:
        await query.edit_message_text("📭 هیچ کلاینتی یافت نشد.", reply_markup=back_keyboard())
        return

    text = "📋 *لیست کلاینت‌ها:*\n\n"
    for i, c in enumerate(clients[:20], 1):
        status = "✅" if c.get("enable") else "❌"
        gb_total = round(c.get("totalGB", 0) / (1024**3), 2)
        text += (
            f"{i}. {status} `{c.get('email', 'نامشخص')}`\n"
            f"   📦 حجم: {gb_total} GB\n"
            f"   🆔 `{c.get('id', '')}`\n\n"
        )
    if len(clients) > 20:
        text += f"... و {len(clients)-20} کلاینت دیگر\n"

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())


# ─────────────── ADD CLIENT ───────────────
@admin_only
async def add_client_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ *افزودن کلاینت جدید*\n\nنام (email) کلاینت را وارد کنید:\n_(مثال: user123)_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return WAITING_CLIENT_EMAIL


async def add_client_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if not email or " " in email:
        await update.message.reply_text("❌ نام نباید فاصله داشته باشد. دوباره وارد کنید:")
        return WAITING_CLIENT_EMAIL
    context.user_data["new_email"] = email
    await update.message.reply_text(
        f"✅ نام: `{email}`\n\nحجم (GB) را وارد کنید:\n_(مثال: 10)_",
        parse_mode="Markdown"
    )
    return WAITING_CLIENT_GB


async def add_client_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        gb = float(update.message.text.strip())
        if gb <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد معتبر وارد کنید:")
        return WAITING_CLIENT_GB
    context.user_data["new_gb"] = gb
    await update.message.reply_text(
        f"✅ حجم: {gb} GB\n\nمدت اعتبار (روز) را وارد کنید:\n_(0 = نامحدود)_",
        parse_mode="Markdown"
    )
    return WAITING_CLIENT_DAYS


async def add_client_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text.strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return WAITING_CLIENT_DAYS

    email = context.user_data["new_email"]
    gb = context.user_data["new_gb"]

    await update.message.reply_text("⏳ در حال ساخت کلاینت...")
    success, result = await api.add_client(email, gb, days)

    if success:
        await update.message.reply_text(
            f"✅ *کلاینت ساخته شد!*\n\n"
            f"👤 نام: `{email}`\n"
            f"📦 حجم: {gb} GB\n"
            f"⏱ مدت: {'نامحدود' if days == 0 else f'{days} روز'}\n"
            f"🆔 UUID: `{result}`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(f"❌ خطا:\n{result}", reply_markup=main_menu_keyboard())

    context.user_data.clear()
    return ConversationHandler.END


# ─────────────── UPDATE CLIENT ───────────────
@admin_only
async def update_client_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ *ویرایش کلاینت*\n\nUUID کلاینت را وارد کنید:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return WAITING_UPDATE_UUID


async def update_client_uuid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uuid_val = update.message.text.strip()
    context.user_data["update_uuid"] = uuid_val

    keyboard = [
        [InlineKeyboardButton("📦 تغییر حجم", callback_data="upd_gb"),
         InlineKeyboardButton("⏱ تغییر مدت", callback_data="upd_days")],
        [InlineKeyboardButton("✅ فعال‌سازی", callback_data="upd_enable"),
         InlineKeyboardButton("❌ غیرفعال‌سازی", callback_data="upd_disable")],
        [InlineKeyboardButton("🚫 لغو", callback_data="cancel")]
    ]
    await update.message.reply_text(
        f"🆔 UUID: `{uuid_val}`\n\nچه چیزی را ویرایش کنید؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_UPDATE_FIELD


async def update_client_field_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data

    uuid_val = context.user_data.get("update_uuid", "")

    if field in ("upd_enable", "upd_disable"):
        enable = field == "upd_enable"
        await query.edit_message_text("⏳ در حال به‌روزرسانی...")
        success, msg = await api.toggle_client(uuid_val, enable)
        status = ("✅ فعال شد" if enable else "✅ غیرفعال شد") if success else f"❌ {msg}"
        await query.edit_message_text(status, reply_markup=main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    elif field == "upd_gb":
        context.user_data["update_field"] = "gb"
        await query.edit_message_text("📦 حجم جدید (GB) را وارد کنید:")
        return WAITING_UPDATE_VALUE
    elif field == "upd_days":
        context.user_data["update_field"] = "days"
        await query.edit_message_text("⏱ مدت جدید (روز) را وارد کنید (0=نامحدود):")
        return WAITING_UPDATE_VALUE
    elif field == "cancel":
        await query.edit_message_text("🚫 لغو شد.", reply_markup=main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END


async def update_client_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text.strip()
    uuid_val = context.user_data["update_uuid"]
    field = context.user_data["update_field"]

    try:
        val = float(value) if field == "gb" else int(value)
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ مقدار نامعتبر. دوباره وارد کنید:")
        return WAITING_UPDATE_VALUE

    await update.message.reply_text("⏳ در حال به‌روزرسانی...")
    success, msg = await api.update_client_field(uuid_val, field, val)
    result = "✅ با موفقیت به‌روز شد!" if success else f"❌ خطا: {msg}"
    await update.message.reply_text(result, reply_markup=main_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END


# ─────────────── DELETE CLIENT ───────────────
@admin_only
async def delete_client_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🗑 *حذف کلاینت*\n\nUUID کلاینت را وارد کنید:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return WAITING_DELETE_UUID


async def delete_client_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uuid_val = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"confirm_delete:{uuid_val}"),
         InlineKeyboardButton("🚫 لغو", callback_data="main_menu")]
    ]
    await update.message.reply_text(
        f"⚠️ آیا مطمئنید؟\n🆔 `{uuid_val}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def delete_client_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uuid_val = query.data.split(":", 1)[1]

    await query.edit_message_text("⏳ در حال حذف...")
    success, msg = await api.delete_client(uuid_val)
    result = f"✅ کلاینت حذف شد!" if success else f"❌ خطا: {msg}"
    await query.edit_message_text(result, reply_markup=main_menu_keyboard())


# ─────────────── STATS ───────────────
@admin_only
async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ در حال دریافت آمار...")

    success, data = await api.get_inbounds()
    if not success:
        await query.edit_message_text(f"❌ خطا: {data}", reply_markup=back_keyboard())
        return

    clients = api.extract_all_clients(data)
    total = len(clients)
    active = sum(1 for c in clients if c.get("enable"))
    total_gb = round(sum(c.get("totalGB", 0) for c in clients) / (1024**3), 2)

    text = (
        "📊 *آمار کلی پنل*\n\n"
        f"👥 کل کلاینت‌ها: `{total}`\n"
        f"✅ فعال: `{active}`\n"
        f"❌ غیرفعال: `{total - active}`\n"
        f"📦 حجم تخصیص‌یافته: `{total_gb} GB`\n"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())


# ─────────────── RESTART ───────────────
@admin_only
async def restart_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("✅ بله، ریستارت", callback_data="confirm_restart"),
         InlineKeyboardButton("🚫 لغو", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        "⚠️ *آیا از ریستارت پنل مطمئنید؟*\nچند ثانیه سرویس قطع می‌شود.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ در حال ریستارت پنل...")
    success, msg = await api.restart_panel()
    result = "✅ پنل با موفقیت ریستارت شد!" if success else f"❌ خطا: {msg}"
    await query.edit_message_text(result, reply_markup=main_menu_keyboard())


# ─────────────── STATUS ───────────────
@admin_only
async def panel_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ در حال بررسی وضعیت...")

    success, data = await api.get_status()
    if not success:
        await query.edit_message_text(f"❌ پنل در دسترس نیست!\n{data}", reply_markup=back_keyboard())
        return

    clients = api.extract_all_clients(data) if isinstance(data, list) else []
    text = (
        "🖥 *وضعیت پنل*\n\n"
        f"✅ پنل آنلاین است\n"
        f"🌐 آدرس: `{config.PANEL_URL}`\n"
        f"👥 تعداد کلاینت‌ها: `{len(clients)}`\n"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())


# ─────────────── CANCEL ───────────────
async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("🚫 لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🚫 لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception:", exc_info=context.error)


# ─────────────── MAIN ───────────────
def main():
    app = Application.builder().token(config.BOT_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_client_start, pattern="^add_client$")],
        states={
            WAITING_CLIENT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_email)],
            WAITING_CLIENT_GB:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_gb)],
            WAITING_CLIENT_DAYS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_days)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$"),
            CommandHandler("cancel", cancel_command),
        ],
    )

    update_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(update_client_start, pattern="^update_client$")],
        states={
            WAITING_UPDATE_UUID:  [MessageHandler(filters.TEXT & ~filters.COMMAND, update_client_uuid)],
            WAITING_UPDATE_FIELD: [CallbackQueryHandler(update_client_field_cb, pattern="^upd_|^cancel$")],
            WAITING_UPDATE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_client_value)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$"),
            CommandHandler("cancel", cancel_command),
        ],
    )

    delete_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_client_start, pattern="^delete_client$")],
        states={
            WAITING_DELETE_UUID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_client_confirm)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$"),
            CommandHandler("cancel", cancel_command),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(add_conv)
    app.add_handler(update_conv)
    app.add_handler(delete_conv)
    app.add_handler(CallbackQueryHandler(list_clients_handler,   pattern="^list_clients$"))
    app.add_handler(CallbackQueryHandler(stats_handler,          pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(restart_panel_handler,  pattern="^restart_panel$"))
    app.add_handler(CallbackQueryHandler(confirm_restart,        pattern="^confirm_restart$"))
    app.add_handler(CallbackQueryHandler(panel_status_handler,   pattern="^panel_status$"))
    app.add_handler(CallbackQueryHandler(delete_client_execute,  pattern="^confirm_delete:"))
    app.add_handler(CallbackQueryHandler(menu,                   pattern="^main_menu$"))
    app.add_error_handler(error_handler)

    logger.info("✅ ربات شروع به کار کرد...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
