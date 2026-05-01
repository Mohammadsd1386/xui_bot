#!/bin/bash
set -e
echo "🚀 نصب ربات VPN..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -q
echo "✅ نصب کامل شد!"
echo ""
echo "اقدامات بعدی:"
echo "1. فایل .env را ویرایش کنید"
echo "2. python bot.py را اجرا کنید"
echo "3. در تلگرام /setup <SETUP_TOKEN> ارسال کنید"
