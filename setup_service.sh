#!/bin/bash
DIR=$(pwd)
PYTHON="$DIR/venv/bin/python3"
cat > /etc/systemd/system/vpnbot.service << EOF
[Unit]
Description=VPN Shop Bot
After=network.target
[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$PYTHON $DIR/bot.py
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
echo "✅ سرویس فعال شد!"
echo "لاگ: journalctl -u vpnbot -f"
