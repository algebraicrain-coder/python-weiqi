from __future__ import annotations

import json
import queue
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..board import BLACK, PASS, WHITE, format_vertex, parse_vertex
from .base import EngineError, EngineUnavailable, Position
from .config import AIConfig
from .katago import KATAGO_RULES


class AnalysisCancelled(EngineError):
    """主动取消分析时抛出，调用方通常直接忽略。"""


@dataclass(frozen=True)
class MoveEval:
    vertex: str
    index: int | None
    visits: int
    winrate: float          # 黑方视角
    score_lead: float       # 黑方视角
    order: int
    pv: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "vertex": self.vertex,
            "index": self.index,
            "visits": self.visits,
            "winrate": self.winrate,
            "score_lead": self.score_lead,
            "order": self.order,
            "pv": list(self.pv),
        }


@dataclass(frozen=True)
class Analysis:
    key: str
    to_play: int
    root_winrate: float
    root_score_lead: float
    moves: tuple[MoveEval, ...]
    ownership: tuple[float, ...] | None
    during_search: bool

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "to_play": self.to_play,
            "root_winrate": self.root_winrate,
            "root_score_lead": self.root_score_lead,
            "moves": [move.to_dict() for move in self.moves],
            "ownership": list(self.ownership) if self.ownership is not None else None,
            "during_search": self.during_search,
        }


