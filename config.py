import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
    PANEL_URL: str = os.getenv("PANEL_URL", "http://your-panel-ip:port")
    PANEL_PATH: str = os.getenv("PANEL_PATH", "/UIsCCndjcqGPoV1RbI")
    PANEL_USER: str = os.getenv("PANEL_USER", "admin")
    PANEL_PASS: str = os.getenv("PANEL_PASS", "admin")
    INBOUND_ID: int = int(os.getenv("INBOUND_ID", "1"))

    # Admin Telegram user IDs (comma separated)
    _admin_ids = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS: list = [int(i.strip()) for i in _admin_ids.split(",") if i.strip()] if _admin_ids else []
