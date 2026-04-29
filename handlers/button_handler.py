"""
Button Handler - مسیریابی همه callback ها
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers import (
    clients_handler, stats_handler, restart_handler
)
from xui_client import XUIClient
from config import Config

logger = logging.getLogger(__name__)
config = Config()


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # لیست کلاینت‌ها
    if data == "list_clients":
        await query.answer()
        await clients_handler.handle_list_callback(update, context)
    
    # آمار همه کلاینت‌ها
    elif data == "all_stats":
        await query.answer()
        await stats_handler.handle_callback(update, context)
    
    # آمار یک کلاینت
    elif data.startswith("client_stat:"):
        await stats_handler.handle_single_callback(update, context)
    
    # ریستارت - تأیید
    elif data == "restart_confirm":
        await query.answer()
        await restart_handler.handle_confirm_callback(update, context)
    
    # ریستارت - اجرا
    elif data == "do_restart":
        await restart_handler.handle_do_callback(update, context)
    
    # وضعیت سرور
    elif data == "server_status":
        await restart_handler.handle_status_callback(update, context)
    
    # فعال/غیرفعال کردن
    elif data.startswith("toggle_on:") or data.startswith("toggle_off:"):
        await query.answer()
        action, cid = data.split(":")
        enable = action == "toggle_on"
        await _toggle_client(query, cid, enable)
    
    # ریست ترافیک
    elif data.startswith("reset_traffic:"):
        await query.answer()
        parts = data.split(":")
        cid, email = parts[1], parts[2]
        await _reset_traffic(query, email)
    
    # منوی اصلی
    elif data == "main_menu":
        await query.answer()
        from handlers.start_handler import MAIN_KEYBOARD, MAIN_MENU_TEXT
        user = update.effective_user
        await query.message.reply_text(
            MAIN_MENU_TEXT.format(name=user.first_name),
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
    
    else:
        await query.answer("⚠️ دستور نامشخص")


async def _toggle_client(query, client_uuid: str, enable: bool):
    xui = XUIClient()
    success, msg = xui.toggle_client(client_uuid, enable)
    state = "✅ فعال" if enable else "❌ غیرفعال"
    
    if success:
        await query.message.reply_text(
            f"{state} — کلاینت با موفقیت {'فعال' if enable else 'غیرفعال'} شد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👥 لیست کلاینت‌ها", callback_data="list_clients"),
            ]]),
        )
    else:
        await query.message.reply_text(f"❌ خطا: {msg}")


async def _reset_traffic(query, email: str):
    xui = XUIClient()
    success, msg = xui.reset_client_traffic(config.DEFAULT_INBOUND_ID, email)
    if success:
        await query.message.reply_text(
            f"✅ ترافیک کلاینت `{email}` ریست شد.",
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text(f"❌ خطا: {msg}")
