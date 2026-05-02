#!/usr/bin/env python3
"""ابزار صدور و بررسی لایسنس — فقط برای شما"""
import sys, argparse
from license import generate_license, verify_license, get_hw_id


def main():
    p = argparse.ArgumentParser(description="VPN Bot License Manager")
    sub = p.add_subparsers(dest="cmd")

    g = sub.add_parser("gen", help="صدور لایسنس جدید")
    g.add_argument("hw_id")
    g.add_argument("--days", type=int, default=0)
    g.add_argument("--name", default="")

    v = sub.add_parser("verify", help="بررسی لایسنس")
    v.add_argument("key")

    sub.add_parser("hwid", help="HW ID این سرور")

    args = p.parse_args()

    if args.cmd == "gen":
        key = generate_license(args.hw_id, args.days, args.name)
        print(f"\n{'='*60}")
        print(f"✅ لایسنس صادر شد — {args.name or '—'}")
        print(f"HW: {args.hw_id}")
        print(f"اعتبار: {'مادام‌العمر' if args.days == 0 else str(args.days) + ' روز'}")
        print(f"{'='*60}")
        print(f"\n{key}\n")
        print(f"نصب روی سرور مشتری:")
        print(f"  echo '{key}' > .license\n")

    elif args.cmd == "verify":
        ok, info = verify_license(args.key)
        if ok:
            from datetime import datetime
            exp = info.get("exp", 0)
            print(f"\n✅ معتبر | {info.get('name','—')} | انقضا: {'مادام‌العمر' if exp==0 else datetime.fromtimestamp(exp).strftime('%Y/%m/%d')}\n")
        else:
            print(f"\n❌ {info}\n")

    elif args.cmd == "hwid":
        print(f"\nHW ID: {get_hw_id()}\n")

    else:
        p.print_help()


if __name__ == "__main__":
    main()
