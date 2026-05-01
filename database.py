import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "vpnbot.db"
logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS admins (
            telegram_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            role TEXT DEFAULT 'admin', added_by INTEGER,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS panels (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('xui','marzban')),
            url TEXT NOT NULL, path TEXT DEFAULT '', username TEXT NOT NULL,
            password TEXT NOT NULL, inbound_id INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1, created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            gb REAL NOT NULL, days INTEGER NOT NULL, price_rial INTEGER DEFAULT 0,
            price_usdt REAL DEFAULT 0, is_active INTEGER DEFAULT 1,
            panel_id INTEGER REFERENCES panels(id),
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, phone TEXT,
            referrer_id INTEGER REFERENCES users(telegram_id),
            balance_rial INTEGER DEFAULT 0, discount_pct INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0, free_test_used INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            plan_id INTEGER REFERENCES plans(id), panel_id INTEGER REFERENCES panels(id),
            client_uuid TEXT, client_email TEXT, sub_link TEXT,
            gb REAL, days INTEGER, price_paid INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'rial',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','active','expired','cancelled')),
            expires_at INTEGER, created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            order_id INTEGER REFERENCES orders(id), amount_rial INTEGER DEFAULT 0,
            amount_crypto REAL DEFAULT 0, currency TEXT,
            gateway TEXT CHECK(gateway IN ('zarinpal','usdt_bep20','tron','ton','balance')),
            tx_hash TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','confirming','confirmed','failed')),
            created_at INTEGER DEFAULT (strftime('%s','now')), confirmed_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL REFERENCES users(telegram_id),
            referred_id INTEGER NOT NULL REFERENCES users(telegram_id),
            reward_rial INTEGER DEFAULT 0, created_at INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE(referred_id)
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            subject TEXT, status TEXT DEFAULT 'open' CHECK(status IN ('open','answered','closed')),
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            sender_id INTEGER NOT NULL, is_admin INTEGER DEFAULT 0, message TEXT NOT NULL,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        INSERT OR IGNORE INTO settings VALUES
            ('bot_token',''),('owner_id',''),('bot_name','ربات فروش VPN'),('bot_username',''),
            ('zarinpal_merchant',''),('usdt_bep20_address',''),('tron_address',''),
            ('ton_address',''),('ton_memo',''),('usd_to_rial','650000'),
            ('ton_price_usd','3.5'),('referral_reward_rial','50000'),
            ('free_test_gb','1'),('free_test_days','3'),('free_test_enabled','0'),
            ('support_username',''),('channel_id',''),('channel_join_required','0'),
            ('bscscan_api_key',''),('min_payment_rial','50000');
        """)
    logger.info("✅ Database initialized")

def get_setting(key: str, default=None):
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
