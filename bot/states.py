"""
states.py

Some flows need multiple messages back and forth (e.g. Deposit:
pick method -> upload screenshot -> enter reference number). We use
aiogram's FSM (Finite State Machine) to remember "which step is this
player on" between messages. This is stored in Redis (see bot/main.py),
so it survives bot restarts.
"""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    entering_name = State()
    entering_phone = State()


class DepositStates(StatesGroup):
    choosing_method = State()
    entering_amount = State()
    awaiting_screenshot = State()
    awaiting_reference_number = State()


class WithdrawStates(StatesGroup):
    choosing_method = State()
    entering_amount = State()
    entering_payment_details = State()


class ChallengeStates(StatesGroup):
    choosing_stake = State()
    entering_username = State()
