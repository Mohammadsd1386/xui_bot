from telegram import Update
from telegram.ext import ContextTypes
from services.db_service import is_admin, get_user


def require_admin(func):
    """Decorator: only admins can use this."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not is_admin(uid):
            if update.callback_query:
                await update.callback_query.answer("⛔ دسترسی ندارید.", show_alert=True)
            else:
                await update.message.reply_text("⛔ دسترسی ندارید.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


def require_not_banned(func):
    """Decorator: blocked users cannot use bot."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        user = get_user(uid)
        if user and user.get("is_banned"):
            if update.callback_query:
                await update.callback_query.answer("🚫 حساب شما مسدود شده.", show_alert=True)
            else:
                await update.message.reply_text("🚫 حساب شما مسدود شده است.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


async def answer(update: Update, text: str, kb=None, parse_mode="Markdown", edit=True):
    """Helper: answer callback or send message."""
    query = update.callback_query
    if query:
        if edit:
            try:
                await query.edit_message_text(text, reply_markup=kb, parse_mode=parse_mode)
            except Exception:
                await query.message.reply_text(text, reply_markup=kb, parse_mode=parse_mode)
        else:
            await query.message.reply_text(text, reply_markup=kb, parse_mode=parse_mode)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=parse_mode)
