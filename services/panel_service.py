import aiohttp
import json
import uuid
import time
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class XUIApi:
    def __init__(self, panel: dict):
        self.panel = panel
        base = panel["url"].rstrip("/")
        path = (panel.get("path") or "").strip("/")
        self.base = f"{base}/{path}" if path else base
        self._cookie = None

    async def _login(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{self.base}/login",
                    data={"username": self.panel["username"], "password": self.panel["password"]},
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as r:
                    data = await r.json(content_type=None)
                    if data.get("success"):
                        self._cookie = {k: v.value for k, v in r.cookies.items()}
                        return True
        except Exception as e:
            logger.error(f"XUI login: {e}")
        return False

    async def _req(self, method: str, endpoint: str, data: dict = None, retry: bool = True):
        if not self._cookie:
            if not await self._login():
                return False, "خطا در ورود به پنل"
        url = f"{self.base}/panel/api{endpoint}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest"
        }
        try:
            async with aiohttp.ClientSession(cookies=self._cookie) as s:
                kw = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=15)}
                if data:
                    kw["data"] = urlencode(data)
                async with s.request(method, url, **kw) as r:
                    if r.status == 401 and retry:
                        self._cookie = None
                        return await self._req(method, endpoint, data, False)
                    try:
                        res = await r.json(content_type=None)
                    except Exception:
                        res = {"success": r.status < 300, "msg": await r.text()}
                    if res.get("success"):
                        return True, res.get("obj", res)
                    return False, res.get("msg", "خطا")
        except aiohttp.ClientConnectorError:
            return False, "اتصال به پنل برقرار نشد"
        except Exception as e:
            return False, str(e)

    def _rand_sub(self) -> str:
        import random, string
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))

    async def get_inbounds(self):
        return await self._req("GET", "/inbounds/list")

    async def add_client(self, email: str, gb: float, days: int, inbound_id: int = None):
        uid = str(uuid.uuid4())
        ib_id = inbound_id or self.panel.get("inbound_id", 1)
        expiry = int((time.time() + days * 86400) * 1000) if days > 0 else 0
        sub_id = self._rand_sub()
        client = {
            "id": uid, "flow": "", "email": email, "limitIp": 0,
            "totalGB": int(gb * 1024 ** 3), "expiryTime": expiry,
            "enable": True, "tgId": "", "subId": sub_id, "comment": "", "reset": 0
        }
        settings = json.dumps({"clients": [client]})
        ok, res = await self._req("POST", "/inbounds/addClient", {"id": ib_id, "settings": settings})
        if ok:
            sub_link = f"http://v2.vipiranpanel.ir:2095/{sub_id}"
            return True, {"uuid": uid, "sub_link": sub_link}
        return False, res

    async def _find_client(self, target_uuid: str):
        ok, ibs = await self.get_inbounds()
        if not ok or not isinstance(ibs, list):
            return None, None
        for ib in ibs:
            try:
                s = ib.get("settings", "{}")
                settings = json.loads(s) if isinstance(s, str) else s
                for c in settings.get("clients", []):
                    if c.get("id") == target_uuid:
                        return c, ib
            except Exception:
                pass
        return None, None

    async def renew_client(self, target_uuid: str, extra_gb: float = 0, extra_days: int = 0):
        client, ib = await self._find_client(target_uuid)
        if not client:
            return False, "کلاینت یافت نشد"
        if extra_gb > 0:
            client["totalGB"] = client.get("totalGB", 0) + int(extra_gb * 1024 ** 3)
        if extra_days > 0:
            base = max(client.get("expiryTime", 0) / 1000, time.time())
            client["expiryTime"] = int((base + extra_days * 86400) * 1000)
        client["enable"] = True
        settings = json.dumps({"clients": [client]})
        return await self._req("POST", f"/inbounds/updateClient/{target_uuid}",
                               {"id": ib.get("id"), "settings": settings})

    async def delete_client(self, target_uuid: str):
        client, ib = await self._find_client(target_uuid)
        if not client:
            return False, "کلاینت یافت نشد"
        return await self._req("POST", f"/inbounds/{ib.get('id')}/delClient/{target_uuid}")

    async def get_client_traffic(self, target_uuid: str):
        ok, ibs = await self.get_inbounds()
        if not ok or not isinstance(ibs, list):
            return None
        for ib in ibs:
            try:
                s = ib.get("settings", "{}")
                settings = json.loads(s) if isinstance(s, str) else s
                for c in settings.get("clients", []):
                    if c.get("id") == target_uuid:
                        for st in ib.get("clientStats", []):
                            if st.get("email") == c.get("email"):
                                return {
                                    "up": st.get("up", 0), "down": st.get("down", 0),
                                    "total": c.get("totalGB", 0),
                                    "enable": c.get("enable", True),
                                    "expiry": c.get("expiryTime", 0),
                                    "last_online": st.get("lastOnlineTime", 0)
                                }
            except Exception:
                pass
        return None

    async def list_clients(self):
        ok, ibs = await self.get_inbounds()
        if not ok or not isinstance(ibs, list):
            return []
        clients = []
        for ib in ibs:
            try:
                s = ib.get("settings", "{}")
                settings = json.loads(s) if isinstance(s, str) else s
                for c in settings.get("clients", []):
                    c["_inbound_id"] = ib.get("id")
                    c["_inbound_remark"] = ib.get("remark", "")
                    clients.append(c)
            except Exception:
                pass
        return clients

    async def restart(self):
        return await self._req("POST", "/server/restartXrayService")


