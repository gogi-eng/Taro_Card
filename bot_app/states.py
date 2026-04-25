from aiogram.fsm.state import State, StatesGroup


class OrderFlow(StatesGroup):
    entering_question = State()
    choosing_payment = State()
    awaiting_payment_confirm = State()
    waiting_payment_proof = State()
    waiting_tron_tx_hash = State()


class FreeOneCard(StatesGroup):
    enter_question = State()


class AdminDelivery(StatesGroup):
    waiting_reading = State()
