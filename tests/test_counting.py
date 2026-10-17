import unittest

from goban import BLACK, WHITE, Board, Game
from goban.cli import mark_dead_phase


def place(board, color, *points):
    for x, y in points:
        board.grid[board.index(x, y)] = color


def _reader(responses):
    queue = iter(responses)

    def read(prompt=""):
        try:
            return next(queue)
        except StopIteration:
            raise EOFError

    return read


def _silent(*args, **kwargs):
    return None


class ScoreDeadTest(unittest.TestCase):
    def test_score_excludes_dead_stones(self):
        board = Board(size=5, komi=0.5)
        place(board, WHITE, (1, 1))
        place(board, BLACK, (0, 1), (2, 1), (1, 0))
        base = board.score()
        with_dead = board.score(dead={board.index(1, 1)})
        self.assertEqual(with_dead[1], base[1] - 1)
        self.assertGreater(with_dead[0], base[0])


class ToggleDeadTest(unittest.TestCase):
    def setUp(self):
        self.game = Game(size=5)
        place(self.game.board, WHITE, (1, 1), (1, 2))
        place(self.game.board, BLACK, (0, 1), (0, 2), (2, 1), (2, 2), (1, 0))

    def test_toggle_marks_whole_group(self):
        count = self.game.toggle_dead(self.game.board.index(1, 1))
        self.assertEqual(count, 2)
        self.assertEqual(len(self.game.dead), 2)

    def test_toggle_again_revives(self):
        self.game.toggle_dead(self.game.board.index(1, 1))
        self.game.toggle_dead(self.game.board.index(1, 2))
        self.assertEqual(self.game.dead, set())

    def test_empty_point_does_nothing(self):
        self.assertEqual(self.game.toggle_dead(self.game.board.index(4, 4)), 0)


class MarkDeadPhaseTest(unittest.TestCase):
    def test_mark_then_done(self):
        game = Game(size=5)
        place(game.board, WHITE, (1, 1))
        place(game.board, BLACK, (0, 1), (2, 1), (1, 0))
        reader = _reader(["dead B2", "done"])
        action = mark_dead_phase(game, reader=reader, writer=_silent)
        self.assertEqual(action, "done")
        self.assertEqual(game.dead, {game.board.index(1, 1)})

    def test_undo_resumes_play(self):
        game = Game(size=9)
        game.play(game.board.index(2, 2))
        game.pass_move()
        game.pass_move()
        self.assertTrue(game.over)
        reader = _reader(["undo"])
        action = mark_dead_phase(game, reader=reader, writer=_silent)
        self.assertEqual(action, "resumed")
        self.assertFalse(game.over)

    def test_bare_vertex_toggles(self):
        game = Game(size=5)
        place(game.board, WHITE, (1, 1))
        reader = _reader(["B2", "done"])
        mark_dead_phase(game, reader=reader, writer=_silent)
        self.assertIn(game.board.index(1, 1), game.dead)

    def test_result_reflects_dead_removal(self):
        game = Game(size=5, komi=0.5)
        place(game.board, WHITE, (1, 1))
        place(game.board, BLACK, (0, 1), (2, 1), (1, 0))
        before = game.result()
        game.toggle_dead(game.board.index(1, 1))
        after = game.result()
        self.assertGreater(after["score"][0], before["score"][0])
        self.assertLess(after["score"][1], before["score"][1])


if __name__ == "__main__":
    unittest.main()
