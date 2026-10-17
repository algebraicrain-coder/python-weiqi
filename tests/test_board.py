import unittest

from goban import BLACK, PASS, WHITE, Board, Game
from goban.board import format_vertex, parse_vertex


def place(board, color, *points):
    for x, y in points:
        board.grid[board.index(x, y)] = color


class CoordinateTest(unittest.TestCase):
    def test_roundtrip_without_i(self):
        self.assertEqual(format_vertex(parse_vertex("A1", 19), 19), "A1")
        self.assertEqual(format_vertex(parse_vertex("H8", 19), 19), "H8")
        self.assertEqual(format_vertex(parse_vertex("J8", 19), 19), "J8")
        self.assertEqual(format_vertex(parse_vertex("T19", 19), 19), "T19")

    def test_i_is_invalid(self):
        with self.assertRaises(ValueError):
            parse_vertex("I5", 19)

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            parse_vertex("T20", 19)


class CaptureTest(unittest.TestCase):
    def test_single_stone_capture(self):
        board = Board(size=3)
        place(board, WHITE, (1, 1))
        place(board, BLACK, (0, 1), (2, 1), (1, 0))
        captured = board.play(board.index(1, 2))
        self.assertEqual(captured, 1)
        self.assertEqual(board.grid[board.index(1, 1)], 0)
        self.assertEqual(board.captures[BLACK], 1)

    def test_suicide_is_illegal(self):
        board = Board(size=3)
        place(board, BLACK, (0, 1), (2, 1), (1, 0), (1, 2))
        board.to_play = WHITE
        self.assertFalse(board.is_legal(board.index(1, 1)))

    def test_group_with_liberty_is_alive(self):
        board = Board(size=3)
        place(board, WHITE, (1, 1))
        place(board, BLACK, (0, 1), (2, 1))
        captured = board.play(board.index(1, 0))
        self.assertEqual(captured, 0)


class KoTest(unittest.TestCase):
    def setUp(self):
        self.board = Board(size=5)
        place(self.board, BLACK, (1, 2), (0, 1), (1, 0))
        place(self.board, WHITE, (1, 1), (2, 2), (3, 1), (2, 0))
        self.board.reset_positions()

    def test_capture_starts_ko(self):
        captured = self.board.play(self.board.index(2, 1))
        self.assertEqual(captured, 1)

    def test_recapture_is_illegal(self):
        self.board.play(self.board.index(2, 1))
        self.assertFalse(self.board.is_legal(self.board.index(1, 1)))

    def test_undo_restores_position(self):
        before = tuple(self.board.grid)
        self.board.play(self.board.index(2, 1))
        self.board.undo()
        self.assertEqual(tuple(self.board.grid), before)


class ScoreTest(unittest.TestCase):
    def test_area_scoring_with_komi(self):
        board = Board(size=3, komi=0.5)
        place(board, BLACK, (1, 0), (0, 1))
        place(board, WHITE, (2, 2))
        black, white = board.score()
        self.assertEqual(black, 3.0)
        self.assertEqual(white, 1.5)

    def test_empty_board_is_komi_only(self):
        board = Board(size=9, komi=6.5)
        self.assertEqual(board.score(), (0.0, 6.5))


class GameTest(unittest.TestCase):
    def test_two_passes_end_game(self):
        game = Game(size=9, komi=6.5)
        game.pass_move()
        game.pass_move()
        self.assertTrue(game.over)
        self.assertEqual(game.result()["reason"], "score")
        self.assertEqual(game.passes, 2)

    def test_undo_removes_move_and_pass(self):
        game = Game(size=9)
        game.play(game.board.index(2, 2))
        game.pass_move()
        self.assertEqual(len(game.moves), 2)
        game.undo()
        game.undo()
        self.assertEqual(len(game.moves), 0)
        self.assertEqual(game.board.to_play, BLACK)

    def test_resign_result(self):
        game = Game(size=9)
        game.resign()
        result = game.result()
        self.assertEqual(result["winner"], WHITE)
        self.assertEqual(result["reason"], "resign")


if __name__ == "__main__":
    unittest.main()
