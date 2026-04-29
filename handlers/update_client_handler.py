"""
Update Client Handler - ویرایش کلاینت
"""

import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from xui_client import XUIClient

logger = logging.getLogger(__name__)

WAITING_UPDATE_FIELD = 0
WAITING_UPDATE_VALUE = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    client_uuid = query.data.split(":")[1]
    context.user_data["update_uuid"] = client_uuid
    
    # پیدا کردن کلاینت
    xui = XUIClient()
    clients = xui.get_clients()
    client = next((c for c in clients if c.get("id") == client_uuid), None)
    
    if not client:
        await query.message.reply_text("❌ کلاینت پیدا نشد.")
        return ConversationHandler.END
    
    context.user_data["current_client"] = client
    email = client.get("email", "-")
    
    await query.message.reply_text(
        f"✏️ *ویرایش کلاینت: {email}*\n\nکدام فیلد را می‌خواهید ویرایش کنید؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📧 نام (email)", callback_data="upd_field:email")],
            [InlineKeyboardButton("📦 حجم ترافیک (GB)", callback_data="upd_field:gb")],
            [InlineKeyboardButton("📅 اعتبار (روز)", callback_data="upd_field:days")],
            [InlineKeyboardButton("🔌 تعداد آی‌پی", callback_data="upd_field:ip")],
            [InlineKeyboardButton("❌ لغو", callback_data="list_clients")],
        ]),
    )
    return WAITING_UPDATE_FIELD


async def select_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    field = query.data.split(":")[1]
    context.user_data["update_field"] = field
    
    prompts = {
        "email": "📧 نام جدید (ایمیل) را وارد کنید:",
        "gb":    "📦 حجم جدید (گیگابایت) را وارد کنید:\n_برای نامحدود 0 وارد کنید_",
        "days":  "📅 مدت اعتبار جدید (روز از امروز) را وارد کنید:\n_برای نامحدود 0 وارد کنید_",
        "ip":    "🔌 تعداد آی‌پی مجاز جدید را وارد کنید:\n_برای نامحدود 0 وارد کنید_",
    }
    
    await query.message.reply_text(
        prompts.get(field, "مقدار جدید را وارد کنید:"),
        parse_mode="Markdown",
    )
    return WAITING_UPDATE_VALUE


async def get_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data.get("update_field")
    client_uuid = context.user_data.get("update_uuid")
    value_text = update.message.text.strip()
    
    updates = {}
    display = ""
    
    try:
        if field == "email":
            updates["email"] = value_text.replace(" ", "_")
            display = f"نام: `{updates['email']}`"
        
        elif field == "gb":
            gb = float(value_text)
            updates["totalGB"] = int(gb * 1024 ** 3)
            display = f"حجم: `{gb} GB`" if gb > 0 else "حجم: نامحدود"
        
        elif field == "days":
            days = int(value_text)
            if days <= 0:
                updates["expiryTime"] = 0
                display = "اعتبار: نامحدود"
            else:
                updates["expiryTime"] = int((time.time() + days * 86400) * 1000)
                display = f"اعتبار: `{days} روز`"
        
        elif field == "ip":
            updates["limitIp"] = int(value_text)
            display = f"آی‌پی: `{updates['limitIp']}`" if updates["limitIp"] > 0 else "آی‌پی: نامحدود"
        
        else:
            await update.message.reply_text("❌ فیلد نامعتبر.")
            return ConversationHandler.END
            
    except ValueError:
        await update.message.reply_text("❌ مقدار نامعتبر. دوباره وارد کنید:")
        return WAITING_UPDATE_VALUE
    
    await update.message.reply_text("⏳ در حال آپدیت...")
    
    xui = XUIClient()
    success, msg = xui.update_client(client_uuid, updates)
    
    if success:
        await update.message.reply_text(
            f"✅ *کلاینت آپدیت شد!*\n\n{display}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👥 لیست کلاینت‌ها", callback_data="list_clients"),
            ]]),
        )
    else:
        await update.message.reply_text(f"❌ خطا: {msg}")
    
    context.user_data.clear()
    return ConversationHandler.END
