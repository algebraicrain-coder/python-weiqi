import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from goban import web


class WebGameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wg = web.WebGame(record_dir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_defaults(self):
        state = self.wg.dispatch("new", {})
        self.assertEqual(state["size"], 19)
        self.assertEqual(state["ko"], "chinese")
        self.assertFalse(state["over"])

    def test_move_and_turn(self):
        self.wg.dispatch("new", {"size": 9})
        state = self.wg.dispatch("move", {"vertex": "D4"})
        self.assertEqual(state["to_play"], 2)
        self.assertEqual(sum(1 for c in state["grid"] if c), 1)

    def test_illegal_move_sets_message(self):
        self.wg.dispatch("new", {"size": 9})
        self.wg.dispatch("move", {"vertex": "D4"})
        state = self.wg.dispatch("move", {"vertex": "D4"})
        self.assertIn("illegal", state["message"])

    def test_pass_twice_counting(self):
        self.wg.dispatch("new", {"size": 9})
        self.wg.dispatch("pass", {})
        state = self.wg.dispatch("pass", {})
        self.assertTrue(state["over"])
        self.assertTrue(state["counting"])
        self.assertIsNotNone(state["score"])

    def test_dead_toggle_and_score(self):
        self.wg.dispatch("new", {"size": 5, "komi": 0.5})
        board = self.wg.game.board
        board.grid[board.index(1, 1)] = 2
        for x, y in ((0, 1), (2, 1), (1, 0)):
            board.grid[board.index(x, y)] = 1
        board.reset_positions()
        self.wg.dispatch("pass", {})
        self.wg.dispatch("pass", {})
        before = self.wg.dispatch("finish", {})["score"]
        self.wg.dispatch("dead", {"vertex": "B2"})
        after = self.wg.dispatch("finish", {})["score"]
        self.assertLess(after[1], before[1])

    def test_page_js_strings_are_not_split_by_newlines(self):
        script = web.PAGE.split("<script>", 1)[1].split("</script>", 1)[0]
        for lineno, line in enumerate(script.splitlines(), 1):
            if line.count("'") % 2:
                self.fail(f"unterminated JS string on script line {lineno}: {line!r}")

    def test_page_actions_use_post_and_state_uses_get(self):
        script = web.PAGE.split("<script>", 1)[1].split("</script>", 1)[0]
        self.assertIn("fetch('/api/state')", script)
        self.assertNotIn("payload === undefined", script)

    def test_save_txt_format_and_suffix(self):
        self.wg.dispatch("new", {"size": 9})
        self.wg.dispatch("move", {"vertex": "D4"})
        state = self.wg.dispatch("save", {"name": "game", "format": "txt"})
        path = Path(state["message"].split("saved to ")[1])
        self.assertEqual(path.suffix, ".txt")
        self.assertIn("moves:", path.read_text(encoding="utf-8"))

    def test_save_default_name_honours_format(self):
        self.wg.dispatch("new", {"size": 9})
        state = self.wg.dispatch("save", {"format": "txt"})
        path = Path(state["message"].split("saved to ")[1])
        self.assertEqual(path.suffix, ".txt")

    def test_save_unsupported_suffix_raises(self):
        self.wg.dispatch("new", {"size": 9})
        self.wg.dispatch("move", {"vertex": "D4"})
        with self.assertRaises(ValueError):
            self.wg.dispatch("save", {"name": "bad.md"})

    def test_settings_save_load_roundtrip(self):
        self.wg.dispatch("new", {"size": 9})
        self.wg.dispatch("settings", {"PB": "Alice", "PW": "Bob"})
        self.wg.dispatch("move", {"vertex": "D4"})
        saved = self.wg.dispatch("save", {"name": "rt.sgf"})
        self.assertTrue(Path(saved["message"].split("saved to ")[1]).exists())
        self.wg.dispatch("new", {"size": 9})
        loaded = self.wg.dispatch("load", {"name": "rt.sgf"})
        self.assertEqual(loaded["metadata"]["PB"], "Alice")
        self.assertEqual(sum(1 for c in loaded["grid"] if c), 1)


class WebHttpTest(unittest.TestCase):
    def test_http_endpoints(self):
        wg = web.WebGame(record_dir=tempfile.mkdtemp())
        server = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(wg))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            html = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn('<canvas id="board"', html)

            def post(path, payload=None):
                req = urllib.request.Request(
                    base + path,
                    data=json.dumps(payload or {}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                try:
                    return json.loads(urllib.request.urlopen(req).read())
                except urllib.error.HTTPError as error:
                    with error:
                        return json.loads(error.read())

            state = post("/api/new", {"size": 9})
            self.assertEqual(state["size"], 9)
            state = post("/api/move", {"vertex": "D4"})
            self.assertEqual(sum(1 for c in state["grid"] if c), 1)
            state = post("/api/move", {"vertex": "Z9"})
            self.assertIn("bad vertex", state["message"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
