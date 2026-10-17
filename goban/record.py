from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from .board import BLACK, EMPTY, KO_RULE_LABELS, PASS, WHITE, Board, format_vertex
from .game import Game
from .sgf import SGFNode, index_to_sgf, parse_sgf, sgf_to_index, serialize_sgf

APP_NAME = "local-go:goban:0.1"
DEFAULT_RECORD_DIR = Path(__file__).resolve().parent.parent / "records"
SAVE_FORMATS = ("sgf", "txt")
DEFAULT_FORMAT = "sgf"
META_KEYS = [
    "PB",
    "PW",
    "BR",
    "WR",
    "DT",
    "EV",
    "RO",
    "PC",
    "RU",
    "RE",
    "KM",
    "SZ",
    "HA",
    "GN",
    "GC",
    "AP",
]


def _parse_size(value: str) -> int:
    return int(str(value).split(":")[0])


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("_")
    return cleaned or "Player"


_METADATA_SKIP = ("SZ", "KM", "AP", "RE")


def merge_record_metadata(metadata: dict, record) -> None:
    for key, value in record.metadata().items():
        if key in _METADATA_SKIP:
            continue
        metadata.setdefault(key, value)


def default_record_dir() -> Path:
    return DEFAULT_RECORD_DIR


def default_filename(metadata: dict | None = None, when: datetime | None = None,
                     fmt: str = DEFAULT_FORMAT) -> str:
    metadata = metadata or {}
    when = when or datetime.now()
    black = _sanitize(metadata.get("PB") or "Black")
    white = _sanitize(metadata.get("PW") or "White")
    return f"{when:%Y%m%d-%H%M%S}_{black}_vs_{white}.{fmt}"


def record_format(name, default: str = DEFAULT_FORMAT) -> str:
    suffix = Path(name).suffix.lstrip(".").lower()
    return suffix or default


def resolve_write_path(name: str, directory=None, default_format: str = DEFAULT_FORMAT) -> Path:
    directory = Path(directory) if directory is not None else default_record_dir()
    path = Path(name)
    if path.suffix == "":
        path = path.with_suffix(f".{default_format}")
    if path.is_absolute() or path.parent != Path("."):
        return path
    return directory / path.name


def resolve_read_path(name: str, directory=None) -> Path:
    directory = Path(directory) if directory is not None else default_record_dir()
    path = Path(name)
    if path.is_absolute() or path.parent != Path("."):
        return path
    candidate = directory / path.name
    if candidate.exists():
        return candidate
    return path


def _result_code(game: Game) -> str:
    if game.resigned_by is not None:
        winner = "W" if game.resigned_by == BLACK else "B"
        return f"{winner}+R"
    if game.board.no_result:
        return "Void"
    black, white = game.score()
    if black > white:
        return f"B+{black - white:.1f}"
    if white > black:
        return f"W+{white - black:.1f}"
    return "0"


