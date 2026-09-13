from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import TopupManual
from config import (
    REFERRAL_BONUS_COINS, KASPI_NUMBER, KASPI_NAME, CARD_NUMBER,
    KZT_PER_COIN, ADMIN_IDS, PRIVATE_CHANNEL_ID,
)
from database import STARTING_COINS

router = Router()


# ---------- /start ----------

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot):
    referrer_id = None
    if command.args and command.args.startswith("ref"):
        try:
            referrer_id = int(command.args.replace("ref", ""))
        except ValueError:
            referrer_id = None

    is_new_user = await db.get_or_create_user(message.from_user.id, message.from_user.username, referrer_id)

    # Реферальный бонус начисляется сразу, один раз, только для нового пользователя
    if is_new_user and referrer_id and referrer_id != message.from_user.id:
        await db.add_coins(
            referrer_id, REFERRAL_BONUS_COINS, "referral_bonus",
            note=f"за приглашение user_id={message.from_user.id}",
        )
        await db.mark_referral_rewarded(message.from_user.id)
        try:
            await bot.send_message(
                referrer_id,
                f"🎉 По твоей ссылке зарегистрировался новый пользователь! "
                f"Тебе начислено {REFERRAL_BONUS_COINS} коинов.",
            )
        except Exception:
            pass

    greeting = "Привет! 👋\n\nЭто закрытый канал с приватными видео из Казахстана и стран Азии🍑 Только реальные домашние архивы, любительские съемки и горячий эксклюзив.🔥\n"
    if is_new_user:
        greeting += f"Тебе начислено {STARTING_COINS} стартовых коинов 🎁\n"
    greeting += "\n\nНикакой цензуры. Включай просмотр прямо в чате за коины или получай их бесплатно в нашей рефералке.\n\nЛибо сразу получить доступ на приватный канал🔞\n\nВыбирай:"

    await message.answer(greeting, reply_markup=kb.main_menu())


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery):
    await call.message.edit_text("Главное меню:", reply_markup=kb.main_menu())
    await call.answer()


# ---------- Баланс ----------

@router.callback_query(F.data == "balance")
async def cb_balance(call: CallbackQuery):
    balance = await db.get_balance(call.from_user.id)
    refs = await db.count_referrals(call.from_user.id)
    await call.message.edit_text(
        f"💰 Твой баланс: <b>{balance} коинов</b>\n"
        f"👥 Приглашено друзей: {refs}",
        reply_markup=kb.main_menu(),
        parse_mode="HTML",
    )
    await call.answer()


# ---------- Реферальная ссылка ----------

@router.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery, bot: Bot):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref{call.from_user.id}"
    refs = await db.count_referrals(call.from_user.id)
    await call.message.edit_text(
        f"👥 Твоя реферальная ссылка:\n{link}\n\n"
        f"За каждого друга, который запустит бота по этой ссылке, "
        f"ты сразу получишь <b>{REFERRAL_BONUS_COINS} коинов</b>.\n\n"
        f"Уже приглашено: {refs} чел.",
        reply_markup=kb.main_menu(),
        parse_mode="HTML",
    )
    await call.answer()


# ---------- Случайное видео ----------

@router.callback_query(F.data == "random_video")
async def cb_random_video(call: CallbackQuery, bot: Bot):
    import random

    videos = await db.list_active_videos()
    if not videos:
        await call.message.answer("Пока видео нет 🙁")
        await call.answer()
        return

    video = random.choice(videos)
    already = await db.has_purchased(call.from_user.id, video["id"])

    if not already:
        balance = await db.get_balance(call.from_user.id)
        if balance < video["price_coins"]:
            await call.answer(
                f"Недостаточно коинов. Нужно {video['price_coins']}, у тебя {balance}.",
                show_alert=True,
            )
            return
        await db.add_coins(call.from_user.id, -video["price_coins"], "purchase", note=f"video_id={video['id']}")
        await db.record_purchase(call.from_user.id, video["id"])

    if video["file_id"]:
        await bot.send_video(call.from_user.id, video["file_id"], caption=video["title"])
    elif video["channel_link"]:
        await call.message.answer(f"Вот твоя ссылка на видео:\n{video['channel_link']}")
    else:
        await call.message.answer("Видео открыто, но ссылка не настроена — напиши администратору.")

    await call.answer("Готово! 🎲")


# ---------- Пополнение баланса ----------

@router.callback_query(F.data == "topup")
async def cb_topup(call: CallbackQuery):
    await call.message.edit_text(
        "Выбери способ пополнения:",
        reply_markup=kb.topup_methods_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data == "topup_manual")
async def cb_topup_manual(call: CallbackQuery, state: FSMContext):
    text = (
        "💳 Реквизиты для пополнения:\n\n"
        f"Kaspi: {KASPI_NUMBER} ({KASPI_NAME})\n"
        f"Карта: {CARD_NUMBER}\n\n"
        f"Курс: 1 коин = {KZT_PER_COIN} тг\n\n"
        "Переведи любую сумму, затем напиши мне сумму в тенге, "
        "которую перевёл (просто числом)."
    )
    await call.message.answer(text)
    await state.set_state(TopupManual.waiting_amount)
    await call.answer()


@router.message(TopupManual.waiting_amount)
async def process_topup_amount(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Пришли, пожалуйста, только число (сумму в тенге).")
        return
    amount_money = int(message.text.strip())
    amount_coins = amount_money // KZT_PER_COIN
    await state.update_data(amount_money=amount_money, amount_coins=amount_coins)
    await message.answer(
        f"Отлично, это ~{amount_coins} коинов.\n"
        "Теперь пришли скриншот перевода (фото)."
    )
    await state.set_state(TopupManual.waiting_screenshot)


@router.message(TopupManual.waiting_screenshot, F.photo)
async def process_topup_screenshot(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount_money = data.get("amount_money")
    amount_coins = data.get("amount_coins")
    screenshot_file_id = message.photo[-1].file_id

    request_id = await db.create_topup_request(
        user_id=message.from_user.id,
        amount_money=amount_money,
        amount_coins=amount_coins,
        method="manual",
        screenshot_file_id=screenshot_file_id,
    )
    await state.clear()

    await message.answer("Заявка отправлена администратору. Как только подтвердят — коины начислятся ✅")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                screenshot_file_id,
                caption=(
                    f"🆕 Заявка на пополнение #{request_id}\n"
                    f"От: @{message.from_user.username or message.from_user.id} (id {message.from_user.id})\n"
                    f"Сумма: {amount_money} тг → {amount_coins} коинов"
                ),
                reply_markup=kb.admin_topup_decision_keyboard(request_id),
            )
        except Exception:
            pass


@router.message(TopupManual.waiting_screenshot)
async def process_topup_screenshot_wrong(message: Message):
    await message.answer("Нужно именно фото (скриншот перевода). Пришли фото.")
