from aiogram.fsm.state import State, StatesGroup


class TopupManual(StatesGroup):
    waiting_amount = State()
    waiting_screenshot = State()


class TopupCrypto(StatesGroup):
    waiting_amount = State()


class ChannelAccess(StatesGroup):
    waiting_screenshot = State()


class AddVideo(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_price = State()
    waiting_content = State()  # видео файлом или ссылка на пост в канале


class AdjustCoins(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()