class MarzbanApi:
    def __init__(self, panel: dict):
        self.panel = panel
        self.base = panel["url"].rstrip("/")
        self._token = None
        self._token_exp = 0

    async def _login(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{self.base}/api/admin/token",
                    data={"username": self.panel["username"], "password": self.panel["password"],
                          "grant_type": "password"},
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as r:
                    data = await r.json(content_type=None)
                    if "access_token" in data:
                        self._token = data["access_token"]
                        self._token_exp = time.time() + 3500
                        return True
        except Exception as e:
            logger.error(f"Marzban login: {e}")
        return False

    async def _req(self, method: str, endpoint: str, json_data=None, retry: bool = True):
        if not self._token or time.time() > self._token_exp:
            if not await self._login():
                return False, "خطا در ورود به مرزبان"
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as s:
                kw = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=15)}
                if json_data is not None:
                    kw["json"] = json_data
                async with s.request(method, f"{self.base}/api{endpoint}", **kw) as r:
                    if r.status == 401 and retry:
                        self._token = None
                        return await self._req(method, endpoint, json_data, False)
                    data = await r.json(content_type=None)
                    if r.status in (200, 201):
                        return True, data
                    return False, data.get("detail", "خطا")
        except Exception as e:
            return False, str(e)

    async def add_user(self, username: str, gb: float, days: int):
        payload = {
            "username": username,
            "proxies": {"vless": {}, "vmess": {}},
            "inbounds": {"vless": ["VLESS TCP REALITY"], "vmess": ["VMess TCP"]},
            "expire": int(time.time() + days * 86400) if days > 0 else None,
            "data_limit": int(gb * 1024 ** 3) if gb > 0 else None,
            "data_limit_reset_strategy": "no_reset",
            "status": "active", "note": ""
        }
        ok, data = await self._req("POST", "/user", payload)
        if ok:
            return True, {"uuid": data.get("username"), "sub_link": data.get("subscription_url", "")}
        return False, data

    async def get_users(self):
        ok, data = await self._req("GET", "/users")
        if ok:
            return data.get("users", [])
        return []

    async def delete_user(self, username: str):
        return await self._req("DELETE", f"/user/{username}")

    async def renew_user(self, username: str, extra_gb: float = 0, extra_days: int = 0):
        ok, u = await self._req("GET", f"/user/{username}")
        if not ok:
            return False, u
        exp = u.get("expire")
        if exp is None:
            base = int(time.time())
        else:
            base = max(int(exp), int(time.time()))
        new_exp = int(base + extra_days * 86400) if extra_days > 0 else base
        cur_dl = u.get("data_limit") or 0
        add_b = int(extra_gb * (1024 ** 3)) if extra_gb > 0 else 0
        new_dl = cur_dl + add_b if add_b else cur_dl
        payload = {"status": "active", "data_limit": new_dl if new_dl > 0 else None}
        if extra_days > 0:
            payload["expire"] = new_exp
        elif u.get("expire") is not None:
            payload["expire"] = u.get("expire")
        return await self._req("PUT", f"/user/{username}", payload)

    async def restart(self):
        return await self._req("POST", "/restart")


async def get_api(panel: dict):
    if panel["type"] == "xui":
        return XUIApi(panel)
    if panel["type"] == "marzban":
        return MarzbanApi(panel)
    raise ValueError(f"Unknown panel type: {panel['type']}")
