from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Баланс", callback_data="balance")
    kb.button(text="🎲 Случайное видео", callback_data="random_video")
    kb.button(text="🪙 Купить коины", callback_data="topup")
    kb.button(text="🔐 Доступ в канал", callback_data="channel_access")
    kb.button(text="👥 Реферальная ссылка", callback_data="referral")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def topup_methods_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇰🇿 Kaspi / банк (вручную)", callback_data="topup_manual")
    kb.button(text="💳 Крипта (CryptoBot)", callback_data="topup_crypto")
    kb.button(text="⬅️ Назад", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def admin_topup_decision_keyboard(request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"admtopup_ok_{request_id}")
    kb.button(text="❌ Отклонить", callback_data=f"admtopup_no_{request_id}")
    kb.adjust(2)
    return kb.as_markup()
