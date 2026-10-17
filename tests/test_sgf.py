import tempfile
import unittest
from pathlib import Path

from goban import BLACK, PASS, WHITE, Game, GameRecord
from goban.cli import play_game
from goban.record import (
    DEFAULT_FORMAT,
    default_filename,
    record_format,
    resolve_write_path,
)
from goban.sgf import (
    SGFError,
    SGFNode,
    index_to_sgf,
    parse_sgf,
    serialize_sgf,
    sgf_to_index,
)


class ParseTest(unittest.TestCase):
    def test_basic_properties(self):
        trees = parse_sgf("(;GM[1]FF[4]SZ[19]PB[Alice];B[pd];W[dd])")
        self.assertEqual(len(trees), 1)
        root = trees[0]
        self.assertEqual(root.get("PB"), "Alice")
        self.assertEqual(root.get("SZ"), "19")
        self.assertEqual(len(root.children), 1)
        self.assertEqual(root.children[0].get("B"), "pd")
        self.assertEqual(root.children[0].children[0].get("W"), "dd")

    def test_empty_value_is_pass(self):
        root = parse_sgf("(;B[];W[pd])")[0]
        self.assertEqual(root.get("B"), "")

    def test_escaped_value(self):
        root = parse_sgf(r"(;C[a\]b\\c])")[0]
        self.assertEqual(root.get("C"), "a]b\\c")

    def test_collection_of_trees(self):
        trees = parse_sgf("(;B[aa])(;B[bb])")
        self.assertEqual(len(trees), 2)

    def test_unterminated_value_raises(self):
        with self.assertRaises(SGFError):
            parse_sgf("(;C[oops)")


class CoordinateTest(unittest.TestCase):
    def test_top_left(self):
        self.assertEqual(sgf_to_index("aa", 19), 18 * 19)

    def test_roundtrip(self):
        for idx in (0, 1, 18, 180, 360, 342):
            self.assertEqual(sgf_to_index(index_to_sgf(idx, 19), 19), idx)

    def test_pass_roundtrip(self):
        self.assertEqual(index_to_sgf(PASS, 19), "")
        self.assertEqual(sgf_to_index("", 19), PASS)

    def test_out_of_range_raises(self):
        with self.assertRaises(SGFError):
            sgf_to_index("zz", 19)


class SerializeTest(unittest.TestCase):
    def test_structure_roundtrip(self):
        text = "(;GM[1]SZ[9];B[cc];W[dd](;B[ee])(;B[ff]))"
        root = parse_sgf(text)[0]
        again = parse_sgf(serialize_sgf(root))[0]
        self.assertEqual(again.get("SZ"), "9")
        self.assertEqual(len(again.children), 1)
        bcc = again.children[0]
        self.assertEqual(bcc.get("B"), "cc")
        wdd = bcc.children[0]
        self.assertEqual(wdd.get("W"), "dd")
        self.assertEqual(len(wdd.children), 2)

    def test_branch_serialization(self):
        root = SGFNode()
        root.set("GM", "1")
        for value in ("aa", "bb"):
            child = SGFNode()
            child.set("B", value)
            root.children.append(child)
        parsed = parse_sgf(serialize_sgf(root))[0]
        self.assertEqual(len(parsed.children), 2)

    def test_escape_roundtrip(self):
        root = SGFNode()
        root.set("C", "x]y\\z")
        parsed = parse_sgf(serialize_sgf(root))[0]
        self.assertEqual(parsed.get("C"), "x]y\\z")


