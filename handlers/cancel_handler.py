"""
Cancel & Message Handlers
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد. /start برای منوی اصلی")
    return ConversationHandler.END


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "برای مشاهده منوی اصلی دستور /start را وارد کنید."
    )
