"""
Delete Client Handler
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from xui_client import XUIClient
from config import Config

config = Config()
WAITING_DELETE_CONFIRM = 0


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    client_uuid = query.data.split(":")[1]
    context.user_data["delete_uuid"] = client_uuid
    
    xui = XUIClient()
    clients = xui.get_clients()
    client = next((c for c in clients if c.get("id") == client_uuid), None)
    email = client.get("email", "نامشخص") if client else "نامشخص"
    
    await query.message.reply_text(
        f"⚠️ *آیا مطمئنید؟*\n\nکلاینت `{email}` حذف شود؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"del_confirm:yes"),
                InlineKeyboardButton("❌ خیر", callback_data=f"del_confirm:no"),
            ]
        ]),
    )
    return WAITING_DELETE_CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    choice = query.data.split(":")[1]
    
    if choice == "no":
        await query.message.reply_text("❌ حذف لغو شد.")
        context.user_data.clear()
        return ConversationHandler.END
    
    client_uuid = context.user_data.get("delete_uuid")
    await query.message.reply_text("⏳ در حال حذف...")
    
    xui = XUIClient()
    success, msg = xui.delete_client(config.DEFAULT_INBOUND_ID, client_uuid)
    
    if success:
        await query.message.reply_text(
            "✅ *کلاینت با موفقیت حذف شد!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👥 لیست کلاینت‌ها", callback_data="list_clients"),
            ]]),
        )
    else:
        await query.message.reply_text(f"❌ خطا: {msg}")
    
    context.user_data.clear()
    return ConversationHandler.END
