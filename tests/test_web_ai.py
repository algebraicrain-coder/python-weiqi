import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from goban import web
from goban.ai import EngineError, EngineUnavailable
from goban.board import PASS, parse_vertex
from goban.player import RESIGN


class FakeEngine:
    name = "Fake"

    def __init__(self, move=None, error=None):
        self.move = move
        self.error = error
        self.seen = []
        self.closed = False

    def available(self):
        return True

    def genmove(self, position):
        self.seen.append(position)
        if self.error is not None:
            raise self.error
        return self.move

    def close(self):
        self.closed = True


class WebAITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def game_with_ai(self, move):
        engine = FakeEngine(move=move)
        wg = web.WebGame(record_dir=self.root, engine=engine)
        wg.dispatch("new", {"size": 9})
        return wg, engine

    def test_ai_move(self):
        wg, engine = self.game_with_ai(parse_vertex("D4", 9))
        state = wg.request_ai_move()
        self.assertTrue(state["ai_available"])
        self.assertFalse(state["ai_thinking"])
        self.assertEqual(sum(1 for c in state["grid"] if c), 1)
        self.assertEqual(state["to_play"], 2)
        self.assertEqual(len(engine.seen), 1)
        self.assertEqual(engine.seen[0].size, 9)
        self.assertEqual(engine.seen[0].moves, ())

    def test_ai_pass(self):
        wg, _ = self.game_with_ai(PASS)
        state = wg.request_ai_move()
        self.assertEqual(state["passes"], 1)
        self.assertEqual(sum(1 for c in state["grid"] if c), 0)

    def test_ai_resign(self):
        wg, _ = self.game_with_ai(RESIGN)
        state = wg.request_ai_move()
        self.assertTrue(state["over"])
        self.assertIsNotNone(state["resigned_by"])

    def test_ai_error_clears_thinking(self):
        engine = FakeEngine(error=EngineError("boom"))
        wg = web.WebGame(record_dir=self.root, engine=engine)
        wg.dispatch("new", {"size": 9})
        with self.assertRaises(EngineError):
            wg.request_ai_move()
        state = wg.to_state()
        self.assertFalse(state["ai_thinking"])
        self.assertIn("boom", state["ai_hint"])

    def test_ai_disabled(self):
        wg = web.WebGame(record_dir=self.root, ai_config=False)
        state = wg.to_state()
        self.assertFalse(state["ai_available"])
        self.assertEqual(state["ai_hint"], "AI 已禁用")
        with self.assertRaises(EngineUnavailable):
            wg.request_ai_move()

    def test_ai_cancelled_when_position_changes(self):
        class MutatingEngine:
            name = "Fake"

            def __init__(self):
                self.wg = None

            def available(self):
                return True

            def genmove(self, position):
                # 模拟 AI 思考期间人类抢先落子。
                self.wg.dispatch("move", {"vertex": "E5"})
                return parse_vertex("D4", 9)

            def close(self):
                pass

        engine = MutatingEngine()
        wg = web.WebGame(record_dir=self.root, engine=engine)
        engine.wg = wg
        wg.dispatch("new", {"size": 9})
        state = wg.request_ai_move()
        self.assertIn("取消", state["message"])
        self.assertEqual(len(wg.game.moves), 1)

    def test_http_ai_endpoint(self):
        engine = FakeEngine(move=parse_vertex("D4", 9))
        wg = web.WebGame(record_dir=self.root, engine=engine)
        wg.dispatch("new", {"size": 9})
        server = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(wg))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            request = urllib.request.Request(
                base + "/api/ai",
                data=b"{}",
                headers={"Content-Type": "application/json"},
            )
            state = json.load(urllib.request.urlopen(request))
            self.assertEqual(sum(1 for c in state["grid"] if c), 1)
            self.assertEqual(state["to_play"], 2)
        finally:
            server.shutdown()
            server.server_close()

    def test_bad_ai_config_does_not_crash_web(self):
        path = self.root / "ai.json"
        path.write_text("{bad json", encoding="utf-8")
        wg = web.WebGame(record_dir=self.root, ai_config_path=path)
        state = wg.to_state()
        self.assertFalse(state["ai_available"])
        self.assertIn("JSON", state["ai_hint"])

    def test_page_contains_ai_button(self):
        self.assertIn('id="b-ai"', web.PAGE)
        self.assertIn("/api/ai", web.PAGE)


if __name__ == "__main__":
    unittest.main()
