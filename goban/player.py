from __future__ import annotations

RESIGN = -2


class Command(Exception):
    def __init__(self, command: str, argument: str | None = None):
        super().__init__(command)
        self.command = command
        self.argument = argument


class Player:
    def __init__(self, name: str = "Player"):
        self.name = name

    def choose_move(self, game) -> int:
        raise NotImplementedError


class HumanPlayer(Player):
    def __init__(self, name: str, move_source):
        super().__init__(name)
        self.move_source = move_source

    def choose_move(self, game) -> int:
        return self.move_source(game)
