from __future__ import annotations

EMPTY = 0
BLACK = 1
WHITE = 2
PASS = -1
OPPONENT = {BLACK: WHITE, WHITE: BLACK}

COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

KO_CHINESE = "chinese"
KO_SIMPLE = "simple"
KO_SITUATIONAL = "situational"
KO_JAPANESE = "japanese"
KO_RULES = (KO_CHINESE, KO_SIMPLE, KO_SITUATIONAL, KO_JAPANESE)
KO_RULE_LABELS = {
    KO_CHINESE: "Chinese (positional superko)",
    KO_SIMPLE: "Simple ko",
    KO_SITUATIONAL: "Situational superko",
    KO_JAPANESE: "Japanese (simple ko + no result)",
}


class IllegalMove(Exception):
    pass


def color_name(color: int) -> str:
    return {BLACK: "Black", WHITE: "White", EMPTY: "Empty"}[color]


def parse_vertex(text: str, size: int) -> int:
    text = text.strip().upper()
    if not text:
        raise ValueError("empty vertex")
    letter = text[0]
    digits = text[1:]
    if letter not in COLUMNS[:size] or not digits.isdigit():
        raise ValueError(f"bad vertex: {text!r}")
    x = COLUMNS.index(letter)
    y = int(digits) - 1
    if not 0 <= y < size:
        raise ValueError(f"vertex out of range: {text!r}")
    return y * size + x


def format_vertex(idx: int, size: int) -> str:
    x = idx % size
    y = idx // size
    return f"{COLUMNS[x]}{y + 1}"


