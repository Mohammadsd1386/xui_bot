"""
License verification — tied to hardware fingerprint.
"""
import hashlib
import hmac as _hmac
import json
import platform
import socket
import time
import uuid
from pathlib import Path

# !! Change this secret before distributing !!
_MASTER_SECRET = "V9pN2xQkL8mJtR5wYbGcFdAeUoIhZs3X_CHANGE_ME"

LICENSE_FILE = Path(__file__).parent / ".license"


def _get_hw_id() -> str:
    parts = []
    mac = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff)
                    for i in range(0, 48, 8)][::-1])
    parts.append(mac)
    try:
        parts.append(socket.gethostname())
    except Exception:
        pass
    parts.append(platform.system())
    parts.append(platform.machine())
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "Serial" in line or "Hardware" in line:
                    parts.append(line.strip())
                    break
    except Exception:
        pass
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def get_hw_id() -> str:
    return _get_hw_id()


def generate_license(hardware_id: str, expiry_days: int = 0, customer_name: str = "") -> str:
    expiry_ts = int(time.time() + expiry_days * 86400) if expiry_days > 0 else 0
    payload = json.dumps({
        "hw": hardware_id,
        "exp": expiry_ts,
        "name": customer_name,
        "issued": int(time.time())
    }, separators=(',', ':'))
    payload_hex = payload.encode().hex()
    sig = _hmac.new(_MASTER_SECRET.encode(), payload_hex.encode(), hashlib.sha256).hexdigest()
    return f"{payload_hex}.{sig}"


def verify_license(license_key: str) -> tuple:
    if not license_key or '.' not in license_key:
        return False, "فرمت لایسنس نامعتبر"
    try:
        payload_hex, sig = license_key.rsplit('.', 1)
    except ValueError:
        return False, "فرمت لایسنس نامعتبر"

    expected = _hmac.new(_MASTER_SECRET.encode(), payload_hex.encode(), hashlib.sha256).hexdigest()
    if not _hmac.compare_digest(sig, expected):
        return False, "لایسنس جعلی یا دستکاری‌شده"

    try:
        payload = json.loads(bytes.fromhex(payload_hex).decode())
    except Exception:
        return False, "خطا در خواندن لایسنس"

    current_hw = _get_hw_id()
    if payload.get("hw") != current_hw:
        return False, (f"لایسنس برای سرور دیگری صادر شده\n"
                       f"HW ID این سرور: {current_hw}")

    exp = payload.get("exp", 0)
    if exp > 0 and time.time() > exp:
        from datetime import datetime
        return False, f"لایسنس منقضی شده ({datetime.fromtimestamp(exp).strftime('%Y/%m/%d')})"

    return True, payload


def load_and_verify() -> tuple:
    if not LICENSE_FILE.exists():
        hw = _get_hw_id()
        return False, (
            f"فایل لایسنس (.license) یافت نشد!\n\n"
            f"HW ID این سرور:\n{hw}\n\n"
            f"این کد را برای دریافت لایسنس ارسال کنید."
        )
    key = LICENSE_FILE.read_text().strip()
    return verify_license(key)
