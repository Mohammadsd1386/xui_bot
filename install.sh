#!/bin/bash
# ─────────────────────────────────────────────
# اسکریپت نصب و راه‌اندازی ربات مدیریت 3x-ui
# ─────────────────────────────────────────────

set -e

echo "🚀 شروع نصب ربات مدیریت پنل 3x-ui..."

# بررسی Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python3 نصب نیست. در حال نصب..."
    apt-get update && apt-get install -y python3 python3-pip python3-venv
fi

echo "✅ Python3: $(python3 --version)"

# ساخت محیط مجازی
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ محیط مجازی ساخته شد"
fi

# فعال‌سازی و نصب کتابخانه‌ها
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ کتابخانه‌ها نصب شدند"

# بررسی فایل .env
if [ ! -f ".env" ]; then
    echo "⚠️  فایل .env یافت نشد!"
    echo "لطفاً فایل .env را از روی .env.example بسازید و تنظیم کنید"
    exit 1
fi

# بررسی BOT_TOKEN
BOT_TOKEN=$(grep BOT_TOKEN .env | cut -d'=' -f2)
if [[ "$BOT_TOKEN" == *"YOUR_BOT_TOKEN"* ]] || [ -z "$BOT_TOKEN" ]; then
    echo "⚠️  BOT_TOKEN هنوز تنظیم نشده است!"
    echo "فایل .env را ویرایش کنید"
    exit 1
fi

echo ""
echo "✅ همه چیز آماده است!"
echo ""
echo "برای اجرای ربات:"
echo "  source venv/bin/activate"
echo "  python bot.py"
echo ""
echo "برای اجرا به عنوان سرویس systemd:"
echo "  sudo bash setup_service.sh"
