"""ارسال جزئیات کامل سرویس (متن + QR) به کاربر پس از فعال‌سازی."""
from __future__ import annotations

import html
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from utils.helpers import fmt_bytes, fmt_date, fmt_rial, days_left


def sub_qr_url(sub_link: str) -> str:
    return f"https://api.qrserver.com/v1/create-qr-code/?size=512x512&data={quote(sub_link, safe='')}"


def _nav_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 سرویس‌های من", callback_data="my_orders"),
            InlineKeyboardButton("🏠 منو", callback_data="main_menu"),
        ]
    ])


def build_activation_html(
    order: dict,
    *,
    plan_name: str | None,
    sub_link: str,
    client_uuid: str,
    traffic: dict | None = None,
    title: str = "سرویس شما آماده است ✨",
) -> str:
    cfg = order.get("config_name") or order.get("client_email") or "—"
    exp = order.get("expires_at") or 0
    lines = [
        f"🎉 <b>{html.escape(title)}</b>",
        "",
        f"📋 <b>سفارش:</b> <code>#{order.get('id')}</code>",
    ]
    if plan_name:
        lines.append(f"📦 <b>پلن:</b> {html.escape(str(plan_name))}")
    lines.extend([
        f"🏷 <b>نام کانفیگ:</b> <code>{html.escape(str(cfg))}</code>",
        f"🆔 <b>شناسه کلاینت (UUID):</b> <code>{html.escape(str(client_uuid))}</code>",
        f"💾 <b>حجم:</b> {html.escape(str(order.get('gb', 0)))} GB",
        f"📅 <b>مدت:</b> {html.escape(str(order.get('days', 0)))} روز",
        f"⏰ <b>انقضا:</b> {html.escape(fmt_date(exp))} — {html.escape(str(days_left(exp)))}",
    ])
    paid = order.get("price_paid")
    if paid is not None and int(paid or 0) > 0:
        lines.append(f"💰 <b>مبلغ پرداخت:</b> {html.escape(fmt_rial(paid))}")
    if traffic:
        used = int(traffic.get("up", 0) or 0) + int(traffic.get("down", 0) or 0)
        total = int(traffic.get("total", 0) or 0)
        lines.append(f"📊 <b>مصرف فعلی:</b> {html.escape(fmt_bytes(used))} / {html.escape(fmt_bytes(total))}")
        lo_ms = traffic.get("last_online") or 0
        lo = int(lo_ms / 1000) if lo_ms else 0
        if lo > 0:
            lines.append(f"🕒 <b>آخرین اتصال:</b> {html.escape(fmt_date(lo))}")
        else:
            lines.append("🕒 <b>آخرین اتصال:</b> هنوز گزارش نشده")
    lines.extend([
        "",
        "🔗 <b>لینک اشتراک (همه کانفیگ‌های ساب):</b>",
        f"<code>{html.escape(sub_link or '—')}</code>",
        "",
        "<i>این لینک را در اپ VPN خود وارد کنید یا QR را اسکن کنید.</i>",
    ])
    return "\n".join(lines)


async def send_activation_to_user(
    bot,
    chat_id: int,
    order: dict,
    *,
    plan_name: str | None = None,
    sub_link: str = "",
    client_uuid: str = "",
    traffic: dict | None = None,
    title: str = "سرویس شما آماده است ✨",
) -> None:
    text = build_activation_html(
        order,
        plan_name=plan_name,
        sub_link=sub_link,
        client_uuid=client_uuid,
        traffic=traffic,
        title=title,
    )
    kb = _nav_kb()
    try:
        await bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception:
        await bot.send_message(chat_id, text, reply_markup=kb)
    if sub_link:
        try:
            await bot.send_photo(
                chat_id,
                sub_qr_url(sub_link),
                caption="📱 QR کد لینک اشتراک",
            )
        except Exception:
            pass