class Board:
    def __init__(self, size: int = 19, komi: float = 7.5, ko_rule: str = KO_CHINESE):
        if not 2 <= size <= len(COLUMNS):
            raise ValueError("board size must be between 2 and 25")
        if ko_rule not in KO_RULES:
            raise ValueError(f"unknown ko rule: {ko_rule!r}")
        self.size = size
        self.komi = komi
        self.ko_rule = ko_rule
        self.grid: list[int] = [EMPTY] * (size * size)
        self.to_play = BLACK
        self.captures = {BLACK: 0, WHITE: 0}
        self.no_result = False
        self._history: list[dict] = []
        self._positions_grid: set[tuple[int, ...]] = {tuple(self.grid)}
        self._positions_turn: set[tuple[tuple[int, ...], int]] = {(tuple(self.grid), BLACK)}

    def clone(self) -> "Board":
        other = Board(self.size, self.komi, self.ko_rule)
        other.grid = self.grid.copy()
        other.to_play = self.to_play
        other.captures = dict(self.captures)
        other.no_result = self.no_result
        other._history = [dict(entry) for entry in self._history]
        other._positions_grid = set(self._positions_grid)
        other._positions_turn = set(self._positions_turn)
        return other

    def index(self, x: int, y: int) -> int:
        return y * self.size + x

    def coord(self, idx: int) -> tuple[int, int]:
        return idx % self.size, idx // self.size

    def on_board(self, idx: int) -> bool:
        return 0 <= idx < len(self.grid)

    def neighbors(self, idx: int) -> list[int]:
        x, y = self.coord(idx)
        out = []
        if x > 0:
            out.append(idx - 1)
        if x < self.size - 1:
            out.append(idx + 1)
        if y > 0:
            out.append(idx - self.size)
        if y < self.size - 1:
            out.append(idx + self.size)
        return out

    def group_and_liberties(self, idx: int, grid: list[int] | None = None):
        grid = self.grid if grid is None else grid
        color = grid[idx]
        group = {idx}
        liberties: set[int] = set()
        stack = [idx]
        while stack:
            cur = stack.pop()
            for n in self.neighbors(cur):
                if grid[n] == EMPTY:
                    liberties.add(n)
                elif grid[n] == color and n not in group:
                    group.add(n)
                    stack.append(n)
        return group, liberties

    def _result_position(self, idx: int, color: int):
        grid = self.grid.copy()
        grid[idx] = color
        captured = 0
        for n in self.neighbors(idx):
            if grid[n] == OPPONENT[color]:
                group, liberties = self.group_and_liberties(n, grid)
                if not liberties:
                    for stone in group:
                        grid[stone] = EMPTY
                    captured += len(group)
        _, liberties = self.group_and_liberties(idx, grid)
        if not liberties:
            return None, 0
        return grid, captured

    def _legal_ko(self, grid: list[int]) -> bool:
        key = tuple(grid)
        if self.ko_rule in (KO_SIMPLE, KO_JAPANESE):
            return not (self._history and key == self._history[-1]["grid"])
        if self.ko_rule == KO_SITUATIONAL:
            return (key, OPPONENT[self.to_play]) not in self._positions_turn
        return key not in self._positions_grid

    def is_legal(self, idx: int) -> bool:
        if not self.on_board(idx) or self.grid[idx] != EMPTY:
            return False
        grid, _ = self._result_position(idx, self.to_play)
        if grid is None:
            return False
        return self._legal_ko(grid)

    def legal_moves(self) -> list[int]:
        return [i for i in range(len(self.grid)) if self.is_legal(i)]

    def _record_position(self, to_play_next: int, prev_grid: list[int] | tuple) -> None:
        key = tuple(self.grid)
        turn_key = (key, to_play_next)
        if (
            self.ko_rule == KO_JAPANESE
            and turn_key in self._positions_turn
            and key != tuple(prev_grid)
        ):
            self.no_result = True
        self._positions_grid.add(key)
        self._positions_turn.add(turn_key)

    def play(self, idx: int) -> int:
        if not self.is_legal(idx):
            raise IllegalMove(f"illegal move at {idx}")
        color = self.to_play
        grid, captured = self._result_position(idx, color)
        self._history.append(
            {
                "grid": tuple(self.grid),
                "to_play": self.to_play,
                "captures": dict(self.captures),
            }
        )
        prev_grid = self.grid
        self.grid = grid
        self.captures[color] += captured
        self.to_play = OPPONENT[color]
        self._record_position(self.to_play, prev_grid)
        return captured

    def play_unchecked(self, idx: int) -> int:
        color = self.to_play
        grid, captured = self._result_position(idx, color)
        if grid is None:
            grid = self.grid.copy()
            grid[idx] = color
            captured = 0
        self._history.append(
            {
                "grid": tuple(self.grid),
                "to_play": self.to_play,
                "captures": dict(self.captures),
            }
        )
        prev_grid = self.grid
        self.grid = grid
        self.captures[color] += captured
        self.to_play = OPPONENT[color]
        self._record_position(self.to_play, prev_grid)
        return captured

    def place_stone(self, idx: int, color: int) -> None:
        self.grid[idx] = color

    def reset_positions(self) -> None:
        key = tuple(self.grid)
        self._positions_grid = {key}
        self._positions_turn = {(key, self.to_play)}

    def pass_move(self) -> None:
        self._history.append(
            {
                "grid": tuple(self.grid),
                "to_play": self.to_play,
                "captures": dict(self.captures),
            }
        )
        prev_grid = self.grid
        self.to_play = OPPONENT[self.to_play]
        self._record_position(self.to_play, prev_grid)

    def undo(self) -> None:
        if not self._history:
            raise IllegalMove("no move to undo")
        state = self._history.pop()
        self.grid = list(state["grid"])
        self.to_play = state["to_play"]
        self.captures = dict(state["captures"])
        self.no_result = False
        self._positions_grid = {entry["grid"] for entry in self._history}
        self._positions_grid.add(tuple(self.grid))
        self._positions_turn = {
            (entry["grid"], entry["to_play"]) for entry in self._history
        }
        self._positions_turn.add((tuple(self.grid), self.to_play))

    def score(self, dead=None) -> tuple[float, float]:
        grid = self.grid
        if dead:
            grid = self.grid.copy()
            for idx in dead:
                grid[idx] = EMPTY
        visited = [False] * len(grid)
        black = sum(1 for c in grid if c == BLACK)
        white = sum(1 for c in grid if c == WHITE)
        for start in range(len(grid)):
            if grid[start] != EMPTY or visited[start]:
                continue
            visited[start] = True
            stack = [start]
            region = []
            border: set[int] = set()
            while stack:
                cur = stack.pop()
                region.append(cur)
                for n in self.neighbors(cur):
                    if grid[n] == EMPTY:
                        if not visited[n]:
                            visited[n] = True
                            stack.append(n)
                    else:
                        border.add(grid[n])
            if border == {BLACK}:
                black += len(region)
            elif border == {WHITE}:
                white += len(region)
        return float(black), float(white) + self.komi
