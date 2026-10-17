import unittest

from goban import BLACK, WHITE, Board, Game, GameRecord
from goban.cli import settings_phase


def ko_position(ko_rule="chinese"):
    board = Board(size=5, ko_rule=ko_rule)
    board.grid[board.index(1, 2)] = BLACK
    board.grid[board.index(0, 1)] = BLACK
    board.grid[board.index(1, 0)] = BLACK
    board.grid[board.index(1, 1)] = WHITE
    board.grid[board.index(2, 2)] = WHITE
    board.grid[board.index(3, 1)] = WHITE
    board.grid[board.index(2, 0)] = WHITE
    board.to_play = BLACK
    board.reset_positions()
    return board


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


class ImmediateRecaptureTest(unittest.TestCase):
    def test_all_rules_forbid_immediate_recapture(self):
        for rule in ("chinese", "simple", "situational", "japanese"):
            board = ko_position(rule)
            board.play(board.index(2, 1))
            self.assertFalse(
                board.is_legal(board.index(1, 1)), f"rule {rule} should forbid ko recapture"
            )


class RuleDifferenceTest(unittest.TestCase):
    def test_positional_superko_forbids_any_repeat(self):
        board = ko_position("chinese")
        candidate, _ = board._result_position(board.index(2, 1), board.to_play)
        board._positions_grid.add(tuple(candidate))
        self.assertFalse(board.is_legal(board.index(2, 1)))

    def test_simple_ko_ignores_non_immediate_repeat(self):
        board = ko_position("simple")
        candidate, _ = board._result_position(board.index(2, 1), board.to_play)
        board._positions_grid.add(tuple(candidate))
        self.assertTrue(board.is_legal(board.index(2, 1)))

    def test_situational_superko_depends_on_side_to_move(self):
        board = ko_position("situational")
        candidate, _ = board._result_position(board.index(2, 1), board.to_play)
        board._positions_turn.add((tuple(candidate), WHITE))
        self.assertFalse(board.is_legal(board.index(2, 1)))

    def test_situational_allows_if_only_seen_with_other_side(self):
        board = ko_position("situational")
        candidate, _ = board._result_position(board.index(2, 1), board.to_play)
        board._positions_turn.add((tuple(candidate), BLACK))
        self.assertTrue(board.is_legal(board.index(2, 1)))


class JapaneseRuleTest(unittest.TestCase):
    def test_simple_ko_part(self):
        board = ko_position("japanese")
        board.play(board.index(2, 1))
        self.assertFalse(board.is_legal(board.index(1, 1)))

    def test_no_result_on_repetition(self):
        board = Board(size=5, komi=0, ko_rule="japanese")
        board.play_unchecked(board.index(0, 0))
        board.play_unchecked(board.index(4, 4))
        target = list(board.grid)
        target[board.index(1, 1)] = BLACK
        board._positions_turn.add((tuple(target), WHITE))
        self.assertFalse(board.no_result)
        board.play_unchecked(board.index(1, 1))
        self.assertTrue(board.no_result)

    def test_game_over_and_result_text(self):
        game = Game(size=5, ko_rule="japanese")
        game.board.no_result = True
        self.assertTrue(game.over)
        self.assertEqual(game.result()["reason"], "no-result")
        self.assertIn("No result", game.result_text())


class SelectionTest(unittest.TestCase):
    def test_default_is_chinese(self):
        self.assertEqual(Board().ko_rule, "chinese")
        self.assertEqual(Game().board.ko_rule, "chinese")

    def test_settings_change_ko(self):
        game = Game(size=9)
        settings_phase(game, {}, reader=_reader(["ko simple", "done"]), writer=_silent)
        self.assertEqual(game.board.ko_rule, "simple")

    def test_ru_label_written_from_ko_rule(self):
        game = Game(size=9, ko_rule="simple")
        record = GameRecord.from_game(game, {})
        self.assertEqual(record.metadata()["RU"], "Simple ko")


if __name__ == "__main__":
    unittest.main()
