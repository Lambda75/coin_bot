import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.types import FSInputFile

from config import ADMIN_IDS, DB_PATH

BACKUP_INTERVAL_SECONDS = 24 * 60 * 60  # раз в сутки


async def send_backup_now(bot: Bot):
    """Отправляет текущий файл базы данных всем админам одним разом."""
    try:
        file = FSInputFile(DB_PATH, filename=f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db")
    except FileNotFoundError:
        logging.warning("Файл базы данных для бэкапа не найден: %s", DB_PATH)
        return

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                admin_id,
                file,
                caption=f"🗄 Резервная копия базы данных\n{datetime.now().strftime('%d.%m.%Y %H:%M')}",
            )
        except Exception as e:
            logging.warning("Не удалось отправить бэкап админу %s: %s", admin_id, e)


async def backup_loop(bot: Bot):
    """Бесконечный цикл: раз в сутки отправляет свежий бэкап базы данных."""
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
        await send_backup_now(bot)
