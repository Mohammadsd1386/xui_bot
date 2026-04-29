"""
Clients Handler - لیست کلاینت‌ها
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from xui_client import XUIClient

logger = logging.getLogger(__name__)


def _client_keyboard(client: dict) -> InlineKeyboardMarkup:
    cid = client.get("id", "")
    email = client.get("email", "")
    enabled = client.get("enable", True)
    toggle_text = "🔴 غیرفعال کن" if enabled else "🟢 فعال کن"
    toggle_data = f"toggle_off:{cid}" if enabled else f"toggle_on:{cid}"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"update_client:{cid}"),
            InlineKeyboardButton(toggle_text, callback_data=toggle_data),
        ],
        [
            InlineKeyboardButton("📊 آمار", callback_data=f"client_stat:{email}"),
            InlineKeyboardButton("🔁 ریست ترافیک", callback_data=f"reset_traffic:{cid}:{email}"),
        ],
        [
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_client:{cid}"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="list_clients"),
        ],
    ])


def _format_client(client: dict, xui: XUIClient) -> str:
    email = client.get("email", "-")
    enabled = "✅ فعال" if client.get("enable") else "❌ غیرفعال"
    total_gb = xui.bytes_to_gb(client.get("totalGB", 0))
    limit_ip = client.get("limitIp", 0)
    expire = xui.ms_to_date(client.get("expiryTime", 0))
    
    total_str = f"{total_gb} GB" if total_gb > 0 else "نامحدود"
    ip_str = str(limit_ip) if limit_ip > 0 else "نامحدود"
    
    return (
        f"👤 *{email}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"وضعیت: {enabled}\n"
        f"حجم: {total_str}\n"
        f"آی‌پی مجاز: {ip_str}\n"
        f"انقضا: {expire}"
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    await msg.reply_text("⏳ در حال دریافت لیست...")
    
    xui = XUIClient()
    clients = xui.get_clients()
    
    if not clients:
        await msg.reply_text(
            "❌ کلاینتی پیدا نشد یا خطا در اتصال به پنل.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 تلاش مجدد", callback_data="list_clients")
            ]])
        )
        return
    
    await msg.reply_text(f"📋 *لیست کلاینت‌ها* ({len(clients)} کلاینت)\n\nروی هر کلاینت کلیک کنید:", parse_mode="Markdown")
    
    # ارسال هر کلاینت جداگانه با دکمه‌های مدیریت
    for client in clients:
        text = _format_client(client, xui)
        await msg.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=_client_keyboard(client),
        )


async def handle_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """callback برای دکمه لیست"""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ در حال دریافت لیست...")
    
    xui = XUIClient()
    clients = xui.get_clients()
    
    if not clients:
        await query.message.reply_text("❌ کلاینتی پیدا نشد یا خطا در اتصال.")
        return
    
    await query.message.reply_text(
        f"📋 *لیست کلاینت‌ها* ({len(clients)} کلاینت)", 
        parse_mode="Markdown"
    )
    
    for client in clients:
        text = _format_client(client, xui)
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=_client_keyboard(client),
        )