class GameRecord:
    def __init__(self, root: SGFNode, size: int | None = None, komi: float | None = None):
        self.root = root
        self.size = _parse_size(size if size is not None else root.get("SZ", "19"))
        self.komi = float(komi if komi is not None else root.get("KM", "0"))

    def metadata(self) -> dict[str, str]:
        return {key: self.root.get(key) for key in META_KEYS if self.root.has(key)}

    def main_line(self) -> list[SGFNode]:
        nodes = []
        node = self.root
        while node.children:
            node = node.children[0]
            nodes.append(node)
        return nodes

    def moves(self) -> list[tuple[int, int]]:
        moves = []
        for node in self.main_line():
            if node.has("B"):
                moves.append((BLACK, sgf_to_index(node.get("B", ""), self.size)))
            elif node.has("W"):
                moves.append((WHITE, sgf_to_index(node.get("W", ""), self.size)))
        return moves

    def _apply_setup(self, board: Board, node: SGFNode) -> None:
        changed = False
        for ident, color in (("AB", BLACK), ("AW", WHITE)):
            for value in node.get_all(ident):
                board.grid[sgf_to_index(value, self.size)] = color
                changed = True
        for value in node.get_all("AE"):
            board.grid[sgf_to_index(value, self.size)] = EMPTY
            changed = True
        if changed:
            board.reset_positions()
        if node.has("PL"):
            board.to_play = BLACK if node.get("PL") == "B" else WHITE

    def _do_move(self, board: Board, color: int, idx: int) -> None:
        board.to_play = color
        if idx == PASS:
            board.pass_move()
        else:
            board.play_unchecked(idx)

    def steps(self) -> list[dict]:
        board = Board(self.size, self.komi)
        self._apply_setup(board, self.root)
        steps = [
            {
                "grid": list(board.grid),
                "to_play": board.to_play,
                "color": None,
                "idx": None,
                "number": 0,
                "comment": self.root.get("C"),
            }
        ]
        number = 0
        for node in self.main_line():
            self._apply_setup(board, node)
            color = None
            idx = None
            if node.has("B"):
                color, idx = BLACK, sgf_to_index(node.get("B", ""), self.size)
            elif node.has("W"):
                color, idx = WHITE, sgf_to_index(node.get("W", ""), self.size)
            if color is None:
                if steps:
                    steps[-1]["grid"] = list(board.grid)
                    steps[-1]["to_play"] = board.to_play
                continue
            number += 1
            self._do_move(board, color, idx)
            steps.append(
                {
                    "grid": list(board.grid),
                    "to_play": board.to_play,
                    "color": color,
                    "idx": idx,
                    "number": number,
                    "comment": node.get("C"),
                }
            )
        return steps

    def to_game(self) -> Game:
        game = Game(self.size, self.komi)
        self._apply_setup(game.board, self.root)
        for node in self.main_line():
            self._apply_setup(game.board, node)
            if node.has("B"):
                color, idx = BLACK, sgf_to_index(node.get("B", ""), self.size)
            elif node.has("W"):
                color, idx = WHITE, sgf_to_index(node.get("W", ""), self.size)
            else:
                continue
            self._do_move(game.board, color, idx)
            game.moves.append((color, idx))
        return game

    def info(self) -> str:
        lines = [f"{key}: {value}" for key, value in self.metadata().items()]
        moves = self.moves()
        passes = sum(1 for _, idx in moves if idx == PASS)
        lines.append(f"moves: {len(moves) - passes}  passes: {passes}")
        return "\n".join(lines)

    def to_sgf(self) -> str:
        return serialize_sgf(self.root)

    def to_text(self) -> str:
        lines = ["# 围棋棋谱"]
        for key, value in self.metadata().items():
            lines.append(f"{key}: {value}")
        lines.append("")
        lines.append("moves:")
        for number, (color, idx) in enumerate(self.moves(), 1):
            vertex = "pass" if idx == PASS else format_vertex(idx, self.size)
            lines.append(f"  {number}. {'B' if color == BLACK else 'W'} {vertex}")
        return "\n".join(lines) + "\n"

    def serialize(self, fmt: str | None = None) -> str:
        fmt = (fmt or DEFAULT_FORMAT).lower()
        if fmt not in SAVE_FORMATS:
            supported = ", ".join("." + f for f in SAVE_FORMATS)
            raise ValueError(f"unsupported format: .{fmt} (supported: {supported})")
        if fmt == "txt":
            return self.to_text()
        return self.to_sgf()

    def save(self, path, fmt: str | None = None) -> None:
        path = Path(path)
        text = self.serialize(fmt or record_format(path))
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    @classmethod
    def from_sgf(cls, text: str, index: int = 0) -> "GameRecord":
        trees = parse_sgf(text)
        if not trees:
            raise ValueError("no game tree found in SGF")
        root = trees[index]
        return cls(root)

    @classmethod
    def load(cls, path: str, index: int = 0) -> "GameRecord":
        with open(path, encoding="utf-8") as handle:
            return cls.from_sgf(handle.read(), index)

    @classmethod
    def from_game(cls, game: Game, metadata: dict | None = None) -> "GameRecord":
        metadata = dict(metadata or {})
        root = SGFNode()
        root.set("GM", "1")
        root.set("FF", "4")
        root.set("CA", "UTF-8")
        root.set("AP", APP_NAME)
        root.set("SZ", str(game.board.size))
        root.set("KM", str(game.board.komi))
        if not metadata.get("RE") and game.over:
            metadata["RE"] = _result_code(game)
        if not metadata.get("DT"):
            metadata["DT"] = date.today().isoformat()
        if not metadata.get("RU"):
            metadata["RU"] = KO_RULE_LABELS.get(game.board.ko_rule, "Chinese")
        for key, value in metadata.items():
            root.set(key, str(value))
        parent = root
        for color, idx in game.moves:
            node = SGFNode()
            node.set("B" if color == BLACK else "W", index_to_sgf(idx, game.board.size))
            parent.children.append(node)
            parent = node
        dead = getattr(game, "dead", None)
        if dead:
            node = SGFNode()
            node.set("AE", *[index_to_sgf(i, game.board.size) for i in sorted(dead)])
            parent.children.append(node)
        return cls(root, game.board.size, game.board.komi)
