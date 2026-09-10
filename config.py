import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "0") or 0)

KZT_PER_COIN = int(os.getenv("KZT_PER_COIN", "10"))

CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN", "")

REFERRAL_BONUS_COINS = int(os.getenv("REFERRAL_BONUS_COINS", "5"))

# Цена прямого доступа в приватный канал (без коинов, отдельная покупка)
CHANNEL_ACCESS_PRICE_KZT = int(os.getenv("CHANNEL_ACCESS_PRICE_KZT", "2000"))
# Та же цена, но в USDT — для оплаты через CryptoBot (задай сам под текущий курс)
CHANNEL_ACCESS_PRICE_USDT = float(os.getenv("CHANNEL_ACCESS_PRICE_USDT", "4"))
# Сколько часов действует одноразовая ссылка-приглашение в канал после оплаты
CHANNEL_INVITE_EXPIRE_HOURS = int(os.getenv("CHANNEL_INVITE_EXPIRE_HOURS", "24"))

KASPI_NUMBER = os.getenv("KASPI_NUMBER", "")
KASPI_NAME = os.getenv("KASPI_NAME", "")
CARD_NUMBER = os.getenv("CARD_NUMBER", "")

DB_PATH = os.getenv("DB_PATH", "bot.db")
