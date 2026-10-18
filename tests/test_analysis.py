import json
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from goban import web
from goban.ai import (
    Analysis,
    KataGoAnalysis,
    MoveEval,
    Position,
)
from goban.ai.config import AIConfig
from goban.board import BLACK, WHITE, parse_vertex


class FakeAnalyzer:
    name = "Fake analysis"

    def __init__(self):
        self.calls = 0
        self.cancelled = 0
        self.closed = False

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def analyze(self, position, on_update=None):
        self.calls += 1
        analysis = Analysis(
            key=position.key(),
            to_play=position.to_play,
            root_winrate=0.55,
            root_score_lead=1.2,
            moves=(
                MoveEval(
                    vertex="D4",
                    index=parse_vertex("D4", position.size),
                    visits=120,
                    winrate=0.55,
                    score_lead=1.2,
                    order=0,
                    pv=("D4",),
                ),
            ),
            ownership=tuple([0.4] * (position.size * position.size)),
            during_search=False,
        )
        if on_update is not None:
            on_update(analysis)
        return analysis

    def cancel(self):
        self.cancelled += 1

    def close(self):
        self.closed = True


class FakeEngine:
    name = "Fake engine"

    def available(self):
        return True

    def genmove(self, position):
        return parse_vertex("Q16", position.size)

    def close(self):
        pass


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class ParseTest(unittest.TestCase):
    def make_analyzer(self, winrates_as="BLACK"):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "analysis.cfg"
        path.write_text(f"reportAnalysisWinratesAs = {winrates_as}\n", encoding="utf-8")
        config = AIConfig(
            binary="/bin/true",
            model=__file__,
            analysis_config=str(path),
        )
        return KataGoAnalysis(config, winrates_as=winrates_as)

    def tearDown(self):
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def response(self):
        return {
            "id": "x",
            "isDuringSearch": False,
            "rootInfo": {"winrate": 0.6, "scoreLead": 2.0},
            "moveInfos": [
                {
                    "move": "Q16",
                    "visits": 100,
                    "winrate": 0.6,
                    "scoreLead": 2.0,
                    "order": 0,
                    "pv": ["Q16", "D4"],
                }
            ],
            "ownership": [0.5] * 361,
        }

    def test_black_perspective_parse(self):
        analyzer = self.make_analyzer("BLACK")
        position = Position(19, 7.5, "chinese", (), BLACK, (0,) * 361)
        analysis = analyzer._parse(self.response(), position)
        self.assertEqual(analysis.key, position.key())
        self.assertAlmostEqual(analysis.root_winrate, 0.6)
        self.assertAlmostEqual(analysis.root_score_lead, 2.0)
        self.assertEqual(analysis.moves[0].vertex, "Q16")
        self.assertEqual(analysis.moves[0].index, parse_vertex("Q16", 19))
        self.assertAlmostEqual(analysis.ownership[0], 0.5)

    def test_sidetomove_white_is_converted_to_black(self):
        analyzer = self.make_analyzer("SIDETOMOVE")
        position = Position(19, 7.5, "chinese", (), WHITE, (0,) * 361)
        analysis = analyzer._parse(self.response(), position)
        self.assertAlmostEqual(analysis.root_winrate, 0.4)
        self.assertAlmostEqual(analysis.root_score_lead, -2.0)
        self.assertAlmostEqual(analysis.ownership[0], -0.5)

    def test_parse_tolerates_unknown_move(self):
        analyzer = self.make_analyzer("BLACK")
        position = Position(9, 7.5, "chinese", (), BLACK, (0,) * 81)
        response = self.response()
        response["moveInfos"][0]["move"] = "not-a-vertex"
        analysis = analyzer._parse(response, position)
        self.assertEqual(analysis.moves, ())

    def test_analysis_visits_and_continuous_mode(self):
        position = Position(9, 7.5, "chinese", (), BLACK, (0,) * 81)
        config = AIConfig(
            binary="/bin/true",
            model=__file__,
            analysis_config=__file__,
            analysis_visits=1500,
        )
        analyzer = KataGoAnalysis(config, winrates_as="BLACK")
        self.assertEqual(analyzer._build_query(position, "x")["maxVisits"], 1500)
        config = AIConfig(
            binary="/bin/true",
            model=__file__,
            analysis_config=__file__,
            analysis_visits=0,
        )
        analyzer = KataGoAnalysis(config, winrates_as="BLACK")
        self.assertEqual(
            analyzer._build_query(position, "x")["maxVisits"],
            1_000_000_000,
        )


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.analyzer = FakeAnalyzer()
        self.wg = web.WebGame(
            record_dir=self.tmp.name,
            engine=FakeEngine(),
            analyzer=self.analyzer,
        )

    def tearDown(self):
        self.wg.close()
        self.tmp.cleanup()

    def test_enable_and_snapshot(self):
        self.wg.dispatch("analysis", {"enabled": True})
        self.assertTrue(
            wait_for(
                lambda: self.wg.analysis_state()["analysis"] is not None
            )
        )
        state = self.wg.analysis_state()
        self.assertTrue(state["enabled"])
        self.assertAlmostEqual(state["analysis"]["root_winrate"], 0.55)
        self.assertEqual(state["analysis"]["moves"][0]["vertex"], "D4")
        self.assertEqual(state["analysis"]["key"], state["current_key"])

    def test_move_invalidates_and_reanalyzes(self):
        self.wg.dispatch("analysis", {"enabled": True})
        self.assertTrue(wait_for(lambda: self.analyzer.calls >= 1))
        first_key = self.wg.analysis_state()["current_key"]
        self.wg.dispatch("move", {"vertex": "D4"})
        self.assertTrue(wait_for(lambda: self.wg.analysis_state()["current_key"] != first_key))
        self.assertTrue(wait_for(lambda: self.analyzer.calls >= 2))
        state = self.wg.analysis_state()
        self.assertEqual(state["analysis"]["key"], state["current_key"])

    def test_disable_stops_polling(self):
        self.wg.dispatch("analysis", {"enabled": True})
        self.assertTrue(wait_for(lambda: self.analyzer.calls >= 1))
        self.wg.dispatch("analysis", {"enabled": False})
        self.assertFalse(self.wg.analysis_state()["enabled"])


class HttpAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.analyzer = FakeAnalyzer()
        self.wg = web.WebGame(
            record_dir=self.tmp.name,
            engine=FakeEngine(),
            analyzer=self.analyzer,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(self.wg))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.wg.close()
        self.tmp.cleanup()

    def post(self, path, payload):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.load(urllib.request.urlopen(request))

    def get(self, path):
        return json.load(urllib.request.urlopen(self.base + path))

    def test_toggle_and_fetch_analysis(self):
        state = self.post("/api/analysis", {"enabled": True})
        self.assertTrue(state["analysis_available"])
        self.assertTrue(state["analysis_enabled"])
        self.assertTrue(
            wait_for(lambda: self.get("/api/analysis")["analysis"] is not None)
        )
        analysis = self.get("/api/analysis")
        self.assertEqual(analysis["analysis"]["moves"][0]["vertex"], "D4")
        self.assertEqual(analysis["analysis"]["key"], analysis["current_key"])

    def test_page_contains_analysis_ui(self):
        html = urllib.request.urlopen(self.base + "/").read().decode("utf-8")
        self.assertIn('id="b-analysis"', html)
        self.assertIn('id="analysis-summary"', html)
        self.assertIn("/api/analysis", html)


if __name__ == "__main__":
    unittest.main()