class RecordTest(unittest.TestCase):
    def _capture_game(self):
        game = Game(size=9, komi=6.5)
        for vertex in ("D5", "E5", "F5", "A1", "E4", "A2", "E6"):
            game.play(game.board.index(*_vertex_to_xy(vertex)))
        return game

    def test_roundtrip_moves(self):
        game = Game(size=9, komi=6.5)
        for vertex in ("D4", "E4", "D5", "E6"):
            game.play(game.board.index(*_vertex_to_xy(vertex)))
        record = GameRecord.from_game(game, {"PB": "Black", "PW": "White"})
        text = record.to_sgf()
        replayed = GameRecord.from_sgf(text).to_game()
        self.assertEqual(game.moves, replayed.moves)
        self.assertEqual(game.board.grid, replayed.board.grid)

    def test_roundtrip_with_capture_and_pass(self):
        game = self._capture_game()
        game.pass_move()
        game.pass_move()
        record = GameRecord.from_game(game)
        replayed = GameRecord.from_sgf(record.to_sgf()).to_game()
        self.assertEqual(game.moves, replayed.moves)
        self.assertEqual(game.board.grid, replayed.board.grid)
        self.assertEqual(game.board.captures[BLACK], 1)

    def test_metadata_and_result(self):
        game = Game(size=9)
        game.resign()
        record = GameRecord.from_game(game, {"PB": "Alice", "PW": "Bob"})
        meta = record.metadata()
        self.assertEqual(meta["PB"], "Alice")
        self.assertEqual(meta["RE"], "W+R")

    def test_setup_stones(self):
        root = parse_sgf("(;SZ[9]AB[dd][ee]PL[W];W[ff])")[0]
        record = GameRecord(root)
        steps = record.steps()
        dd = sgf_to_index("dd", 9)
        self.assertEqual(steps[0]["grid"][dd], BLACK)
        self.assertEqual(steps[0]["to_play"], WHITE)

    def test_saved_result_reflects_dead_stones(self):
        game = Game(size=5, komi=0.5)
        board = game.board
        board.grid[board.index(1, 1)] = WHITE
        for x, y in ((0, 1), (2, 1), (1, 0)):
            board.grid[board.index(x, y)] = BLACK
        board.reset_positions()
        game.pass_move()
        game.pass_move()
        game.toggle_dead(board.index(1, 1))
        record = GameRecord.from_game(game, {})
        black, white = game.score()
        expected = (
            f"B+{black - white:.1f}" if black > white else f"W+{white - black:.1f}"
        )
        self.assertEqual(record.metadata()["RE"], expected)

    def test_ae_setup_node_does_not_duplicate_step(self):
        root = parse_sgf("(;SZ[5]KM[0.5];B[cc];W[dd];B[];W[];AE[bb])")[0]
        steps = GameRecord(root).steps()
        self.assertEqual(len(steps), 5)
        numbers = [step["number"] for step in steps]
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(len(set(numbers)), len(numbers))

    def test_save_and_load_file(self):
        game = Game(size=9)
        for vertex in ("D4", "E4"):
            game.play(game.board.index(*_vertex_to_xy(vertex)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.sgf"
            GameRecord.from_game(game, {"PB": "A", "PW": "B"}).save(str(path))
            loaded = GameRecord.load(str(path))
        self.assertEqual(loaded.metadata()["PB"], "A")
        self.assertEqual(loaded.moves(), game.moves)


def _vertex_to_xy(vertex):
    from goban import parse_vertex

    idx = parse_vertex(vertex, 9)
    return idx % 9, idx // 9


def _reader(responses):
    queue = iter(responses)

    def read(prompt=""):
        try:
            return next(queue)
        except StopIteration:
            raise EOFError

    return read


def _silent_writer(*args, **kwargs):
    return None


class PathAndSaveTest(unittest.TestCase):
    def test_bare_name_goes_to_record_dir(self):
        path = resolve_write_path("game.sgf", "/tmp/records")
        self.assertEqual(path, Path("/tmp/records/game.sgf"))

    def test_subdirectory_name_is_kept(self):
        path = resolve_write_path("sub/game.sgf", "/tmp/records")
        self.assertEqual(path, Path("sub/game.sgf"))

    def test_default_filename_uses_player_names(self):
        name = default_filename({"PB": "Alice", "PW": "Bob"})
        self.assertTrue(name.endswith("_Alice_vs_Bob.sgf"))

    def test_missing_suffix_gets_default_sgf(self):
        self.assertEqual(resolve_write_path("game", "/tmp/records"), Path("/tmp/records/game.sgf"))

    def test_missing_suffix_uses_chosen_format(self):
        path = resolve_write_path("game", "/tmp/records", default_format="txt")
        self.assertEqual(path, Path("/tmp/records/game.txt"))

    def test_default_filename_honours_format(self):
        self.assertTrue(default_filename({}, fmt="txt").endswith(".txt"))

    def test_record_format_reads_suffix(self):
        self.assertEqual(record_format("a/b.sgf"), "sgf")
        self.assertEqual(record_format("a/b.TXT"), "txt")
        self.assertEqual(record_format("noext"), DEFAULT_FORMAT)

    def test_save_writes_txt_and_sgf(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Game(size=9)
            game.play(0)
            game.play(9)
            record = GameRecord.from_game(game)
            sgf_path = Path(tmp) / "g.sgf"
            txt_path = Path(tmp) / "g.txt"
            record.save(sgf_path)
            record.save(txt_path)
            self.assertTrue(sgf_path.read_text(encoding="utf-8").startswith("("))
            text = txt_path.read_text(encoding="utf-8")
            self.assertIn("# 围棋棋谱", text)
            self.assertIn("1. B A1", text)
            self.assertIn("2. W A2", text)

    def test_serialize_defaults_to_sgf(self):
        record = GameRecord.from_game(Game(size=9))
        self.assertTrue(record.serialize().startswith("(;"))
        self.assertTrue(record.serialize("txt").startswith("# 围棋棋谱"))

    def test_save_rejects_unknown_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = GameRecord.from_game(Game(size=9))
            with self.assertRaises(ValueError):
                record.save(Path(tmp) / "g.md")

    def test_quit_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Game(size=9)
            reader = _reader(["D4", "q", "q"])
            play_game(game, record_dir=tmp, reader=reader, writer=_silent_writer)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_endgame_q_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Game(size=9)
            reader = _reader(["D4", "E4", "pass", "pass", "q"])
            play_game(game, record_dir=tmp, reader=reader, writer=_silent_writer)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_endgame_yes_saves_default_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Game(size=9)
            reader = _reader(["D4", "E4", "pass", "pass", "done", "y", ""])
            output = []
            play_game(game, record_dir=tmp, reader=reader, writer=output.append)
            files = list(Path(tmp).glob("*.sgf"))
            self.assertEqual(len(files), 1)
            self.assertTrue(any("saved to" in line for line in output))


if __name__ == "__main__":
    unittest.main()
