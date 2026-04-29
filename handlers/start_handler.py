"""
Start Handler - منوی اصلی
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


MAIN_MENU_TEXT = """
🤖 *پنل مدیریت 3x-ui*

سلام {name}! به ربات مدیریت پنل خوش اومدی.

از دکمه‌های زیر استفاده کن:
"""

MAIN_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("👥 لیست کلاینت‌ها", callback_data="list_clients"),
        InlineKeyboardButton("➕ افزودن کلاینت", callback_data="add_client"),
    ],
    [
        InlineKeyboardButton("📊 آمار مصرف", callback_data="all_stats"),
        InlineKeyboardButton("🔄 ریستارت پنل", callback_data="restart_confirm"),
    ],
    [
        InlineKeyboardButton("🖥 وضعیت سرور", callback_data="server_status"),
    ],
])


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        MAIN_MENU_TEXT.format(name=user.first_name),
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
