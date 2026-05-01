import aiohttp
import logging
import time
from database import get_db, get_setting

logger = logging.getLogger(__name__)

class ZarinPalService:
    LIVE_URL = "https://api.zarinpal.com/pg/v4/payment/"
    LIVE_PAY = "https://www.zarinpal.com/pg/StartPay/"

    def __init__(self, merchant):
        self.merchant = merchant

    async def request(self, amount, description, callback_url, mobile=None):
        payload = {"merchant_id":self.merchant,"amount":amount,"description":description,"callback_url":callback_url}
        if mobile: payload["metadata"] = {"mobile": mobile}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.LIVE_URL}request.json", json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json(content_type=None)
                    if data.get("data",{}).get("code") == 100:
                        auth = data["data"]["authority"]
                        return True, f"{self.LIVE_PAY}{auth}", auth
                    return False, data.get("errors",{}).get("message","خطای زرین‌پال"), None
        except Exception as e:
            return False, str(e), None

    async def verify(self, authority, amount):
        payload = {"merchant_id":self.merchant,"authority":authority,"amount":amount}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.LIVE_URL}verify.json", json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json(content_type=None)
                    code = data.get("data",{}).get("code")
                    if code in (100,101): return True, data["data"].get("ref_id")
                    return False, data.get("errors",{}).get("message","پرداخت تأیید نشد")
        except Exception as e:
            return False, str(e)

class CryptoChecker:
    @staticmethod
    async def check_usdt_bep20(wallet, expected_amount, since_ts):
        api_key = get_setting("bscscan_api_key","")
        contract = "0x55d398326f99059fF775485246999027B3197955"
        params = {"module":"account","action":"tokentx","contractaddress":contract,"address":wallet,
                  "startblock":0,"endblock":99999999,"sort":"desc","apikey":api_key or "YourApiKeyToken"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://api.bscscan.com/api", params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json(content_type=None)
                    for tx in (data.get("result") or []):
                        if int(tx.get("timeStamp",0)) < since_ts: continue
                        amount = int(tx.get("value",0)) / (10**int(tx.get("tokenDecimal",18)))
                        if amount >= expected_amount * 0.98: return True, tx.get("hash")
        except Exception as e:
            logger.error(f"BSCScan: {e}")
        return False, None

    @staticmethod
    async def check_tron_usdt(wallet, expected_amount, since_ts):
        contract = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        params = {"toAddress":wallet,"contract_address":contract,"limit":20,"start":0}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://apilist.tronscanapi.com/api/transfer/trc20", params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json(content_type=None)
                    for tx in data.get("token_transfers",[]):
                        if tx.get("block_ts",0)/1000 < since_ts: continue
                        if float(tx.get("quant",0))/1e6 >= expected_amount*0.98: return True, tx.get("transaction_id")
        except Exception as e:
            logger.error(f"TronScan: {e}")
        return False, None

    @staticmethod
    async def check_ton(wallet, expected_amount, since_ts):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://toncenter.com/api/v2/getTransactions", params={"address":wallet,"limit":20}, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json(content_type=None)
                    for tx in data.get("result",[]):
                        if tx.get("utime",0) < since_ts: continue
                        if int(tx.get("in_msg",{}).get("value",0))/1e9 >= expected_amount*0.98: return True, None
        except Exception as e:
            logger.error(f"TON: {e}")
        return False, None

async def confirm_payment(payment_id, tx_hash=None):
    with get_db() as db:
        payment = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not payment or dict(payment)["status"] != "pending": return False
        db.execute("UPDATE payments SET status='confirmed',tx_hash=?,confirmed_at=strftime('%s','now') WHERE id=?", (tx_hash, payment_id))
        order_id = dict(payment)["order_id"]
        if order_id:
            db.execute("UPDATE orders SET status='active' WHERE id=?", (order_id,))
        user_id = dict(payment)["user_id"]
        ref = db.execute("SELECT * FROM referrals WHERE referred_id=? AND reward_rial=0", (user_id,)).fetchone()
        if ref:
            reward = int(get_setting("referral_reward_rial","50000"))
            db.execute("UPDATE users SET balance_rial=balance_rial+? WHERE telegram_id=?", (reward, dict(ref)["referrer_id"]))
            db.execute("UPDATE referrals SET reward_rial=? WHERE id=?", (reward, dict(ref)["id"]))
    return True
