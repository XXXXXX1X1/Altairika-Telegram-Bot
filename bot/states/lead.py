from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    name = State()
    phone = State()
    time = State()       # только для booking
    city = State()       # только для franchise
    confirm = State()
    exit_confirm = State()  # пауза при попытке прервать форму
