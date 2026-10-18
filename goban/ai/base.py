from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ..board import BLACK, PASS
from ..player import RESIGN, Player

if TYPE_CHECKING:
    from ..game import Game


class EngineError(RuntimeError):
    """AI 引擎运行出错（进程退出、超时、协议错误等）。"""


class EngineUnavailable(EngineError):
    """没有找到可用的引擎或模型。"""


@dataclass(frozen=True)
class Position:
    """传给引擎的只读局面快照。

    使用快照而不是直接传 ``Game``，是为了让 Web 端可以在不持锁的情况下
    调用引擎，回来后再检查局面是否已经变化。
    """

    size: int
    komi: float
    ko_rule: str
    moves: tuple[tuple[int, int], ...]
    to_play: int
    # 当前盘面。用于识别 SGF 里的摆子（AB/AW），此时 move 重放不足以还原局面。
    grid: tuple[int, ...] = ()

    @classmethod
    def from_game(cls, game: "Game") -> "Position":
        return cls(
            size=game.board.size,
            komi=game.board.komi,
            ko_rule=game.board.ko_rule,
            moves=tuple(game.moves),
            to_play=game.board.to_play,
            grid=tuple(game.board.grid),
        )

    def key(self) -> str:
        """局面的稳定指纹，用于缓存和判断分析结果是否已过期。"""
        payload = repr((self.size, self.komi, self.ko_rule, self.moves, self.grid))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def has_setup(self) -> bool:
        """盘面是否包含 move 重放之外的摆子（SGF 的 AB/AW）。"""
        if not self.grid:
            return False
        from ..board import Board, IllegalMove

        board = Board(self.size, self.komi, self.ko_rule)
        try:
            for color, move in self.moves:
                board.to_play = color
                if move == PASS:
                    board.pass_move()
                else:
                    board.play(move)
        except IllegalMove:
            return True
        return tuple(board.grid) != self.grid


class Engine(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def genmove(self, position: Position) -> int:
        """返回内部索引、``PASS`` 或 ``RESIGN``。"""

    def close(self) -> None:
        ...


class EnginePlayer(Player):
    """把 AI 引擎包装成与 ``HumanPlayer`` 相同的玩家接口。"""

    def __init__(self, name: str, engine: Engine):
        super().__init__(name)
        self.engine = engine

    def choose_move(self, game) -> int:
        return self.engine.genmove(Position.from_game(game))
