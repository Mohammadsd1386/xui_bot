import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))

    @staticmethod
    def get(key, default=None):
        from database import get_setting
        return get_setting(key, default)

    @staticmethod
    def usd_to_rial():
        from database import get_setting
        return int(get_setting("usd_to_rial", "650000"))

    @staticmethod
    def referral_reward():
        from database import get_setting
        return int(get_setting("referral_reward_rial", "50000"))

    @staticmethod
    def free_test_enabled():
        from database import get_setting
        return get_setting("free_test_enabled", "0") == "1"

    @staticmethod
    def free_test_gb():
        from database import get_setting
        return float(get_setting("free_test_gb", "1"))

    @staticmethod
    def free_test_days():
        from database import get_setting
        return int(get_setting("free_test_days", "3"))
