import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from goban.ai import (
    AIConfig,
    EngineError,
    EnginePlayer,
    EngineUnavailable,
    KATAGO_RULES,
    KataGoGTP,
    Position,
    discover_config,
)
from goban.board import BLACK, PASS, WHITE, format_vertex, parse_vertex
from goban.game import Game
from goban.player import RESIGN


FAKE_ENGINE = """#!/usr/bin/env python3
import sys
for raw in sys.stdin:
    command = raw.strip()
    if command == "quit":
        print("=")
        print()
        sys.stdout.flush()
        break
    if command.startswith("genmove"):
        print("= D4")
    else:
        print("=")
    print()
    sys.stdout.flush()
"""

SLOW_ENGINE = """#!/usr/bin/env python3
import sys
import time
for raw in sys.stdin:
    command = raw.strip()
    if command.startswith("genmove"):
        time.sleep(5)
    print("=")
    print()
    sys.stdout.flush()
"""


class AITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.model = self.root / "model.bin.gz"
        self.model.write_bytes(b"fake")

    def tearDown(self):
        self.tmp.cleanup()

    def make_script(self, text: str, name: str = "fake_katago.py") -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
        return path

    def config(self, script: Path, timeout: float = 3.0) -> AIConfig:
        return AIConfig(
            binary=str(script),
            model=str(self.model),
            max_visits=100,
            timeout=timeout,
        )

    def test_position_snapshot(self):
        game = Game(9)
        game.play(parse_vertex("D4", 9))
        game.pass_move()
        position = Position.from_game(game)
        self.assertEqual(position.size, 9)
        self.assertEqual(position.to_play, BLACK)
        self.assertEqual(position.moves[0], (BLACK, parse_vertex("D4", 9)))
        self.assertEqual(position.moves[1], (WHITE, PASS))

    def test_setup_stones_detection(self):
        game = Game(9)
        game.play(parse_vertex("D4", 9))
        self.assertFalse(KataGoGTP._has_setup(Position.from_game(game)))

        grid = [0] * 81
        grid[40] = BLACK  # E5
        position = Position(9, 7.5, "chinese", (), BLACK, tuple(grid))
        self.assertTrue(KataGoGTP._has_setup(position))

    def test_katago_rule_mapping(self):
        self.assertEqual(KATAGO_RULES["chinese"], "chinese-ogs")
        self.assertEqual(KATAGO_RULES["simple"], "chinese")
        self.assertEqual(KATAGO_RULES["situational"], "aga")
        self.assertEqual(KATAGO_RULES["japanese"], "japanese")

    def test_config_availability(self):
        script = self.make_script(FAKE_ENGINE)
        config = self.config(script)
        self.assertTrue(config.available())
        self.assertEqual(config.missing_reason(), "")

    def test_config_missing_reason(self):
        config = AIConfig(binary="", model="")
        self.assertFalse(config.available())
        self.assertIn("katago", config.missing_reason())

    def test_discover_relative_ai_json(self):
        script = self.make_script(FAKE_ENGINE)
        config_dir = self.root / "cfg"
        config_dir.mkdir()
        model = config_dir / "m.bin.gz"
        model.write_bytes(b"fake")
        (config_dir / "ai.json").write_text(
            json.dumps(
                {
                    "binary": os.path.relpath(script, config_dir),
                    "model": model.name,
                    "max_visits": 42,
                    "timeout": 7,
                }
            ),
            encoding="utf-8",
        )
        config = discover_config(config_path=config_dir / "ai.json")
        self.assertIsNotNone(config)
        self.assertEqual(Path(config.binary).resolve(), script.resolve())
        self.assertEqual(Path(config.model).resolve(), model.resolve())
        self.assertEqual(config.max_visits, 42)
        self.assertEqual(config.timeout, 7)

    def test_genmove_parses_vertex(self):
        script = self.make_script(FAKE_ENGINE)
        engine = KataGoGTP(self.config(script))
        try:
            move = engine.genmove(Position(9, 7.5, "chinese", (), BLACK))
        finally:
            engine.close()
        self.assertEqual(move, parse_vertex("D4", 9))

    def test_parse_special_moves(self):
        self.assertEqual(KataGoGTP._parse_move("= pass", 9), PASS)
        self.assertEqual(KataGoGTP._parse_move("= resign", 9), RESIGN)
        self.assertEqual(
            KataGoGTP._parse_move("= " + format_vertex(parse_vertex("Q16", 19), 19), 19),
            parse_vertex("Q16", 19),
        )
        with self.assertRaises(EngineError):
            KataGoGTP._parse_move("= nowhere", 9)

    def test_engine_unavailable(self):
        config = AIConfig(binary=str(self.root / "missing"), model=str(self.model))
        engine = KataGoGTP(config)
        with self.assertRaises(EngineUnavailable):
            engine.genmove(Position(9, 7.5, "chinese", (), BLACK))
        engine.close()

    def test_timeout_kills_process(self):
        script = self.make_script(SLOW_ENGINE, "slow_katago.py")
        engine = KataGoGTP(self.config(script, timeout=0.3))
        started = time.monotonic()
        with self.assertRaises(EngineError):
            engine.genmove(Position(9, 7.5, "chinese", (), BLACK))
        self.assertLess(time.monotonic() - started, 3.0)
        engine.close()

    def test_engine_player_uses_snapshot(self):
        class FakeEngine:
            name = "Fake"

            def __init__(self):
                self.seen = None

            def available(self):
                return True

            def genmove(self, position):
                self.seen = position
                return PASS

            def close(self):
                pass

        game = Game(9)
        game.play(parse_vertex("D4", 9))
        engine = FakeEngine()
        player = EnginePlayer("Fake", engine)
        self.assertEqual(player.choose_move(game), PASS)
        self.assertEqual(engine.seen.moves, ((BLACK, parse_vertex("D4", 9)),))
        self.assertEqual(engine.seen.to_play, WHITE)


if __name__ == "__main__":
    unittest.main()
