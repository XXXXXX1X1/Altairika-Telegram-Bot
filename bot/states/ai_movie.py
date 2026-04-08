from aiogram.fsm.state import State, StatesGroup


class AiPick(StatesGroup):
    waiting = State()   # ожидание ответа пользователя
    refine = State()    # уточнение параметров (сохраняем предыдущие)
