import time
from database import get_db, get_setting
from services.user_service import get_user

def create_order(user_id, plan_id, panel_id, gb, days, price_rial, currency):
    with get_db() as db:
        cur = db.execute("INSERT INTO orders(user_id,plan_id,panel_id,gb,days,price_paid,currency,status) VALUES(?,?,?,?,?,?,?,'pending')",
                         (user_id, plan_id, panel_id, gb, days, price_rial, currency))
        return cur.lastrowid

def activate_order(order_id, client_uuid, client_email, sub_link):
    with get_db() as db:
        order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order: return False
        expires_at = int(time.time() + dict(order)["days"] * 86400) if dict(order)["days"] > 0 else 0
        db.execute("UPDATE orders SET status='active',client_uuid=?,client_email=?,sub_link=?,expires_at=? WHERE id=?",
                   (client_uuid, client_email, sub_link, expires_at, order_id))
        return True

def get_order(order_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

def create_payment(user_id, order_id, amount_rial, currency, gateway):
    amount_crypto = 0.0
    if gateway not in ("zarinpal","balance"):
        usd_rate = int(get_setting("usd_to_rial","650000"))
        amount_crypto = round(amount_rial / usd_rate, 4)
    with get_db() as db:
        cur = db.execute("INSERT INTO payments(user_id,order_id,amount_rial,amount_crypto,currency,gateway) VALUES(?,?,?,?,?,?)",
                         (user_id, order_id, amount_rial, amount_crypto, currency, gateway))
        return cur.lastrowid

def pay_with_balance(user_id, order_id, amount_rial):
    user = get_user(user_id)
    if not user or user["balance_rial"] < amount_rial: return False
    with get_db() as db:
        db.execute("UPDATE users SET balance_rial=balance_rial-? WHERE telegram_id=?", (amount_rial, user_id))
    return True

def get_sales_stats():
    with get_db() as db:
        total = db.execute("SELECT SUM(amount_rial) as total,COUNT(*) as cnt FROM payments WHERE status='confirmed'").fetchone()
        by_gw = db.execute("SELECT gateway,SUM(amount_rial) as total,COUNT(*) as cnt FROM payments WHERE status='confirmed' GROUP BY gateway ORDER BY total DESC").fetchall()
        today = int(time.time()) - 86400
        month = int(time.time()) - 86400*30
        today_s = db.execute("SELECT SUM(amount_rial) as total FROM payments WHERE status='confirmed' AND created_at>?", (today,)).fetchone()
        month_s = db.execute("SELECT SUM(amount_rial) as total FROM payments WHERE status='confirmed' AND created_at>?", (month,)).fetchone()
        return {"total_rial": total["total"] or 0, "total_count": total["cnt"] or 0,
                "today_rial": today_s["total"] or 0, "month_rial": month_s["total"] or 0,
                "by_gateway": [dict(r) for r in by_gw]}

def get_pending_payments():
    with get_db() as db:
        rows = db.execute("""SELECT p.*,u.username,u.full_name FROM payments p
            JOIN users u ON p.user_id=u.telegram_id
            WHERE p.status='pending' AND p.gateway != 'zarinpal'
            ORDER BY p.created_at DESC""").fetchall()
        return [dict(r) for r in rows]
