import time

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
from states import AddVideo, AdjustCoins
from config import ADMIN_IDS, PRIVATE_CHANNEL_ID, CHANNEL_INVITE_EXPIRE_HOURS
from backup import send_backup_now

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def credit_topup_coins(user_id: int, amount_coins: int):
    """Начисляет коины пользователю после подтверждённой оплаты.
    Реферальный бонус сюда не входит — он начисляется сразу при регистрации по ссылке."""
    await db.add_coins(user_id, amount_coins, "topup", note="подтверждено админом")


async def generate_channel_invite(bot: Bot) -> str:
    """Создаёт одноразовую ссылку-приглашение в приватный канал с ограниченным сроком действия."""
    expire_at = int(time.time()) + CHANNEL_INVITE_EXPIRE_HOURS * 3600
    link = await bot.create_chat_invite_link(
        chat_id=PRIVATE_CHANNEL_ID,
        member_limit=1,
        expire_date=expire_at,
    )
    return link.invite_link


# ---------- Подтверждение ручных пополнений ----------

@router.callback_query(F.data.startswith("admtopup_ok_"))
async def cb_confirm_topup(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    request_id = int(call.data.split("_")[2])
    req = await db.get_topup_request(request_id)
    if not req or req["status"] != "pending":
        await call.answer("Заявка уже обработана", show_alert=True)
        return

    await db.set_topup_status(request_id, "confirmed")

    if req["purpose"] == "channel":
        try:
            invite_link = await generate_channel_invite(bot)
            await bot.send_message(
                req["user_id"],
                f"✅ Оплата подтверждена! Вот твоя ссылка на канал "
                f"(действует {CHANNEL_INVITE_EXPIRE_HOURS} ч. и только на 1 человека):\n{invite_link}",
            )
        except Exception:
            try:
                await bot.send_message(
                    req["user_id"],
                    "✅ Оплата подтверждена, но не удалось создать ссылку автоматически. "
                    "Администратор пришлёт её вручную.",
                )
            except Exception:
                pass
    else:
        await credit_topup_coins(req["user_id"], req["amount_coins"])
        try:
            await bot.send_message(
                req["user_id"],
                f"✅ Оплата подтверждена! Начислено {req['amount_coins']} коинов.",
            )
        except Exception:
            pass

    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n✅ ПОДТВЕРЖДЕНО")
    await call.answer("Подтверждено")


@router.callback_query(F.data.startswith("admtopup_no_"))
async def cb_reject_topup(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    request_id = int(call.data.split("_")[2])
    req = await db.get_topup_request(request_id)
    if not req or req["status"] != "pending":
        await call.answer("Заявка уже обработана", show_alert=True)
        return

    await db.set_topup_status(request_id, "rejected")
    try:
        await bot.send_message(req["user_id"], "❌ Оплата не подтверждена. Свяжись с администратором.")
    except Exception:
        pass

    await call.message.edit_caption(caption=(call.message.caption or "") + "\n\n❌ ОТКЛОНЕНО")
    await call.answer("Отклонено")


# ---------- Добавление видео ----------

@router.message(Command("addvideo"))
async def cmd_add_video(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Название видео?")
    await state.set_state(AddVideo.waiting_title)


@router.message(AddVideo.waiting_title)
async def add_video_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Описание (или '-' чтобы пропустить)?")
    await state.set_state(AddVideo.waiting_description)


@router.message(AddVideo.waiting_description)
async def add_video_description(message: Message, state: FSMContext):
    desc = None if message.text.strip() == "-" else message.text
    await state.update_data(description=desc)
    await message.answer("Цена в коинах? (число)")
    await state.set_state(AddVideo.waiting_price)


@router.message(AddVideo.waiting_price)
async def add_video_price(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Нужно число. Попробуй ещё раз.")
        return
    await state.update_data(price=int(message.text.strip()))
    await message.answer(
        "Теперь пришли само видео файлом,\n"
        "ИЛИ пришли текстом ссылку на пост в приватном канале."
    )
    await state.set_state(AddVideo.waiting_content)


@router.message(AddVideo.waiting_content, F.video)
async def add_video_content_file(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.add_video(
        title=data["title"],
        description=data.get("description"),
        price_coins=data["price"],
        file_id=message.video.file_id,
        channel_link=None,
    )
    await message.answer("✅ Видео добавлено в каталог.")
    await state.clear()


@router.message(AddVideo.waiting_content, F.text)
async def add_video_content_link(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.add_video(
        title=data["title"],
        description=data.get("description"),
        price_coins=data["price"],
        file_id=None,
        channel_link=message.text.strip(),
    )
    await message.answer("✅ Видео добавлено в каталог.")
    await state.clear()


# ---------- Ручная корректировка баланса ----------

@router.message(Command("addcoins"))
async def cmd_adjust_coins(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введи telegram_id пользователя:")
    await state.set_state(AdjustCoins.waiting_user_id)


@router.message(AdjustCoins.waiting_user_id)
async def adjust_coins_userid(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("Нужен числовой id.")
        return
    await state.update_data(user_id=int(message.text.strip()))
    await message.answer("Сколько коинов начислить? (можно отрицательное число, например -10)")
    await state.set_state(AdjustCoins.waiting_amount)


@router.message(AdjustCoins.waiting_amount)
async def adjust_coins_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно целое число.")
        return
    data = await state.get_data()
    user_id = data["user_id"]
    await db.add_coins(user_id, amount, "admin_adjust", note=f"вручную от {message.from_user.id}")
    await message.answer(f"Готово. Начислено {amount} коинов пользователю {user_id}.")
    try:
        await bot.send_message(user_id, f"Твой баланс изменён администратором на {amount} коинов.")
    except Exception:
        pass
    await state.clear()


# ---------- Ручной бэкап базы ----------

@router.message(Command("backup"))
async def cmd_backup(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Отправляю копию базы данных...")
    await send_backup_now(bot)


# ---------- Статистика ----------

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(
        "📊 Статистика:\n"
        f"Пользователей: {stats['users']}\n"
        f"Коинов в обороте: {stats['coins_in_circulation']}\n"
        f"Покупок: {stats['purchases']}\n"
        f"Заявок на пополнение в ожидании: {stats['pending_topups']}"
    )
