from __future__ import annotations

from .board import (
    BLACK,
    EMPTY,
    KO_CHINESE,
    PASS,
    WHITE,
    Board,
    IllegalMove,
    color_name,
)


class GameOver(Exception):
    pass


class Game:
    def __init__(self, size: int = 19, komi: float = 7.5, ko_rule: str = KO_CHINESE):
        self.board = Board(size, komi, ko_rule)
        self.moves: list[tuple[int, int]] = []
        self.resigned_by: int | None = None
        self.dead: set[int] = set()

    @property
    def passes(self) -> int:
        count = 0
        for _, move in reversed(self.moves):
            if move == PASS:
                count += 1
            else:
                break
        return count

    @property
    def over(self) -> bool:
        return (
            self.resigned_by is not None
            or self.passes >= 2
            or self.board.no_result
        )

    @property
    def last_move(self) -> int | None:
        if not self.moves:
            return None
        _, move = self.moves[-1]
        return None if move == PASS else move

    def play(self, idx: int) -> int:
        if self.over:
            raise GameOver("game is already over")
        color = self.board.to_play
        captured = self.board.play(idx)
        self.moves.append((color, idx))
        return captured

    def pass_move(self) -> None:
        if self.over:
            raise GameOver("game is already over")
        color = self.board.to_play
        self.board.pass_move()
        self.moves.append((color, PASS))

    def resign(self) -> None:
        if self.over:
            raise GameOver("game is already over")
        self.resigned_by = self.board.to_play

    def undo(self) -> None:
        if not self.moves:
            raise IllegalMove("no move to undo")
        self.board.undo()
        self.moves.pop()
        self.dead.clear()

    def toggle_dead(self, idx: int) -> int:
        if self.board.grid[idx] == EMPTY:
            return 0
        group, _ = self.board.group_and_liberties(idx)
        if group <= self.dead:
            self.dead -= group
        else:
            self.dead |= group
        return len(group)

    def score(self) -> tuple[float, float]:
        return self.board.score(self.dead)

    def result(self) -> dict:
        if self.resigned_by is not None:
            winner = WHITE if self.resigned_by == BLACK else BLACK
            return {"winner": winner, "reason": "resign", "margin": None, "score": None}
        if self.board.no_result:
            return {"winner": None, "reason": "no-result", "margin": None, "score": None}
        black, white = self.score()
        winner = BLACK if black > white else WHITE
        return {
            "winner": winner,
            "reason": "score",
            "margin": abs(black - white),
            "score": (black, white),
        }

    def result_text(self) -> str:
        if self.resigned_by is not None:
            winner = WHITE if self.resigned_by == BLACK else BLACK
            return f"{color_name(winner)} wins by resignation"
        if self.board.no_result:
            return "No result (position repeated)"
        black, white = self.score()
        if black > white:
            return f"Black wins by {black - white:.1f} points"
        if white > black:
            return f"White wins by {white - black:.1f} points"
        return "Draw"
