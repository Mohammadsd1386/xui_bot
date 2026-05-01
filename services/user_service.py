from database import get_db, get_setting

def get_or_create_user(telegram_id, username=None, full_name=None, referrer_id=None):
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if not user:
            db.execute("INSERT INTO users(telegram_id,username,full_name,referrer_id) VALUES(?,?,?,?)",
                       (telegram_id, username, full_name, referrer_id))
            if referrer_id and referrer_id != telegram_id:
                db.execute("INSERT OR IGNORE INTO referrals(referrer_id,referred_id) VALUES(?,?)",
                           (referrer_id, telegram_id))
        else:
            db.execute("UPDATE users SET username=?,full_name=? WHERE telegram_id=?",
                       (username, full_name, telegram_id))
        return dict(db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone())

def get_user(telegram_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row) if row else None

def is_admin(telegram_id, owner_id=None):
    if owner_id and telegram_id == int(owner_id): return True
    with get_db() as db:
        return db.execute("SELECT 1 FROM admins WHERE telegram_id=?", (telegram_id,)).fetchone() is not None

def get_user_orders(user_id):
    with get_db() as db:
        rows = db.execute("""SELECT o.*,p.name as plan_name,pn.name as panel_name,pn.type as panel_type
            FROM orders o LEFT JOIN plans p ON o.plan_id=p.id
            LEFT JOIN panels pn ON o.panel_id=pn.id
            WHERE o.user_id=? ORDER BY o.created_at DESC""", (user_id,)).fetchall()
        return [dict(r) for r in rows]

def get_user_stats(user_id):
    with get_db() as db:
        orders = db.execute("SELECT COUNT(*) as cnt,SUM(price_paid) as total FROM orders WHERE user_id=? AND status='active'", (user_id,)).fetchone()
        referrals = db.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id=?", (user_id,)).fetchone()
        return {"active_orders": orders["cnt"] or 0, "total_spent": orders["total"] or 0, "referral_count": referrals["cnt"] or 0}

def set_user_discount(user_id, discount_pct):
    with get_db() as db:
        db.execute("UPDATE users SET discount_pct=? WHERE telegram_id=?", (discount_pct, user_id))

def get_all_users(limit=50, offset=0):
    with get_db() as db:
        rows = db.execute("""SELECT u.*,(SELECT COUNT(*) FROM orders WHERE user_id=u.telegram_id) as order_count
            FROM users u ORDER BY u.created_at DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
        return [dict(r) for r in rows]

def ban_user(user_id, banned=True):
    with get_db() as db:
        db.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (1 if banned else 0, user_id))
