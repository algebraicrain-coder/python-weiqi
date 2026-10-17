import tempfile
import unittest
from pathlib import Path

from goban import Game
from goban.cli import make_move_source, play_game, settings_phase
from goban.player import Command


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


class SettingsPhaseTest(unittest.TestCase):
    def test_set_and_show_field(self):
        game = Game(size=9)
        metadata = {}
        settings_phase(
            game, metadata, reader=_reader(["PB Alice", "show", "done"]), writer=_silent
        )
        self.assertEqual(metadata["PB"], "Alice")

    def test_alias_maps_to_property(self):
        game = Game(size=9)
        metadata = {}
        settings_phase(game, metadata, reader=_reader(["black Bob", "done"]), writer=_silent)
        self.assertEqual(metadata["PB"], "Bob")

    def test_set_komi(self):
        game = Game(size=9, komi=7.5)
        settings_phase(game, {}, reader=_reader(["komi 6.5", "done"]), writer=_silent)
        self.assertEqual(game.board.komi, 6.5)

    def test_set_size_before_moves(self):
        game = Game(size=19)
        settings_phase(game, {}, reader=_reader(["size 13", "done"]), writer=_silent)
        self.assertEqual(game.board.size, 13)

    def test_size_refused_after_moves(self):
        game = Game(size=9)
        game.play(game.board.index(2, 2))
        settings_phase(game, {}, reader=_reader(["size 13", "done"]), writer=_silent)
        self.assertEqual(game.board.size, 9)

    def test_clear_field(self):
        game = Game(size=9)
        metadata = {"PB": "Alice"}
        settings_phase(game, metadata, reader=_reader(["del PB", "done"]), writer=_silent)
        self.assertNotIn("PB", metadata)

    def test_unknown_field_ignored(self):
        game = Game(size=9)
        metadata = {}
        settings_phase(game, metadata, reader=_reader(["nonsense x", "done"]), writer=_silent)
        self.assertEqual(metadata, {})


class MergeMetadataTest(unittest.TestCase):
    def test_merge_keeps_existing_and_skips_board_fields(self):
        from goban import GameRecord
        from goban.cli import merge_record_metadata

        record = GameRecord.from_sgf("(;SZ[9]KM[6.5]PB[Alice]PW[Bob]EV[Cup]RE[W+1.5]AP[x])")
        metadata = {"PB": "Override"}
        merge_record_metadata(metadata, record)
        self.assertEqual(metadata["PB"], "Override")
        self.assertEqual(metadata["PW"], "Bob")
        self.assertEqual(metadata["EV"], "Cup")
        self.assertNotIn("SZ", metadata)
        self.assertNotIn("KM", metadata)
        self.assertNotIn("AP", metadata)
        self.assertNotIn("RE", metadata)


class SettingsCommandTest(unittest.TestCase):
    def test_trigger_raises_settings_command(self):
        game = Game(size=9)
        source = make_move_source(_reader(["set"]))
        with self.assertRaises(Command) as caught:
            source(game)
        self.assertEqual(caught.exception.command, "settings")

    def test_at_symbol_triggers(self):
        game = Game(size=9)
        source = make_move_source(_reader(["@"]))
        with self.assertRaises(Command) as caught:
            source(game)
        self.assertEqual(caught.exception.command, "settings")


class SettingsIntegrationTest(unittest.TestCase):
    def test_metadata_from_settings_reaches_sgf(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Game(size=9)
            responses = ["set", "PB Alice", "PW Bob", "done", "D4", "pass", "pass", "done", "y", ""]
            play_game(
                game, record_dir=tmp, reader=_reader(responses), writer=_silent
            )
            files = list(Path(tmp).glob("*.sgf"))
            self.assertEqual(len(files), 1)
            text = files[0].read_text(encoding="utf-8")
            self.assertIn("PB[Alice]", text)
            self.assertIn("PW[Bob]", text)


if __name__ == "__main__":
    unittest.main()
