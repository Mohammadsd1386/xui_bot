"""
Stats Handler - آمار مصرف
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from xui_client import XUIClient


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    await msg.reply_text("⏳ در حال دریافت آمار...")
    await _send_stats(msg)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ در حال دریافت آمار...")
    await _send_stats(query.message)


async def handle_single_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار یک کلاینت خاص"""
    query = update.callback_query
    await query.answer()
    
    email = query.data.split(":")[1]
    xui = XUIClient()
    traffic = xui.get_client_traffic(email)
    
    if not traffic:
        await query.message.reply_text("❌ آمار کلاینت پیدا نشد.")
        return
    
    up = xui.bytes_to_gb(traffic.get("up", 0))
    down = xui.bytes_to_gb(traffic.get("down", 0))
    total = xui.bytes_to_gb(traffic.get("total", 0))
    used = round(up + down, 2)
    enabled = "✅ فعال" if traffic.get("enable") else "❌ غیرفعال"
    
    await query.message.reply_text(
        f"📊 *آمار کلاینت: {email}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"وضعیت: {enabled}\n"
        f"⬆️ آپلود: `{up} GB`\n"
        f"⬇️ دانلود: `{down} GB`\n"
        f"📦 کل مصرف: `{used} GB`\n"
        f"💾 حجم کل: `{total} GB`",
        parse_mode="Markdown",
    )


async def _send_stats(msg):
    xui = XUIClient()
    traffics = xui.get_all_traffics()
    
    if not traffics:
        await msg.reply_text("❌ آماری پیدا نشد یا خطا در اتصال.")
        return
    
    total_used = 0
    lines = []
    
    for t in traffics:
        email = t.get("email", "-")
        up = xui.bytes_to_gb(t.get("up", 0))
        down = xui.bytes_to_gb(t.get("down", 0))
        used = round(up + down, 2)
        total_gb = xui.bytes_to_gb(t.get("total", 0))
        enabled = "✅" if t.get("enable") else "❌"
        total_used += used
        
        total_str = f"/{total_gb}GB" if total_gb > 0 else "/∞"
        lines.append(f"{enabled} `{email}`: {used}GB{total_str}")
    
    text = (
        f"📊 *آمار مصرف کلی*\n"
        f"━━━━━━━━━━━━━━\n"
        f"👥 تعداد کلاینت: {len(traffics)}\n"
        f"📦 کل مصرف: {round(total_used, 2)} GB\n"
        f"━━━━━━━━━━━━━━\n"
    ) + "\n".join(lines)
    
    await msg.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="all_stats"),
        ]]),
    )
