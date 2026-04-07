from aiogram.fsm.state import State, StatesGroup


class UserQuestionForm(StatesGroup):
    waiting_text = State()
