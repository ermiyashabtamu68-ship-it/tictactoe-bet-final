"""
test_game_logic.py

Tests the win/draw detection logic in match_service.py. These
functions don't touch the database, so these tests run instantly
with no setup required.

Run with: pytest api/tests/test_game_logic.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.match_service import check_winner, is_draw


def test_check_winner_row():
    assert check_winner("XXX______") == "X"
    assert check_winner("___OOO___") == "O"
    assert check_winner("______XXX") == "X"


def test_check_winner_column():
    assert check_winner("X__X__X__") == "X"
    assert check_winner("_O__O__O_") == "O"
    assert check_winner("__X__X__X") == "X"


def test_check_winner_diagonal():
    assert check_winner("X___X___X") == "X"
    assert check_winner("__O_O_O__") == "O"


def test_check_winner_no_winner_yet():
    assert check_winner("X__O_____") is None
    assert check_winner("_________") is None


def test_check_winner_full_board_no_winner():
    # A classic draw board
    assert check_winner("XOXXOOOXX") is None


def test_is_draw_true_when_full_and_no_winner():
    assert is_draw("XOXXOOOXX") is True


def test_is_draw_false_when_not_full():
    assert is_draw("XOX______") is False


def test_is_draw_false_when_someone_won_even_if_full():
    # Board is full AND has a winner - should NOT count as a draw
    board = "XXXOOXXOO"
    assert check_winner(board) == "X"
    assert is_draw(board) is False


def test_is_draw_false_on_empty_board():
    assert is_draw("_________") is False
