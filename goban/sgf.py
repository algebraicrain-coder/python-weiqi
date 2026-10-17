from __future__ import annotations

from .board import PASS

UPPER = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
LOWER = frozenset("abcdefghijklmnopqrstuvwxyz")


class SGFError(Exception):
    pass


class SGFNode:
    __slots__ = ("properties", "children")

    def __init__(self):
        self.properties: dict[str, list[str]] = {}
        self.children: list["SGFNode"] = []

    def get(self, ident: str, default=None):
        values = self.properties.get(ident)
        return values[0] if values else default

    def get_all(self, ident: str) -> list[str]:
        return list(self.properties.get(ident, []))

    def has(self, ident: str) -> bool:
        return ident in self.properties

    def set(self, ident: str, *values: str) -> None:
        self.properties[ident] = list(values)

    def add(self, ident: str, value: str) -> None:
        self.properties.setdefault(ident, []).append(value)

    def __repr__(self) -> str:
        return f"SGFNode({self.properties!r}, children={len(self.children)})"


def sgf_to_index(value: str, size: int) -> int:
    if value == "":
        return PASS
    if len(value) != 2 or value[0] not in LOWER or value[1] not in LOWER:
        raise SGFError(f"bad point: {value!r}")
    col = ord(value[0]) - ord("a")
    row = ord(value[1]) - ord("a")
    if not (0 <= col < size and 0 <= row < size):
        raise SGFError(f"point out of range: {value!r}")
    return (size - 1 - row) * size + col


def index_to_sgf(idx: int, size: int) -> str:
    if idx == PASS:
        return ""
    x = idx % size
    y = idx // size
    return chr(ord("a") + x) + chr(ord("a") + (size - 1 - y))


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def parse_collection(self) -> list[SGFNode]:
        trees = []
        while True:
            self._skip_ws()
            if self.pos >= self.length:
                break
            if self.text[self.pos] != "(":
                raise SGFError(f"expected '(' at offset {self.pos}")
            trees.append(self._parse_game_tree())
        return trees

    def _parse_game_tree(self) -> SGFNode:
        if self.text[self.pos] != "(":
            raise SGFError(f"expected '(' at offset {self.pos}")
        self.pos += 1
        first, last = self._parse_sequence()
        while True:
            self._skip_ws()
            if self.pos < self.length and self.text[self.pos] == "(":
                last.children.append(self._parse_game_tree())
            else:
                break
        self._skip_ws()
        if self.pos >= self.length or self.text[self.pos] != ")":
            raise SGFError(f"expected ')' at offset {self.pos}")
        self.pos += 1
        return first

    def _parse_sequence(self):
        nodes = []
        while True:
            self._skip_ws()
            if self.pos < self.length and self.text[self.pos] == ";":
                nodes.append(self._parse_node())
            else:
                break
        if not nodes:
            raise SGFError("empty sequence")
        for parent, child in zip(nodes, nodes[1:]):
            parent.children.append(child)
        return nodes[0], nodes[-1]

    def _parse_node(self) -> SGFNode:
        self.pos += 1
        node = SGFNode()
        while True:
            self._skip_ws()
            if self.pos >= self.length:
                break
            if self.text[self.pos] not in UPPER:
                break
            ident = self._parse_ident()
            values = []
            while True:
                self._skip_ws()
                if self.pos < self.length and self.text[self.pos] == "[":
                    values.append(self._parse_value())
                else:
                    break
            node.properties.setdefault(ident, []).extend(values)
        return node

    def _parse_ident(self) -> str:
        start = self.pos
        while self.pos < self.length and self.text[self.pos] in UPPER:
            self.pos += 1
        return self.text[start : self.pos]

    def _parse_value(self) -> str:
        self.pos += 1
        out = []
        while self.pos < self.length:
            ch = self.text[self.pos]
            if ch == "\\":
                self.pos += 1
                if self.pos < self.length:
                    out.append(self.text[self.pos])
                    self.pos += 1
                continue
            if ch == "]":
                self.pos += 1
                return "".join(out)
            out.append(ch)
            self.pos += 1
        raise SGFError("unterminated property value")

    def _skip_ws(self) -> None:
        while self.pos < self.length and self.text[self.pos].isspace():
            self.pos += 1


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("]", "\\]")


def _node_to_sgf(node: SGFNode) -> str:
    parts = [";"]
    for ident, values in node.properties.items():
        parts.append(ident)
        if not values:
            parts.append("[]")
            continue
        for value in values:
            parts.append("[" + _escape(value) + "]")
    return "".join(parts)


def serialize_sgf(node: SGFNode) -> str:
    out = ["("]
    while True:
        out.append(_node_to_sgf(node))
        if len(node.children) == 1:
            node = node.children[0]
            continue
        break
    for child in node.children:
        out.append(serialize_sgf(child))
    out.append(")")
    return "".join(out)


def parse_sgf(text: str) -> list[SGFNode]:
    return _Parser(text).parse_collection()
