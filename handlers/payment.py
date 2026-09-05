"""
Оплата через CryptoBot (Crypto Pay API).

Как подключить:
1. В Telegram открыть @CryptoBot -> Crypto Pay -> Create App.
2. Получить токен приложения и вписать его в .env как CRYPTOBOT_TOKEN.
3. Курс коинов к USDT задаётся ниже в USDT_PER_COIN — поменяй под себя.

Документация API: https://help.crypt.bot/crypto-pay-api
"""

import aiohttp
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import CRYPTOBOT_TOKEN
from states import TopupCrypto
import database as db
from handlers.admin import credit_topup_coins

router = Router()

CRYPTOBOT_API = "https://pay.crypt.bot/api"
USDT_PER_COIN = 0.05  # 1 коин = 0.05 USDT — поменяй под свой курс


async def cryptobot_request(method: str, **params):
    if not CRYPTOBOT_TOKEN:
        return None
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{CRYPTOBOT_API}/{method}", headers=headers, json=params) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]
            return None


@router.callback_query(F.data == "topup_crypto")
async def cb_topup_crypto(call: CallbackQuery, state: FSMContext):
    if not CRYPTOBOT_TOKEN:
        await call.message.answer(
            "Оплата криптой пока не настроена администратором. "
            "Выбери ручной способ пополнения."
        )
        await call.answer()
        return

    await call.message.answer(
        f"Сколько коинов хочешь купить? (1 коин = {USDT_PER_COIN} USDT)\nНапиши число."
    )
    await state.set_state(TopupCrypto.waiting_amount)
    await call.answer()


@router.message(TopupCrypto.waiting_amount)
async def process_crypto_amount(message: Message, state: FSMContext, bot: Bot):
    if not message.text.strip().isdigit():
        await message.answer("Нужно число (сколько коинов купить).")
        return

    amount_coins = int(message.text.strip())
    amount_usdt = round(amount_coins * USDT_PER_COIN, 2)

    invoice = await cryptobot_request(
        "createInvoice",
        asset="USDT",
        amount=amount_usdt,
        description=f"Пополнение {amount_coins} коинов",
        payload=f"user:{message.from_user.id}",
    )

    if not invoice:
        await message.answer("Не удалось создать счёт. Попробуй позже или напиши администратору.")
        await state.clear()
        return

    request_id = await db.create_topup_request(
        user_id=message.from_user.id,
        amount_money=None,
        amount_coins=amount_coins,
        method="cryptobot",
    )
    # сохраняем invoice_id прямо в заявке через комментарий, чтобы проверить позже
    await db.set_topup_status(request_id, "pending", admin_comment=str(invoice["invoice_id"]))

    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатить", url=invoice["pay_url"])
    kb.button(text="✅ Я оплатил", callback_data=f"checkcrypto_{request_id}")
    kb.adjust(1)

    await message.answer(
        f"Счёт на {amount_usdt} USDT создан.\nОплати по кнопке ниже, затем нажми «Я оплатил».",
        reply_markup=kb.as_markup(),
    )
    await state.clear()


@router.callback_query(F.data.startswith("checkcrypto_"))
async def cb_check_crypto(call: CallbackQuery, bot: Bot):
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

    if paid:
        await db.set_topup_status(request_id, "confirmed")
        await credit_topup_coins(req["user_id"], req["amount_coins"])
        await call.message.answer(f"✅ Оплата получена! Начислено {req['amount_coins']} коинов.")
    else:
        await call.answer("Оплата пока не найдена. Если только что оплатил — подожди минуту и попробуй снова.", show_alert=True)
