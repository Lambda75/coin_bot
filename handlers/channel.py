from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import ChannelAccess
from config import (
    CHANNEL_ACCESS_PRICE_KZT, KASPI_NUMBER, KASPI_NAME, CARD_NUMBER, ADMIN_IDS,
)

router = Router()


@router.callback_query(F.data == "channel_access")
async def cb_channel_access(call: CallbackQuery, state: FSMContext):
    text = (
        "🔐 Прямой доступ в приватный канал\n\n"
        f"Цена: <b>{CHANNEL_ACCESS_PRICE_KZT} тг</b> (без использования коинов)\n\n"
        f"Kaspi: {KASPI_NUMBER} ({KASPI_NAME})\n"
        f"Карта: {CARD_NUMBER}\n\n"
        "После оплаты пришли, пожалуйста, скриншот перевода (фото)."
    )
    await call.message.answer(text)
    await state.set_state(ChannelAccess.waiting_screenshot)
    await call.answer()


@router.message(ChannelAccess.waiting_screenshot, F.photo)
async def process_channel_screenshot(message: Message, state: FSMContext, bot: Bot):
    screenshot_file_id = message.photo[-1].file_id

    request_id = await db.create_topup_request(
        user_id=message.from_user.id,
        amount_money=CHANNEL_ACCESS_PRICE_KZT,
        amount_coins=None,
        method="manual",
        screenshot_file_id=screenshot_file_id,
        purpose="channel",
    )
    await state.clear()

    await message.answer("Заявка отправлена администратору. Как только подтвердят — пришлю ссылку на канал ✅")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                screenshot_file_id,
                caption=(
                    f"🆕 Заявка на ДОСТУП В КАНАЛ #{request_id}\n"
                    f"От: @{message.from_user.username or message.from_user.id} (id {message.from_user.id})\n"
                    f"Сумма: {CHANNEL_ACCESS_PRICE_KZT} тг"
                ),
                reply_markup=kb.admin_topup_decision_keyboard(request_id),
            )
        except Exception:
            pass


@router.message(ChannelAccess.waiting_screenshot)
async def process_channel_screenshot_wrong(message: Message):
    await message.answer("Нужно именно фото (скриншот перевода). Пришли фото.")
