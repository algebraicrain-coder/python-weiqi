import io
import unittest
from contextlib import redirect_stdout

from goban import Game
from goban import help as helpmod
from goban.cli import main, make_move_source
from goban.player import Command


def _reader(responses):
    queue = iter(responses)

    def read(prompt=""):
        try:
            return next(queue)
        except StopIteration:
            raise EOFError

    return read


class HelpTextTest(unittest.TestCase):
    def test_summary_lists_play_commands(self):
        text = helpmod.resolve(None, "play")
        self.assertIn("pass", text)
        self.assertIn("save", text)

    def test_detail_for_command(self):
        text = helpmod.resolve("save", "play")
        self.assertIn("SGF", text)

    def test_topic_scoring(self):
        text = helpmod.resolve("scoring")
        self.assertIn("面积法", text)

    def test_set_detail_references_settings(self):
        text = helpmod.resolve("set", "play")
        self.assertIn("设置模式", text)
        self.assertIn("help settings", text)

    def test_settings_submode_has_own_detailed_help(self):
        summary = helpmod.resolve(None, "settings")
        self.assertIn("komi", summary)
        self.assertIn("del", summary)
        detail = helpmod.resolve("komi", "settings")
        self.assertIn("贴目", detail)

    def test_counting_submode_help(self):
        summary = helpmod.resolve(None, "counting")
        self.assertIn("dead", summary)
        detail = helpmod.resolve("dead", "counting")
        self.assertIn("死子", detail)

    def test_context_view(self):
        text = helpmod.resolve(None, "view")
        self.assertIn("next", text)

    def test_context_prefers_same_context(self):
        entry = helpmod.find("done", "settings")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.context, "settings")

    def test_unknown_topic(self):
        text = helpmod.resolve("zzz")
        self.assertIn("没有关于", text)

    def test_overview_non_empty(self):
        self.assertIn("对弈命令", helpmod.overview_text())

    def test_full_contains_details(self):
        self.assertIn("坐标系统", helpmod.full_text())


class HelpCommandTest(unittest.TestCase):
    def test_help_with_topic(self):
        source = make_move_source(_reader(["help scoring"]))
        with self.assertRaises(Command) as caught:
            source(Game(size=9))
        self.assertEqual(caught.exception.command, "help")
        self.assertEqual(caught.exception.argument, "scoring")


class HelpCliTest(unittest.TestCase):
    def test_main_help_topic(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["help", "scoring"])
        self.assertEqual(code, 0)
        self.assertIn("面积法", buffer.getvalue())

    def test_main_help_overview(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["help"])
        self.assertEqual(code, 0)
        self.assertIn("主题说明", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
