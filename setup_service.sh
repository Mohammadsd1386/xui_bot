#!/bin/bash
# ─────────────────────────────────────────────
# راه‌اندازی سرویس systemd برای ربات
# ─────────────────────────────────────────────

BOT_DIR=$(pwd)
PYTHON_PATH="$BOT_DIR/venv/bin/python"

echo "📦 در حال ساخت سرویس systemd..."

cat > /etc/systemd/system/xui-bot.service << EOF
[Unit]
Description=3x-ui Telegram Bot Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
ExecStart=$PYTHON_PATH $BOT_DIR/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xui-bot
systemctl start xui-bot

echo ""
echo "✅ سرویس با موفقیت راه‌اندازی شد!"
echo ""
echo "دستورات مفید:"
echo "  systemctl status xui-bot     # وضعیت"
echo "  systemctl stop xui-bot       # توقف"
echo "  systemctl restart xui-bot    # ریستارت"
echo "  journalctl -u xui-bot -f     # لاگ‌ها"
