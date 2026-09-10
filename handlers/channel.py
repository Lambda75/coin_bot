from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
import keyboards as kb
from states import ChannelAccess
from config import (
    CHANNEL_ACCESS_PRICE_KZT, CHANNEL_ACCESS_PRICE_USDT,
    KASPI_NUMBER, KASPI_NAME, CARD_NUMBER, ADMIN_IDS, CRYPTOBOT_TOKEN,
)
from handlers.payment import cryptobot_request
from handlers.admin import generate_channel_invite

router = Router()


@router.callback_query(F.data == "channel_access")
async def cb_channel_access(call: CallbackQuery):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Kaspi / карта", callback_data="channel_manual")
    keyboard.button(text="🪙 Крипта (CryptoBot)", callback_data="channel_crypto")
    keyboard.adjust(1)

    await call.message.answer(
        "🔐 Прямой доступ в приватный канал\n\n"
        f"Цена: <b>{CHANNEL_ACCESS_PRICE_KZT} тг</b> или <b>{CHANNEL_ACCESS_PRICE_USDT} USDT</b>\n\n"
        "Выбери способ оплаты:",
        reply_markup=keyboard.as_markup(),
    )
    await call.answer()


# ---------- Оплата вручную (Kaspi/карта + скриншот) ----------

@router.callback_query(F.data == "channel_manual")
async def cb_channel_manual(call: CallbackQuery, state: FSMContext):
    text = (
        "💳 Реквизиты для оплаты доступа в канал:\n\n"
        f"Kaspi: {KASPI_NUMBER} ({KASPI_NAME})\n"
        f"Карта: {CARD_NUMBER}\n\n"
        f"Сумма: {CHANNEL_ACCESS_PRICE_KZT} тг\n\n"
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


# ---------- Оплата криптой через CryptoBot (автоматическое подтверждение) ----------

@router.callback_query(F.data == "channel_crypto")
async def cb_channel_crypto(call: CallbackQuery, bot: Bot):
    if not CRYPTOBOT_TOKEN:
        await call.message.answer(
            "Оплата криптой пока не настроена администратором. Выбери Kaspi / карту."
        )
        await call.answer()
        return

    invoice = await cryptobot_request(
        "createInvoice",
        asset="USDT",
        amount=CHANNEL_ACCESS_PRICE_USDT,
        description="Доступ в приватный канал",
        payload=f"channel_access:{call.from_user.id}",
    )

    if not invoice:
        await call.message.answer("Не удалось создать счёт. Попробуй позже или напиши администратору.")
        await call.answer()
        return

    request_id = await db.create_topup_request(
        user_id=call.from_user.id,
        amount_money=None,
        amount_coins=None,
        method="cryptobot",
        purpose="channel",
    )
    await db.set_topup_status(request_id, "pending", admin_comment=str(invoice["invoice_id"]))

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Оплатить", url=invoice["pay_url"])
    keyboard.button(text="✅ Я оплатил", callback_data=f"checkchannelcrypto_{request_id}")
    keyboard.adjust(1)

    await call.message.answer(
        f"Счёт на {CHANNEL_ACCESS_PRICE_USDT} USDT создан.\n"
        "Оплати по кнопке ниже, затем нажми «Я оплатил».",
        reply_markup=keyboard.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("checkchannelcrypto_"))
async def cb_check_channel_crypto(call: CallbackQuery, bot: Bot):
    request_id = int(call.data.split("_")[1])
    req = await db.get_topup_request(request_id)
    if not req or req["status"] != "pending":
        await call.answer("Заявка уже обработана", show_alert=True)
        return

    invoice_id = req["admin_comment"]
    result = await cryptobot_request("getInvoices", invoice_ids=invoice_id)

    paid = False
    if result and result.get("items"):
        paid = result["items"][0]["status"] == "paid"

    if not paid:
        await call.answer(
            "Оплата пока не найдена. Если только что оплатил — подожди минуту и попробуй снова.",
            show_alert=True,
        )
        return

    await db.set_topup_status(request_id, "confirmed")
    try:
        invite_link = await generate_channel_invite(bot)
        await call.message.answer(
            f"✅ Оплата получена! Вот твоя ссылка на канал:\n{invite_link}"
        )
    except Exception:
        await call.message.answer(
            "✅ Оплата получена, но не удалось создать ссылку автоматически. "
            "Администратор пришлёт её вручную."
        )
