from aiogram.fsm.state import State, StatesGroup


class OrderFlow(StatesGroup):
    entering_question = State()
    awaiting_payment_confirm = State()
    waiting_payment_proof = State()
    waiting_tron_tx_hash = State()


class AdminDelivery(StatesGroup):
    waiting_reading = State()
