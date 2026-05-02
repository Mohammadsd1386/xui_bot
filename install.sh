#!/bin/bash
set -e
echo "🚀 نصب ربات VPN Shop..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -q
echo ""
echo "✅ نصب کامل شد!"
echo ""
echo "مراحل بعدی:"
echo "  1. فایل .env را ویرایش کنید"
echo "  2. لایسنس دریافت کنید: python3 license_tool.py hwid"
echo "  3. لایسنس را نصب کنید: echo 'KEY' > .license"
echo "  4. اجرا: source venv/bin/activate && python3 bot.py"
echo "  5. در تلگرام: /setup <SETUP_TOKEN>"
