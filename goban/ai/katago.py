from __future__ import annotations

import atexit
import queue
import subprocess
import threading

from ..board import (
    BLACK,
    PASS,
    WHITE,
    format_vertex,
    parse_vertex,
)
from ..player import RESIGN
from .base import EngineError, EngineUnavailable, Position
from .config import AIConfig

# 本项目的劫规则 -> KataGo 的 shorthand。
# 注意：KataGo 的 chinese 是“简单劫 + 数子”，chinese-ogs 才是位置超级劫。
KATAGO_RULES = {
    "chinese": "chinese-ogs",
    "simple": "chinese",
    "situational": "aga",
    "japanese": "japanese",
}


class KataGoGTP:
    """通过 GTP 文本协议驱动本机 KataGo 的极简客户端。"""

    name = "KataGo"

    def __init__(self, config: AIConfig):
        self.config = config
        self._proc: subprocess.Popen | None = None
        self._queue: queue.Queue | None = None
        self._stderr: list[str] = []
        self._lock = threading.RLock()
        atexit.register(self.close)

    def available(self) -> bool:
        return self.config.available()

    def unavailable_reason(self) -> str:
        return self.config.missing_reason()

    def _start_locked(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if not self.available():
            raise EngineUnavailable(self.config.missing_reason())
        command = [
            self.config.binary_path(),
            "gtp",
            "-model",
            self.config.model,
        ]
        if self.config.gtp_config:
            command.extend(["-config", self.config.gtp_config])
        self._stderr = []
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._queue = queue.Queue()
        threading.Thread(
            target=self._read_stdout,
            args=(self._proc, self._queue),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr,
            args=(self._proc,),
            daemon=True,
        ).start()

    def _read_stdout(self, proc: subprocess.Popen, output: queue.Queue) -> None:
        try:
            for line in proc.stdout:
                output.put(line)
        except (OSError, ValueError) as error:
            output.put(error)
        finally:
            output.put(None)

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stderr:
                self._stderr.append(line.rstrip())
                if len(self._stderr) > 40:
                    del self._stderr[:-40]
        except (OSError, ValueError):
            pass

    def _kill_locked(self) -> None:
        proc = self._proc
        self._proc = None
        self._queue = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            self._close_pipes(proc)

    @staticmethod
    def _close_pipes(proc: subprocess.Popen) -> None:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _read_response_locked(self) -> str:
        output = self._queue
        if output is None:
            raise EngineError("KataGo 尚未启动")
        lines = []
        while True:
            try:
                item = output.get(timeout=self.config.timeout)
            except queue.Empty:
                self._kill_locked()
                raise EngineError(f"KataGo 响应超时（{self.config.timeout:g}s）")
            if item is None:
                tail = " | ".join(self._stderr[-4:])
                self._kill_locked()
                raise EngineError("KataGo 已退出" + (f"：{tail}" if tail else ""))
            if isinstance(item, Exception):
                self._kill_locked()
                raise EngineError(f"读取 KataGo 输出失败：{item}")
            line = item.rstrip("\r\n")
            if line == "":
                break
            lines.append(line)
        if not lines:
            return ""
        first = lines[0]
        if first.startswith("?"):
            raise EngineError("KataGo 返回错误：" + first[1:].strip())
        if first.startswith("="):
            first = first[1:].lstrip()
        return "\n".join([first, *lines[1:]]).strip()

    def _command_locked(self, command: str) -> str:
        if self._proc is None or self._proc.poll() is not None:
            self._start_locked()
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise EngineError("KataGo 进程不可用")
        try:
            proc.stdin.write(command + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            self._kill_locked()
            raise EngineError(f"无法写入 KataGo：{error}") from error
        return self._read_response_locked()

    def command(self, text: str) -> str:
        with self._lock:
            return self._command_locked(text)

    @staticmethod
    def _has_setup(position: Position) -> bool:
        return position.has_setup()

    def genmove(self, position: Position) -> int:
        with self._lock:
            self._command_locked(f"boardsize {position.size}")
            self._command_locked(f"komi {position.komi:g}")
            rule = KATAGO_RULES.get(position.ko_rule)
            if rule:
                try:
                    self._command_locked(f"kata-set-rules {rule}")
                except EngineError:
                    # 旧网络可能不支持某些规则组合，退回最接近的通用规则。
                    self._command_locked("kata-set-rules chinese")
            if self.config.max_visits > 0:
                self._command_locked(f"kata-set-param maxVisits {int(self.config.max_visits)}")
            if self.config.max_time is not None and self.config.max_time > 0:
                self._command_locked(f"kata-set-param maxTime {self.config.max_time:g}")
            if self._has_setup(position):
                # set_position 不保留手顺/劫，但能正确还原带摆子的 SGF。
                stones = []
                for idx, color in enumerate(position.grid):
                    if color == BLACK:
                        stones.append(f"B {format_vertex(idx, position.size)}")
                    elif color == WHITE:
                        stones.append(f"W {format_vertex(idx, position.size)}")
                if stones:
                    self._command_locked("set_position " + " ".join(stones))
                else:
                    self._command_locked("clear_board")
            else:
                self._command_locked("clear_board")
                for color, move in position.moves:
                    player = "B" if color == BLACK else "W"
                    vertex = "pass" if move == PASS else format_vertex(move, position.size)
                    self._command_locked(f"play {player} {vertex}")
            player = "B" if position.to_play == BLACK else "W"
            response = self._command_locked(f"genmove {player}")
        return self._parse_move(response, position.size)

    @staticmethod
    def _parse_move(text: str, size: int) -> int:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise EngineError("KataGo 没有返回落子")
        move = lines[-1]
        if move.startswith("="):
            move = move[1:].strip()
        lowered = move.lower()
        if lowered == "pass":
            return PASS
        if lowered == "resign":
            return RESIGN
        try:
            return parse_vertex(move, size)
        except ValueError as error:
            raise EngineError(f"KataGo 返回了无法识别的落子：{move!r}") from error

    def close(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            self._queue = None
            if proc is None:
                return
            try:
                if proc.poll() is None and proc.stdin is not None:
                    proc.stdin.write("quit\n")
                    proc.stdin.flush()
                    proc.wait(timeout=2)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                try:
                    if proc.poll() is None:
                        proc.kill()
                except OSError:
                    pass
            finally:
                try:
                    proc.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                self._close_pipes(proc)
