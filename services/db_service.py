"""All database operations — single source of truth."""
import time
from database import get_db, get_setting


# ── USERS ─────────────────────────────────────────────────────────────────────

def upsert_user(tg_id: int, username: str = None, full_name: str = None, referrer_id: int = None) -> dict:
    with get_db() as db:
        existing = db.execute("SELECT * FROM users WHERE telegram_id=?", (tg_id,)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO users(telegram_id,username,full_name,referrer_id) VALUES(?,?,?,?)",
                (tg_id, username, full_name, referrer_id)
            )
            if referrer_id and referrer_id != tg_id:
                db.execute(
                    "INSERT OR IGNORE INTO referrals(referrer_id,referred_id) VALUES(?,?)",
                    (referrer_id, tg_id)
                )
        else:
            db.execute(
                "UPDATE users SET username=?, full_name=? WHERE telegram_id=?",
                (username, full_name, tg_id)
            )
        return dict(db.execute("SELECT * FROM users WHERE telegram_id=?", (tg_id,)).fetchone())


def get_user(tg_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE telegram_id=?", (tg_id,)).fetchone()
        return dict(row) if row else None


def is_admin(tg_id: int) -> bool:
    from database import get_setting
    owner = get_setting("owner_id", "")
    if owner and str(tg_id) == str(owner):
        return True
    with get_db() as db:
        return db.execute("SELECT 1 FROM admins WHERE telegram_id=?", (tg_id,)).fetchone() is not None


def get_admin_ids() -> list:
    ids = []
    owner = get_setting("owner_id", "")
    if owner:
        try:
            ids.append(int(owner))
        except ValueError:
            pass
    with get_db() as db:
        rows = db.execute("SELECT telegram_id FROM admins").fetchall()
        ids += [r["telegram_id"] for r in rows]
    return list(set(ids))


def get_users_page(limit: int = 20, offset: int = 0) -> list:
    with get_db() as db:
        rows = db.execute(
            "SELECT u.*, (SELECT COUNT(*) FROM orders WHERE user_id=u.telegram_id) as order_count "
            "FROM users u ORDER BY u.created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


def count_users() -> int:
    with get_db() as db:
        return db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]


def set_discount(tg_id: int, pct: int):
    with get_db() as db:
        db.execute("UPDATE users SET discount_pct=? WHERE telegram_id=?", (pct, tg_id))


def add_balance(tg_id: int, amount: int):
    with get_db() as db:
        db.execute("UPDATE users SET balance_rial=balance_rial+? WHERE telegram_id=?", (amount, tg_id))


def ban_user(tg_id: int, banned: bool):
    with get_db() as db:
        db.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (1 if banned else 0, tg_id))


def mark_free_test_used(tg_id: int):
    with get_db() as db:
        db.execute("UPDATE users SET free_test_used=1 WHERE telegram_id=?", (tg_id,))


# ── PANELS ────────────────────────────────────────────────────────────────────

def get_panels(active_only: bool = False) -> list:
    with get_db() as db:
        q = "SELECT * FROM panels" + (" WHERE is_active=1" if active_only else "") + " ORDER BY id"
        return [dict(r) for r in db.execute(q).fetchall()]


def get_panel(panel_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM panels WHERE id=?", (panel_id,)).fetchone()
        return dict(row) if row else None


def add_panel(name, ptype, url, path, username, password, inbound_id) -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO panels(name,type,url,path,username,password,inbound_id) VALUES(?,?,?,?,?,?,?)",
            (name, ptype, url, path, username, password, inbound_id)
        )
        return cur.lastrowid


def delete_panel(panel_id: int):
    with get_db() as db:
        used_plan = db.execute("SELECT COUNT(*) as c FROM plans WHERE panel_id=?", (panel_id,)).fetchone()["c"]
        used_order = db.execute("SELECT COUNT(*) as c FROM orders WHERE panel_id=?", (panel_id,)).fetchone()["c"]
        if used_plan > 0 or used_order > 0:
            raise ValueError("این پنل در پلن‌ها/سفارش‌ها استفاده شده و قابل حذف نیست.")
        db.execute("DELETE FROM panels WHERE id=?", (panel_id,))


def toggle_panel(panel_id: int):
    with get_db() as db:
        db.execute("UPDATE panels SET is_active = 1 - is_active WHERE id=?", (panel_id,))


