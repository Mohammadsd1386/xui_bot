"""
Add Client Handler - افزودن کلاینت جدید
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from xui_client import XUIClient
from config import Config

logger = logging.getLogger(__name__)
config = Config()

# States
WAITING_CLIENT_NAME = 0
WAITING_CLIENT_GB   = 1
WAITING_CLIENT_DAYS = 2
WAITING_CLIENT_IP   = 3


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    
    await query.message.reply_text(
        "➕ *افزودن کلاینت جدید*\n\n"
        "مرحله ۱/۴\n"
        "📧 نام (ایمیل) کلاینت را وارد کنید:\n\n"
        "_مثال: ali\\_user یا user01_\n\n"
        "برای لغو: /cancel",
        parse_mode="Markdown",
    )
    return WAITING_CLIENT_NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip().replace(" ", "_")
    
    if len(name) < 2:
        await update.message.reply_text("❌ نام باید حداقل ۲ کاراکتر باشد. دوباره وارد کنید:")
        return WAITING_CLIENT_NAME
    
    context.user_data["email"] = name
    
    await update.message.reply_text(
        f"✅ نام: `{name}`\n\n"
        f"مرحله ۲/۴\n"
        f"📦 حجم ترافیک (گیگابایت) را وارد کنید:\n"
        f"_پیش‌فرض: {config.DEFAULT_GB} GB — برای نامحدود 0 وارد کنید_",
        parse_mode="Markdown",
    )
    return WAITING_CLIENT_GB


async def get_gb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        gb = float(update.message.text.strip())
        if gb < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد معتبر وارد کنید (مثال: 10 یا 0.5):")
        return WAITING_CLIENT_GB
    
    context.user_data["total_gb"] = gb
    
    await update.message.reply_text(
        f"✅ حجم: `{gb} GB`\n\n"
        f"مرحله ۳/۴\n"
        f"📅 مدت اعتبار (روز) را وارد کنید:\n"
        f"_پیش‌فرض: {config.DEFAULT_DAYS} — برای نامحدود 0 وارد کنید_",
        parse_mode="Markdown",
    )
    return WAITING_CLIENT_DAYS


async def get_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        days = int(update.message.text.strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید (مثال: 30):")
        return WAITING_CLIENT_DAYS
    
    context.user_data["expire_days"] = days
    
    await update.message.reply_text(
        f"✅ اعتبار: `{days} روز`\n\n"
        f"مرحله ۴/۴\n"
        f"🔌 تعداد آی‌پی مجاز را وارد کنید:\n"
        f"_پیش‌فرض: {config.DEFAULT_IP_LIMIT} — برای نامحدود 0 وارد کنید_",
        parse_mode="Markdown",
    )
    return WAITING_CLIENT_IP


async def get_ip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        ip_limit = int(update.message.text.strip())
        if ip_limit < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد صحیح وارد کنید:")
        return WAITING_CLIENT_IP
    
    context.user_data["limit_ip"] = ip_limit
    
    # نمایش خلاصه
    d = context.user_data
    gb_str = f"{d['total_gb']} GB" if d['total_gb'] > 0 else "نامحدود"
    days_str = f"{d['expire_days']} روز" if d['expire_days'] > 0 else "نامحدود"
    ip_str = str(ip_limit) if ip_limit > 0 else "نامحدود"
    
    processing_msg = await update.message.reply_text(
        f"⏳ در حال ساخت کلاینت...\n\n"
        f"👤 نام: `{d['email']}`\n"
        f"📦 حجم: `{gb_str}`\n"
        f"📅 اعتبار: `{days_str}`\n"
        f"🔌 آی‌پی: `{ip_str}`",
        parse_mode="Markdown",
    )
    
    xui = XUIClient()
    success, result = xui.add_client(
        email=d["email"],
        total_gb=d["total_gb"],
        expire_days=d["expire_days"],
        limit_ip=ip_limit,
    )
    
    if success:
        await processing_msg.edit_text(
            f"✅ *کلاینت با موفقیت ساخته شد!*\n\n"
            f"👤 نام: `{d['email']}`\n"
            f"📦 حجم: `{gb_str}`\n"
            f"📅 اعتبار: `{days_str}`\n"
            f"🔌 آی‌پی: `{ip_str}`\n"
            f"🔑 UUID: `{result}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👥 لیست کلاینت‌ها", callback_data="list_clients"),
                InlineKeyboardButton("➕ کلاینت جدید", callback_data="add_client"),
            ]]),
        )
    else:
        await processing_msg.edit_text(
            f"❌ *خطا در ساخت کلاینت*\n\n{result}",
            parse_mode="Markdown",
        )
    
    context.user_data.clear()
    return ConversationHandler.END
