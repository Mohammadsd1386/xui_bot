import aiohttp
import json
import uuid
import time
import logging
from urllib.parse import urlencode
from config import Config

logger = logging.getLogger(__name__)


class XUIApi:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.PANEL_URL.rstrip("/") + config.PANEL_PATH
        self.session_cookie = None

    async def _login(self) -> bool:
        url = f"{self.base_url}/login"
        payload = {
            "username": self.config.PANEL_USER,
            "password": self.config.PANEL_PASS
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            cookies = resp.cookies
                            self.session_cookie = {
                                k: v.value for k, v in cookies.items()
                            }
                            logger.info("✅ Login successful")
                            return True
                    logger.error(f"Login failed: {await resp.text()}")
                    return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    async def _request(self, method: str, endpoint: str, data: dict = None, retry: bool = True):
        if not self.session_cookie:
            ok = await self._login()
            if not ok:
                return False, "خطا در ورود به پنل"

        url = f"{self.base_url}/panel/api{endpoint}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            async with aiohttp.ClientSession(cookies=self.session_cookie) as session:
                kwargs = {
                    "headers": headers,
                    "timeout": aiohttp.ClientTimeout(total=15)
                }
                if data:
                    kwargs["data"] = urlencode(data)

                async with session.request(method, url, **kwargs) as resp:
                    if resp.status == 401 and retry:
                        self.session_cookie = None
                        return await self._request(method, endpoint, data, retry=False)

                    text = await resp.text()
                    try:
                        result = json.loads(text)
                    except Exception:
                        result = {"success": resp.status == 200, "msg": text}

                    if result.get("success"):
                        return True, result.get("obj", result)
                    else:
                        return False, result.get("msg", "خطای ناشناخته")

        except aiohttp.ClientConnectorError:
            return False, "اتصال به پنل برقرار نشد"
        except Exception as e:
            logger.error(f"Request error: {e}")
            return False, str(e)

    # ─────────────────────────────────────────────
    # INBOUNDS
    # ─────────────────────────────────────────────
    async def get_inbounds(self):
        return await self._request("GET", "/inbounds/list")

    async def get_status(self):
        ok, data = await self._request("GET", "/inbounds/list")
        if ok:
            return True, data
        return False, data

    # ─────────────────────────────────────────────
    # CLIENTS
    # ─────────────────────────────────────────────
    def extract_all_clients(self, inbounds_data) -> list:
        clients = []
        if not isinstance(inbounds_data, list):
            return clients
        for inbound in inbounds_data:
            settings_raw = inbound.get("settings", "{}")
            try:
                settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
                for c in settings.get("clients", []):
                    c["_inbound_id"] = inbound.get("id")
                    clients.append(c)
            except Exception:
                pass
        return clients

    def find_client_by_uuid(self, inbounds_data, target_uuid: str) -> tuple:
        if not isinstance(inbounds_data, list):
            return None, None
        for inbound in inbounds_data:
            settings_raw = inbound.get("settings", "{}")
            try:
                settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
                for c in settings.get("clients", []):
                    if c.get("id") == target_uuid:
                        return c, inbound
            except Exception:
                pass
        return None, None

    def _make_sub_id(self) -> str:
        import random, string
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))

    async def add_client(self, email: str, gb: float, days: int) -> tuple:
        client_uuid = str(uuid.uuid4())
        total_bytes = int(gb * 1024 ** 3)
        expiry = 0
        if days > 0:
            expiry = int((time.time() + days * 86400) * 1000)

        client = {
            "id": client_uuid,
            "flow": "",
            "email": email,
            "limitIp": 0,
            "totalGB": total_bytes,
            "expiryTime": expiry,
            "enable": True,
            "tgId": "",
            "subId": self._make_sub_id(),
            "comment": "",
            "reset": 0
        }

        settings = json.dumps({"clients": [client]})
        data = {
            "id": self.config.INBOUND_ID,
            "settings": settings
        }

        ok, result = await self._request("POST", "/inbounds/addClient", data)
        if ok:
            return True, client_uuid
        return False, result

    async def update_client_field(self, target_uuid: str, field: str, value) -> tuple:
        ok, inbounds = await self.get_inbounds()
        if not ok:
            return False, inbounds

        client, inbound = self.find_client_by_uuid(inbounds, target_uuid)
        if not client:
            return False, "کلاینت یافت نشد"

        if field == "gb":
            client["totalGB"] = int(float(value) * 1024 ** 3)
        elif field == "days":
            if int(value) == 0:
                client["expiryTime"] = 0
            else:
                client["expiryTime"] = int((time.time() + int(value) * 86400) * 1000)

        settings = json.dumps({"clients": [client]})
        data = {
            "id": inbound.get("id", self.config.INBOUND_ID),
            "settings": settings
        }
        return await self._request("POST", f"/inbounds/updateClient/{target_uuid}", data)

    async def toggle_client(self, target_uuid: str, enable: bool) -> tuple:
        ok, inbounds = await self.get_inbounds()
        if not ok:
            return False, inbounds

        client, inbound = self.find_client_by_uuid(inbounds, target_uuid)
        if not client:
            return False, "کلاینت یافت نشد"

        client["enable"] = enable
        settings = json.dumps({"clients": [client]})
        data = {
            "id": inbound.get("id", self.config.INBOUND_ID),
            "settings": settings
        }
        return await self._request("POST", f"/inbounds/updateClient/{target_uuid}", data)

    async def delete_client(self, target_uuid: str) -> tuple:
        ok, inbounds = await self.get_inbounds()
        if not ok:
            return False, inbounds

        _, inbound = self.find_client_by_uuid(inbounds, target_uuid)
        if not inbound:
            return False, "کلاینت یافت نشد"

        inbound_id = inbound.get("id", self.config.INBOUND_ID)
        return await self._request("POST", f"/inbounds/{inbound_id}/delClient/{target_uuid}")

    async def restart_panel(self) -> tuple:
        return await self._request("POST", "/server/restartXrayService")
