import aiosqlite
from datetime import datetime
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,          -- telegram_id
    username TEXT,
    coins INTEGER NOT NULL DEFAULT 0,
    referrer_id INTEGER,
    referral_rewarded INTEGER NOT NULL DEFAULT 0, -- 1 когда за него уже начислили бонус рефереру
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    price_coins INTEGER NOT NULL,
    file_id TEXT,              -- file_id видео в Telegram (если хранится у бота)
    channel_link TEXT,         -- либо ссылка/пост в приватном канале
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    video_id INTEGER NOT NULL,
    purchased_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount_coins INTEGER NOT NULL,   -- положительное = начисление, отрицательное = списание
    type TEXT NOT NULL,              -- topup / referral_bonus / purchase / admin_adjust
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topup_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount_money INTEGER,
    amount_coins INTEGER,
    method TEXT NOT NULL,            -- manual / cryptobot
    purpose TEXT NOT NULL DEFAULT 'coins', -- coins / channel
    status TEXT NOT NULL DEFAULT 'pending', -- pending / confirmed / rejected
    screenshot_file_id TEXT,
    admin_comment TEXT,
    created_at TEXT NOT NULL
);
"""

STARTING_COINS = 10


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
        # миграция для баз, созданных до появления поля purpose
        try:
            await db.execute("ALTER TABLE topup_requests ADD COLUMN purpose TEXT NOT NULL DEFAULT 'coins'")
            await db.commit()
        except aiosqlite.OperationalError:
            pass  # колонка уже есть


def now() -> str:
    return datetime.utcnow().isoformat()


# ---------- Пользователи ----------

async def get_or_create_user(user_id: int, username: str | None, referrer_id: int | None = None) -> bool:
    """Возвращает True, если пользователь был создан только что (первый /start)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        if row is None:
            # не даём указать себя в качестве реферера
            if referrer_id == user_id:
                referrer_id = None
            await db.execute(
                "INSERT INTO users (id, username, coins, referrer_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, STARTING_COINS, referrer_id, now()),
            )
            await db.commit()
            return True
        else:
            # обновляем username на случай если поменялся
            await db.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
            await db.commit()
            return False


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return await cur.fetchone()


async def get_balance(user_id: int) -> int:
    user = await get_user(user_id)
    return user["coins"] if user else 0


async def add_coins(user_id: int, amount: int, tx_type: str, note: str = ""):
    """amount может быть отрицательным (списание)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (amount, user_id))
        await db.execute(
            "INSERT INTO transactions (user_id, amount_coins, type, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, tx_type, note, now()),
        )
        await db.commit()


async def mark_referral_rewarded(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET referral_rewarded = 1 WHERE id = ?", (user_id,))
        await db.commit()


async def count_referrals(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


# ---------- Видео ----------

async def add_video(title: str, description: str, price_coins: int, file_id: str | None, channel_link: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO videos (title, description, price_coins, file_id, channel_link, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, price_coins, file_id, channel_link, now()),
        )
        await db.commit()


async def list_active_videos():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM videos WHERE is_active = 1 ORDER BY id DESC")
        return await cur.fetchall()


async def get_video(video_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
        return await cur.fetchone()


async def has_purchased(user_id: int, video_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM purchases WHERE user_id = ? AND video_id = ?", (user_id, video_id)
        )
        return (await cur.fetchone()) is not None


async def record_purchase(user_id: int, video_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO purchases (user_id, video_id, purchased_at) VALUES (?, ?, ?)",
            (user_id, video_id, now()),
        )
        await db.commit()


# ---------- Заявки на пополнение ----------

async def create_topup_request(user_id: int, amount_money: int | None, amount_coins: int | None,
                                method: str, screenshot_file_id: str | None = None,
                                purpose: str = "coins") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO topup_requests (user_id, amount_money, amount_coins, method, purpose, screenshot_file_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, amount_money, amount_coins, method, purpose, screenshot_file_id, now()),
        )
        await db.commit()
        return cur.lastrowid


async def get_topup_request(request_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM topup_requests WHERE id = ?", (request_id,))
        return await cur.fetchone()


async def set_topup_status(request_id: int, status: str, admin_comment: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE topup_requests SET status = ?, admin_comment = ? WHERE id = ?",
            (status, admin_comment, request_id),
        )
        await db.commit()


# ---------- Статистика для админа ----------

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        stats = {}
        cur = await db.execute("SELECT COUNT(*) FROM users")
        stats["users"] = (await cur.fetchone())[0]

        cur = await db.execute("SELECT COALESCE(SUM(coins),0) FROM users")
        stats["coins_in_circulation"] = (await cur.fetchone())[0]

        cur = await db.execute("SELECT COUNT(*) FROM purchases")
        stats["purchases"] = (await cur.fetchone())[0]

        cur = await db.execute("SELECT COUNT(*) FROM topup_requests WHERE status = 'pending'")
        stats["pending_topups"] = (await cur.fetchone())[0]

        return stats
