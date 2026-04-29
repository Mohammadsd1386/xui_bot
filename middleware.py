"""
Middleware - فیلتر ادمین
"""

import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import Config

logger = logging.getLogger(__name__)
config = Config()


def admin_only(func):
    """دکوراتور: فقط ادمین‌ها اجازه دارند"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id not in config.ADMIN_IDS:
            logger.warning(f"Unauthorized access attempt by user {user.id if user else 'unknown'}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ شما دسترسی به این ربات ندارید."
                )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
