"""
3x-ui API Client
ارتباط با API پنل
"""

import uuid
import json
import time
import logging
import requests
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)


class XUIClient:
    def __init__(self):
        self.config = Config()
        self.base_url = self.config.PANEL_URL.rstrip("/") + self.config.PANEL_PATH
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        })
        self._logged_in = False

    def _login(self) -> bool:
        """ورود به پنل"""
        try:
            url = f"{self.base_url}/login"
            data = {
                "username": self.config.PANEL_USERNAME,
                "password": self.config.PANEL_PASSWORD,
            }
            resp = self.session.post(url, data=data, timeout=10)
            result = resp.json()
            if result.get("success"):
                self._logged_in = True
                logger.info("✅ Login successful")
                return True
            logger.error(f"❌ Login failed: {result.get('msg')}")
            return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        """ارسال درخواست با لاگین خودکار"""
        if not self._logged_in:
            if not self._login():
                return None
        
        url = f"{self.base_url}/api{endpoint}"
        try:
            resp = self.session.request(method, url, timeout=15, **kwargs)
            
            # اگر session منقضی شده بود
            if resp.status_code == 401 or (resp.headers.get("content-type","").startswith("text/html")):
                self._logged_in = False
                if self._login():
                    resp = self.session.request(method, url, timeout=15, **kwargs)
                else:
                    return None
            
            return resp.json()
        except Exception as e:
            logger.error(f"Request error [{endpoint}]: {e}")
            return None

    # ─────────────── Inbounds ───────────────

    def get_inbounds(self) -> list:
        """لیست همه اینباندها"""
        result = self._request("GET", "/inbounds/list")
        if result and result.get("success"):
            return result.get("obj", [])
        return []

    def get_inbound(self, inbound_id: int) -> Optional[dict]:
        """اطلاعات یک اینباند"""
        result = self._request("GET", f"/inbounds/get/{inbound_id}")
        if result and result.get("success"):
            return result.get("obj")
        return None

    # ─────────────── Clients ───────────────

    def get_clients(self, inbound_id: Optional[int] = None) -> list:
        """لیست کلاینت‌های یک اینباند"""
        iid = inbound_id or self.config.DEFAULT_INBOUND_ID
        inbound = self.get_inbound(iid)
        if not inbound:
            return []
        settings = json.loads(inbound.get("settings", "{}"))
        return settings.get("clients", [])

    def get_client_traffic(self, email: str) -> Optional[dict]:
        """آمار مصرف یک کلاینت"""
        result = self._request("GET", f"/inbounds/getClientTraffics/{email}")
        if result and result.get("success"):
            return result.get("obj")
        return None

    def get_all_traffics(self) -> list:
        """آمار همه کلاینت‌ها"""
        result = self._request("GET", "/inbounds/clientTraffics/all")
        if result and result.get("success"):
            return result.get("obj", [])
        # fallback: از لیست کلاینت‌ها
        clients = self.get_clients()
        traffics = []
        for c in clients:
            t = self.get_client_traffic(c.get("email", ""))
            if t:
                traffics.append(t)
        return traffics

    def add_client(
        self,
        email: str,
        total_gb: float = 10,
        expire_days: int = 30,
        limit_ip: int = 2,
        inbound_id: Optional[int] = None,
    ) -> tuple[bool, str]:
        """اضافه کردن کلاینت جدید"""
        iid = inbound_id or self.config.DEFAULT_INBOUND_ID
        client_id = str(uuid.uuid4())
        sub_id = uuid.uuid4().hex[:16]
        
        expire_ms = 0
        if expire_days > 0:
            expire_ms = int((time.time() + expire_days * 86400) * 1000)
        
        total_bytes = int(total_gb * 1024 ** 3)
        
        client = {
            "id": client_id,
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "tgId": "",
            "subId": sub_id,
            "comment": "",
            "reset": 0,
        }
        
        settings = json.dumps({"clients": [client]}, ensure_ascii=False)
        data = {"id": iid, "settings": settings}
        
        result = self._request("POST", "/inbounds/addClient", data=data)
        if result and result.get("success"):
            return True, client_id
        msg = result.get("msg", "خطای نامشخص") if result else "خطا در اتصال"
        return False, msg

    def update_client(self, client_uuid: str, updates: dict, inbound_id: Optional[int] = None) -> tuple[bool, str]:
        """آپدیت کلاینت"""
        iid = inbound_id or self.config.DEFAULT_INBOUND_ID
        
        # پیدا کردن کلاینت فعلی
        clients = self.get_clients(iid)
        client = next((c for c in clients if c.get("id") == client_uuid), None)
        if not client:
            return False, "کلاینت پیدا نشد"
        
        # اعمال آپدیت‌ها
        client.update(updates)
        
        settings = json.dumps({"clients": [client]}, ensure_ascii=False)
        data = {"id": iid, "settings": settings}
        
        result = self._request("POST", f"/inbounds/updateClient/{client_uuid}", data=data)
        if result and result.get("success"):
            return True, "آپدیت شد"
        msg = result.get("msg", "خطای نامشخص") if result else "خطا در اتصال"
        return False, msg

    def delete_client(self, inbound_id: int, client_uuid: str) -> tuple[bool, str]:
        """حذف کلاینت"""
        result = self._request("POST", f"/inbounds/{inbound_id}/delClient/{client_uuid}")
        if result and result.get("success"):
            return True, "حذف شد"
        msg = result.get("msg", "خطای نامشخص") if result else "خطا در اتصال"
        return False, msg

    def toggle_client(self, client_uuid: str, enable: bool, inbound_id: Optional[int] = None) -> tuple[bool, str]:
        """فعال/غیرفعال کردن کلاینت"""
        return self.update_client(client_uuid, {"enable": enable}, inbound_id)

    def reset_client_traffic(self, inbound_id: int, email: str) -> tuple[bool, str]:
        """ریست ترافیک کلاینت"""
        result = self._request("POST", f"/inbounds/{inbound_id}/resetClientTraffic/{email}")
        if result and result.get("success"):
            return True, "ترافیک ریست شد"
        msg = result.get("msg", "خطای نامشخص") if result else "خطا در اتصال"
        return False, msg

    # ─────────────── Panel ───────────────

    def restart_panel(self) -> tuple[bool, str]:
        """ریستارت پنل"""
        result = self._request("POST", "/server/restartXrayService")
        if result and result.get("success"):
            return True, "پنل ریستارت شد ✅"
        # fallback
        result2 = self._request("POST", "/server/restart")
        if result2 and result2.get("success"):
            return True, "پنل ریستارت شد ✅"
        return False, "خطا در ریستارت"

    def get_server_status(self) -> Optional[dict]:
        """وضعیت سرور"""
        result = self._request("POST", "/server/status")
        if result and result.get("success"):
            return result.get("obj")
        return None

    # ─────────────── Helpers ───────────────

    @staticmethod
    def bytes_to_gb(b: int) -> float:
        return round(b / (1024 ** 3), 2)

    @staticmethod
    def ms_to_date(ms: int) -> str:
        if not ms or ms == 0:
            return "نامحدود"
        import datetime
        dt = datetime.datetime.fromtimestamp(ms / 1000)
        return dt.strftime("%Y-%m-%d")
