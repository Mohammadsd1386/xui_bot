import aiohttp
import logging

logger = logging.getLogger(__name__)


class ZarinPalService:
    API = "https://api.zarinpal.com/pg/v4/payment/"
    PAY = "https://www.zarinpal.com/pg/StartPay/"

    def __init__(self, merchant: str):
        self.merchant = merchant

    async def request(self, amount: int, description: str, callback_url: str):
        payload = {
            "merchant_id": self.merchant,
            "amount": amount,
            "description": description,
            "callback_url": callback_url,
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.API}request.json", json=payload,
                                  timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json(content_type=None)
                    if data.get("data", {}).get("code") == 100:
                        auth = data["data"]["authority"]
                        return True, f"{self.PAY}{auth}", auth
                    return False, data.get("errors", {}).get("message", "خطای زرین‌پال"), None
        except Exception as e:
            return False, str(e), None

    async def verify(self, authority: str, amount: int):
        payload = {"merchant_id": self.merchant, "authority": authority, "amount": amount}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.API}verify.json", json=payload,
                                  timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json(content_type=None)
                    code = data.get("data", {}).get("code")
                    if code in (100, 101):
                        return True, data["data"].get("ref_id")
                    return False, data.get("errors", {}).get("message", "تأیید نشد")
        except Exception as e:
            return False, str(e)