# ── PLANS ─────────────────────────────────────────────────────────────────────

def get_plans(active_only: bool = False) -> list:
    with get_db() as db:
        q = """SELECT p.*, pn.name as panel_name, pn.type as panel_type
               FROM plans p LEFT JOIN panels pn ON p.panel_id=pn.id"""
        if active_only:
            q += " WHERE p.is_active=1"
        q += " ORDER BY p.price_rial"
        return [dict(r) for r in db.execute(q).fetchall()]


def get_plan(plan_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT p.*, pn.name as panel_name FROM plans p "
            "LEFT JOIN panels pn ON p.panel_id=pn.id WHERE p.id=?",
            (plan_id,)
        ).fetchone()
        return dict(row) if row else None


def add_plan(name, gb, days, price_rial, panel_id) -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO plans(name,gb,days,price_rial,panel_id) VALUES(?,?,?,?,?)",
            (name, gb, days, price_rial, panel_id)
        )
        return cur.lastrowid


def toggle_plan(plan_id: int):
    with get_db() as db:
        db.execute("UPDATE plans SET is_active = 1 - is_active WHERE id=?", (plan_id,))


def delete_plan(plan_id: int):
    with get_db() as db:
        db.execute("DELETE FROM plans WHERE id=?", (plan_id,))


def update_plan_field(plan_id: int, field: str, value):
    allowed = {"name", "gb", "days", "price_rial"}
    if field not in allowed:
        return
    with get_db() as db:
        db.execute(f"UPDATE plans SET {field}=? WHERE id=?", (value, plan_id))


# ── ORDERS ────────────────────────────────────────────────────────────────────

def create_order(
    user_id,
    plan_id,
    panel_id,
    gb,
    days,
    price_rial,
    currency="rial",
    config_name: str = None,
    extends_order_id: int | None = None,
) -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO orders(user_id,plan_id,panel_id,gb,days,price_paid,currency,status,config_name,extends_order_id) "
            "VALUES(?,?,?,?,?,?,'rial','pending',?,?)",
            (user_id, plan_id, panel_id, gb, days, price_rial, config_name, extends_order_id),
        )
        return cur.lastrowid


def activate_order(order_id: int, client_uuid: str, client_email: str, sub_link: str):
    with get_db() as db:
        o = db.execute("SELECT days FROM orders WHERE id=?", (order_id,)).fetchone()
        if not o:
            return
        days = dict(o)["days"] or 0
        expires = int(time.time() + days * 86400) if days > 0 else 0
        db.execute(
            "UPDATE orders SET status='active',client_uuid=?,client_email=?,sub_link=?,expires_at=? WHERE id=?",
            (client_uuid, client_email, sub_link, expires, order_id)
        )


def get_user_orders(user_id: int) -> list:
    with get_db() as db:
        rows = db.execute(
            "SELECT o.*, p.name as plan_name, pn.name as panel_name "
            "FROM orders o LEFT JOIN plans p ON o.plan_id=p.id "
            "LEFT JOIN panels pn ON o.panel_id=pn.id "
            "WHERE o.user_id=? AND o.extends_order_id IS NULL "
            "ORDER BY o.created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_user_orders_admin(user_id: int, limit: int = 25) -> list:
    """همه سفارش‌ها شامل تمدیدهای داخلی — فقط برای ادمین."""
    with get_db() as db:
        rows = db.execute(
            "SELECT o.*, p.name as plan_name FROM orders o "
            "LEFT JOIN plans p ON o.plan_id=p.id "
            "WHERE o.user_id=? ORDER BY o.created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_order(order_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None


# ── PAYMENTS ──────────────────────────────────────────────────────────────────

def create_payment(user_id: int, order_id: int, amount_rial: int, gateway: str) -> int:
    usd_rate = int(get_setting("usdt_to_rial") or get_setting("usd_to_rial", "650000"))
    amount_crypto = round(amount_rial / usd_rate, 4) if gateway not in ("zarinpal", "balance", "card2card") else 0.0
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO payments(user_id,order_id,amount_rial,amount_crypto,gateway) VALUES(?,?,?,?,?)",
            (user_id, order_id, amount_rial, amount_crypto, gateway)
        )
        return cur.lastrowid


def confirm_payment(payment_id: int, tx_hash: str = None):
    with get_db() as db:
        p = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not p:
            return False
        p = dict(p)
        db.execute(
            "UPDATE payments SET status='confirmed', tx_hash=?, confirmed_at=strftime('%s','now') WHERE id=?",
            (tx_hash, payment_id)
        )
        is_extension = False
        if p.get("order_id"):
            orow = db.execute(
                "SELECT extends_order_id FROM orders WHERE id=?", (p["order_id"],)
            ).fetchone()
            ext_parent = dict(orow).get("extends_order_id") if orow else None
            if ext_parent:
                is_extension = True
                db.execute("UPDATE orders SET status='merged' WHERE id=?", (p["order_id"],))
            else:
                db.execute("UPDATE orders SET status='active' WHERE id=?", (p["order_id"],))
        # Referral reward on first purchase (نه برای پرداخت تمدید/افزایش حجم)
        ref = db.execute(
            "SELECT * FROM referrals WHERE referred_id=? AND reward_rial=0", (p["user_id"],)
        ).fetchone()
        if ref and not is_extension:
            reward = int(get_setting("referral_reward_rial", "50000"))
            db.execute("UPDATE users SET balance_rial=balance_rial+? WHERE telegram_id=?",
                       (reward, dict(ref)["referrer_id"]))
            db.execute("UPDATE referrals SET reward_rial=? WHERE id=?", (reward, dict(ref)["id"]))
    return True


def reject_payment(payment_id: int):
    with get_db() as db:
        p = db.execute("SELECT order_id FROM payments WHERE id=?", (payment_id,)).fetchone()
        db.execute("UPDATE payments SET status='failed' WHERE id=?", (payment_id,))
        if p and dict(p)["order_id"]:
            db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (dict(p)["order_id"],))


