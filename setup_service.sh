#!/bin/bash
BOT_DIR=$(pwd)
PYTHON="$BOT_DIR/venv/bin/python"
cat > /etc/systemd/system/vpnbot.service << EOF
[Unit]
Description=VPN Shop Telegram Bot
After=network.target
[Service]
Type=simple
WorkingDirectory=$BOT_DIR
ExecStart=$PYTHON $BOT_DIR/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable vpnbot
systemctl start vpnbot
echo "✅ سرویس راه‌اندازی شد!"
echo "لاگ: journalctl -u vpnbot -f"
