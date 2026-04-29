"""
Restart Handler - ریستارت پنل
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from xui_client import XUIClient


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _confirm(update.effective_message)


async def _confirm(msg):
    await msg.reply_text(
        "⚠️ *آیا مطمئنید که می‌خواهید پنل را ریستارت کنید؟*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ بله، ریستارت", callback_data="do_restart"),
                InlineKeyboardButton("❌ لغو", callback_data="main_menu"),
            ]
        ]),
    )


async def handle_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _confirm(query.message)


async def handle_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ در حال ریستارت...")
    
    await query.message.reply_text("⏳ در حال ریستارت پنل...")
    
    xui = XUIClient()
    success, msg = xui.restart_panel()
    
    if success:
        await query.message.reply_text(
            f"✅ {msg}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🖥 وضعیت سرور", callback_data="server_status"),
            ]]),
        )
    else:
        await query.message.reply_text(f"❌ {msg}")


async def handle_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ در حال دریافت وضعیت سرور...")
    
    xui = XUIClient()
    status = xui.get_server_status()
    
    if not status:
        await query.message.reply_text("❌ خطا در دریافت وضعیت سرور.")
        return
    
    cpu = status.get("cpu", 0)
    mem = status.get("mem", {})
    disk = status.get("disk", {})
    xray = status.get("xray", {})
    uptime = status.get("uptime", 0)
    
    mem_used = round(mem.get("current", 0) / (1024**3), 2) if mem else 0
    mem_total = round(mem.get("total", 0) / (1024**3), 2) if mem else 0
    disk_used = round(disk.get("current", 0) / (1024**3), 2) if disk else 0
    disk_total = round(disk.get("total", 0) / (1024**3), 2) if disk else 0
    
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    xray_status = "✅ در حال اجرا" if xray.get("state") == "running" else "❌ متوقف"
    
    await query.message.reply_text(
        f"🖥 *وضعیت سرور*\n"
        f"━━━━━━━━━━━━━━\n"
        f"⬆️ آپتایم: `{hours}h {minutes}m`\n"
        f"🔥 CPU: `{cpu}%`\n"
        f"💾 RAM: `{mem_used}/{mem_total} GB`\n"
        f"💿 دیسک: `{disk_used}/{disk_total} GB`\n"
        f"🚀 Xray: {xray_status}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="server_status"),
            InlineKeyboardButton("🔁 ریستارت", callback_data="restart_confirm"),
        ]]),
    )