def get_payment(payment_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        return dict(row) if row else None


def get_pending_crypto_payments() -> list:
    with get_db() as db:
        rows = db.execute(
            "SELECT p.*, u.username, u.full_name FROM payments p "
            "JOIN users u ON p.user_id=u.telegram_id "
            "WHERE p.status='pending' AND p.gateway NOT IN ('zarinpal','balance') "
            "ORDER BY p.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def pay_from_balance(user_id: int, amount: int) -> bool:
    with get_db() as db:
        u = db.execute("SELECT balance_rial FROM users WHERE telegram_id=?", (user_id,)).fetchone()
        if not u or dict(u)["balance_rial"] < amount:
            return False
        db.execute("UPDATE users SET balance_rial=balance_rial-? WHERE telegram_id=?", (amount, user_id))
    return True


def get_sales_stats() -> dict:
    with get_db() as db:
        total = db.execute(
            "SELECT SUM(amount_rial) as t, COUNT(*) as c FROM payments WHERE status='confirmed'"
        ).fetchone()
        today_ts = int(time.time()) - 86400
        month_ts = int(time.time()) - 86400 * 30
        today = db.execute(
            "SELECT SUM(amount_rial) as t FROM payments WHERE status='confirmed' AND created_at>?",
            (today_ts,)
        ).fetchone()
        month = db.execute(
            "SELECT SUM(amount_rial) as t FROM payments WHERE status='confirmed' AND created_at>?",
            (month_ts,)
        ).fetchone()
        gateways = db.execute(
            "SELECT gateway, SUM(amount_rial) as t, COUNT(*) as c "
            "FROM payments WHERE status='confirmed' GROUP BY gateway ORDER BY t DESC"
        ).fetchall()
        return {
            "total_rial": total["t"] or 0,
            "total_count": total["c"] or 0,
            "today_rial": today["t"] or 0,
            "month_rial": month["t"] or 0,
            "by_gateway": [dict(r) for r in gateways]
        }


def get_user_financial_stats(user_id: int) -> dict:
    with get_db() as db:
        bought = db.execute(
            "SELECT COUNT(*) as c, SUM(price_paid) as s, SUM(gb) as g FROM orders "
            "WHERE user_id=? AND status!='cancelled'",
            (user_id,)
        ).fetchone()
        paid = db.execute(
            "SELECT SUM(amount_rial) as s FROM payments WHERE user_id=? AND status='confirmed'",
            (user_id,)
        ).fetchone()
        dep = db.execute(
            "SELECT SUM(amount_rial) as s FROM wallet_requests WHERE user_id=? AND type='deposit' AND status='approved'",
            (user_id,)
        ).fetchone()
        wd = db.execute(
            "SELECT SUM(amount_rial) as s FROM wallet_requests WHERE user_id=? AND type='withdraw' AND status='approved'",
            (user_id,)
        ).fetchone()
    return {
        "orders_count": bought["c"] or 0,
        "total_buy_rial": bought["s"] or 0,
        "total_gb": bought["g"] or 0,
        "total_paid_rial": paid["s"] or 0,
        "wallet_deposit_rial": dep["s"] or 0,
        "wallet_withdraw_rial": wd["s"] or 0,
    }


def create_wallet_request(user_id: int, req_type: str, amount_rial: int, note: str = "") -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO wallet_requests(user_id,type,amount_rial,note) VALUES(?,?,?,?)",
            (user_id, req_type, amount_rial, note)
        )
        return cur.lastrowid


def get_pending_wallet_requests() -> list:
    with get_db() as db:
        rows = db.execute(
            "SELECT wr.*, u.username, u.full_name FROM wallet_requests wr "
            "JOIN users u ON u.telegram_id=wr.user_id "
            "WHERE wr.status='pending' ORDER BY wr.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def approve_wallet_request(req_id: int, admin_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM wallet_requests WHERE id=? AND status='pending'", (req_id,)).fetchone()
        if not row:
            return None
        req = dict(row)
        if req["type"] == "deposit":
            db.execute(
                "UPDATE users SET balance_rial=balance_rial+? WHERE telegram_id=?",
                (req["amount_rial"], req["user_id"])
            )
        else:
            u = db.execute("SELECT balance_rial FROM users WHERE telegram_id=?", (req["user_id"],)).fetchone()
            if not u or u["balance_rial"] < req["amount_rial"]:
                return {"error": "موجودی کاربر برای برداشت کافی نیست."}
            db.execute(
                "UPDATE users SET balance_rial=balance_rial-? WHERE telegram_id=?",
                (req["amount_rial"], req["user_id"])
            )
        db.execute(
            "UPDATE wallet_requests SET status='approved', handled_at=strftime('%s','now'), handled_by=? WHERE id=?",
            (admin_id, req_id)
        )
        return req


def reject_wallet_request(req_id: int, admin_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM wallet_requests WHERE id=? AND status='pending'", (req_id,)).fetchone()
        if not row:
            return None
        req = dict(row)
        db.execute(
            "UPDATE wallet_requests SET status='rejected', handled_at=strftime('%s','now'), handled_by=? WHERE id=?",
            (admin_id, req_id)
        )
        return req


# ── ADMINS ────────────────────────────────────────────────────────────────────

def get_admins() -> list:
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM admins ORDER BY created_at").fetchall()]


def add_admin(tg_id: int, added_by: int, username: str = None, full_name: str = None):
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO admins(telegram_id,username,full_name,added_by) VALUES(?,?,?,?)",
            (tg_id, username, full_name, added_by)
        )


def delete_admin(tg_id: int):
    with get_db() as db:
        db.execute("DELETE FROM admins WHERE telegram_id=?", (tg_id,))


# ── TICKETS ───────────────────────────────────────────────────────────────────

def create_ticket(user_id: int, subject: str) -> int:
    with get_db() as db:
        cur = db.execute("INSERT INTO tickets(user_id,subject) VALUES(?,?)", (user_id, subject))
        return cur.lastrowid


def add_ticket_message(ticket_id: int, sender_id: int, message: str, is_admin: bool = False):
    with get_db() as db:
        db.execute(
            "INSERT INTO ticket_messages(ticket_id,sender_id,is_admin,message) VALUES(?,?,?,?)",
            (ticket_id, sender_id, 1 if is_admin else 0, message)
        )
        if is_admin:
            db.execute("UPDATE tickets SET status='answered' WHERE id=?", (ticket_id,))


def get_user_tickets(user_id: int) -> list:
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM tickets WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        ).fetchall()]


def get_ticket(ticket_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None


def get_ticket_messages(ticket_id: int) -> list:
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM ticket_messages WHERE ticket_id=? ORDER BY created_at",
            (ticket_id,)
        ).fetchall()]


# ── MISC ──────────────────────────────────────────────────────────────────────

def search_user_by_id(tg_id: int) -> dict | None:
    return get_user(tg_id)


def get_all_user_ids() -> list:
    with get_db() as db:
        rows = db.execute("SELECT telegram_id FROM users WHERE is_banned=0").fetchall()
        return [r["telegram_id"] for r in rows]