def _read_winrates_as(path: str) -> str:
    """从 analysis cfg 读取胜率视角；默认 KataGo 示例配置是 BLACK。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return "BLACK"
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line.startswith("reportAnalysisWinratesAs"):
            continue
        parts = line.split("=", 1)
        if len(parts) != 2:
            continue
        value = parts[1].strip().upper()
        if value in ("BLACK", "WHITE", "SIDETOMOVE"):
            return value
    return "BLACK"


_CANCELLED = object()
_EOF = object()


class KataGoAnalysis:
    """通过 ``katago analysis`` 的 JSON 协议做实时分析。"""

    name = "KataGo analysis"

    def __init__(self, config: AIConfig, winrates_as: str | None = None):
        self.config = config
        self.winrates_as = (winrates_as or _read_winrates_as(config.analysis_config)).upper()
        if self.winrates_as not in ("BLACK", "WHITE", "SIDETOMOVE"):
            self.winrates_as = "BLACK"
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._pending: dict[str, queue.Queue] = {}
        self._counter = 0
        self._stderr: list[str] = []

    def available(self) -> bool:
        return self.config.analysis_available()

    def unavailable_reason(self) -> str:
        return self.config.analysis_missing_reason()

    def _start_locked(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if not self.available():
            raise EngineUnavailable(self.config.analysis_missing_reason())
        command = [
            self.config.binary_path(),
            "analysis",
            "-model",
            self.config.model,
            "-config",
            self.config.analysis_config,
        ]
        self._stderr = []
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        threading.Thread(
            target=self._read_stdout,
            args=(self._proc,),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr,
            args=(self._proc,),
            daemon=True,
        ).start()

    def _read_stdout(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                with self._lock:
                    target = self._pending.get(str(obj.get("id", "")))
                if target is not None:
                    target.put(obj)
        except (OSError, ValueError):
            pass
        finally:
            with self._lock:
                targets = list(self._pending.values())
            for target in targets:
                target.put(_EOF)

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stderr:
                self._stderr.append(line.rstrip())
                if len(self._stderr) > 40:
                    del self._stderr[:-40]
        except (OSError, ValueError):
            pass

    @staticmethod
    def _close_pipes(proc: subprocess.Popen) -> None:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _write_locked(self, obj: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise EngineError("KataGo analysis 进程不可用")
        try:
            proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise EngineError(f"无法写入 KataGo analysis：{error}") from error

    def _build_query(self, position: Position, query_id: str) -> dict:
        if position.has_setup():
            moves = []
            initial = []
            for idx, color in enumerate(position.grid):
                if color == BLACK:
                    initial.append(["B", format_vertex(idx, position.size)])
                elif color == WHITE:
                    initial.append(["W", format_vertex(idx, position.size)])
        else:
            initial = []
            moves = [
                ["B" if color == BLACK else "W", "pass" if move == PASS else format_vertex(move, position.size)]
                for color, move in position.moves
            ]
        query = {
            "id": query_id,
            "initialStones": initial,
            "moves": moves,
            "rules": KATAGO_RULES.get(position.ko_rule, "chinese-ogs"),
            "komi": position.komi,
            "boardXSize": position.size,
            "boardYSize": position.size,
            "includeOwnership": True,
            "reportDuringSearchEvery": 0.2,
            "analysisPVLen": 10,
        }
        if not moves:
            query["initialPlayer"] = "B" if position.to_play == BLACK else "W"
        visits = int(self.config.analysis_visits)
        if visits > 0:
            query["maxVisits"] = visits
        else:
            # 0 表示持续分析：给一个实际上到不了的上限，靠走子/关闭来取消。
            query["maxVisits"] = 1_000_000_000
        return query

    def _is_black_perspective(self, to_play: int) -> bool:
        if self.winrates_as == "BLACK":
            return True
        if self.winrates_as == "WHITE":
            return False
        return to_play == BLACK

    def _winrate(self, value: float, to_play: int) -> float:
        return value if self._is_black_perspective(to_play) else 1.0 - value

    def _score(self, value: float, to_play: int) -> float:
        return value if self._is_black_perspective(to_play) else -value

    def _ownership(self, value: float, to_play: int) -> float:
        return value if self._is_black_perspective(to_play) else -value

    def _parse(self, obj: dict, position: Position) -> Analysis:
        root = obj.get("rootInfo") or {}
        moves = []
        for info in obj.get("moveInfos") or []:
            vertex = str(info.get("move") or "")
            try:
                index = None if vertex.lower() == "pass" else parse_vertex(vertex, position.size)
            except ValueError:
                continue
            moves.append(
                MoveEval(
                    vertex=vertex,
                    index=index,
                    visits=int(info.get("visits") or 0),
                    winrate=self._winrate(float(info.get("winrate") or 0.0), position.to_play),
                    score_lead=self._score(float(info.get("scoreLead") or 0.0), position.to_play),
                    order=int(info.get("order") or 0),
                    pv=tuple(str(item) for item in (info.get("pv") or [])),
                )
            )
        ownership = obj.get("ownership")
        if isinstance(ownership, list):
            ownership_values = tuple(
                self._ownership(float(value), position.to_play) for value in ownership
            )
        else:
            ownership_values = None
        return Analysis(
            key=position.key(),
            to_play=position.to_play,
            root_winrate=self._winrate(float(root.get("winrate") or 0.0), position.to_play),
            root_score_lead=self._score(float(root.get("scoreLead") or 0.0), position.to_play),
            moves=tuple(moves),
            ownership=ownership_values,
            during_search=bool(obj.get("isDuringSearch", False)),
        )

    def analyze(
        self,
        position: Position,
        on_update: Callable[[Analysis], None] | None = None,
    ) -> Analysis:
        if not self.available():
            raise EngineUnavailable(self.config.analysis_missing_reason())
        with self._lock:
            self._start_locked()
            self._counter += 1
            query_id = f"analysis-{self._counter}"
            target: queue.Queue = queue.Queue()
            self._pending[query_id] = target
            self._write_locked(self._build_query(position, query_id))
        try:
            while True:
                try:
                    item = target.get(timeout=self.config.timeout)
                except queue.Empty:
                    self.cancel()
                    raise EngineError(f"KataGo analysis 响应超时（{self.config.timeout:g}s）")
                if item is _CANCELLED:
                    raise AnalysisCancelled("分析已取消")
                if item is _EOF:
                    tail = " | ".join(self._stderr[-3:])
                    raise EngineError("KataGo analysis 已退出" + (f"：{tail}" if tail else ""))
                if not isinstance(item, dict):
                    continue
                if item.get("error"):
                    raise EngineError(f"KataGo analysis 错误：{item['error']}")
                analysis = self._parse(item, position)
                if on_update is not None:
                    on_update(analysis)
                if not analysis.during_search:
                    return analysis
        finally:
            with self._lock:
                self._pending.pop(query_id, None)

    def cancel(self) -> None:
        with self._lock:
            if not self._pending:
                return
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._counter += 1
                    self._write_locked(
                        {"id": f"cancel-{self._counter}", "action": "terminate_all"}
                    )
                except EngineError:
                    pass
            for target in list(self._pending.values()):
                target.put(_CANCELLED)

    def close(self) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            for target in list(self._pending.values()):
                target.put(_CANCELLED)
            self._pending.clear()
            if proc is None:
                return
            try:
                if proc.poll() is None and proc.stdin is not None:
                    proc.stdin.write(
                        json.dumps({"id": "quit", "action": "terminate_all"}) + "\n"
                    )
                    proc.stdin.flush()
                    proc.stdin.close()
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


class AnalysisService:
    """在后台线程里持续分析当前局面，供网页轮询最新快照。"""

    def __init__(self, source, analyzer: KataGoAnalysis, interval: float = 0.2):
        self.source = source
        self.analyzer = analyzer
        self.interval = interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = False
        self._generation = 0
        self._key: str | None = None
        self._latest: Analysis | None = None
        self._error = ""

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)
            if enabled:
                if self._error:
                    self._key = None
                    self._latest = None
                self._error = ""
            if enabled and self._thread is None:
                self._thread = threading.Thread(
                    target=self._run,
                    name="katago-analysis",
                    daemon=True,
                )
                self._thread.start()
        if not enabled:
            self.analyzer.cancel()

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1
            self._error = ""
            self._key = None
        self.analyzer.cancel()

    def _publish(self, analysis: Analysis, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            if not self._enabled:
                return
            self._latest = analysis
            self._error = ""

    def _publish_error(self, error: Exception, generation: int) -> None:
        with self._lock:
            if generation != self._generation or not self._enabled:
                return
            self._error = str(error)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                enabled = self._enabled
            if not enabled:
                self._stop.wait(0.2)
                continue
            with self.source._lock:
                position = Position.from_game(self.source.game)
            key = position.key()
            with self._lock:
                if key == self._key and (self._latest is not None or self._error):
                    self._stop.wait(self.interval)
                    continue
                self._generation += 1
                generation = self._generation
                self._key = key
                self._error = ""
            try:
                result = self.analyzer.analyze(
                    position,
                    on_update=lambda analysis, g=generation: self._publish(analysis, g),
                )
                if result is not None:
                    self._publish(result, generation)
            except AnalysisCancelled:
                pass
            except EngineError as error:
                self._publish_error(error, generation)
            except Exception as error:
                self._publish_error(error, generation)

    def snapshot(self, current_key: str) -> dict:
        with self._lock:
            return {
                "available": self.analyzer.available(),
                "enabled": self._enabled,
                "hint": self.analyzer.unavailable_reason(),
                "analysis": self._latest.to_dict() if self._latest is not None else None,
                "current_key": current_key,
                "error": self._error,
                "visits": getattr(
                    getattr(self.analyzer, "config", None),
                    "analysis_visits",
                    0,
                ),
            }

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            self._enabled = False
        self.analyzer.cancel()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3)
        self.analyzer.close()
