from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VISITS = 300
DEFAULT_TIMEOUT = 30.0

@dataclass(frozen=True)
class AIConfig:
    binary: str = ""
    model: str = ""
    gtp_config: str = ""
    analysis_config: str = ""
    max_visits: int = DEFAULT_VISITS
    max_time: float | None = None
    timeout: float = DEFAULT_TIMEOUT

    def binary_path(self) -> str:
        """返回可执行文件的绝对路径；如果是 PATH 中的命令名则解析它。"""
        if not self.binary:
            return ""
        path = Path(self.binary).expanduser()
        if path.is_file():
            return str(path)
        return shutil.which(self.binary) or ""

    def available(self) -> bool:
        return bool(
            self.binary_path()
            and self.model
            and Path(self.model).is_file()
            and (not self.gtp_config or Path(self.gtp_config).is_file())
        )

    def missing_reason(self) -> str:
        if not self.binary:
            return "未找到 katago 可执行文件；macOS 可运行 brew install katago"
        if not self.binary_path():
            return f"katago 不可执行：{self.binary}"
        if not self.model:
            return "未找到 KataGo 模型（.bin.gz）；可用 --ai-model 或 ai.json 指定"
        if not Path(self.model).is_file():
            return f"KataGo 模型不存在：{self.model}"
        if self.gtp_config and not Path(self.gtp_config).is_file():
            return f"KataGo 配置不存在：{self.gtp_config}"
        return ""

    def analysis_available(self) -> bool:
        return bool(
            self.binary_path()
            and self.model
            and Path(self.model).is_file()
            and self.analysis_config
            and Path(self.analysis_config).is_file()
        )

    def analysis_missing_reason(self) -> str:
        if not self.binary:
            return "未找到 katago 可执行文件；macOS 可运行 brew install katago"
        if not self.binary_path():
            return f"katago 不可执行：{self.binary}"
        if not self.model:
            return "未找到 KataGo 模型（.bin.gz）；可用 --ai-model 或 ai.json 指定"
        if not Path(self.model).is_file():
            return f"KataGo 模型不存在：{self.model}"
        if not self.analysis_config:
            return "未找到 analysis_example.cfg；可用 --ai-analysis-config 或 ai.json 指定"
        if not Path(self.analysis_config).is_file():
            return f"KataGo 分析配置不存在：{self.analysis_config}"
        return ""


def _resolve_path(value, base: Path) -> str:
    if value in (None, ""):
        return ""
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return str(path.resolve())


def _resolve_binary(value, base: Path) -> str:
    if value in (None, ""):
        return ""
    text = str(value)
    if "/" in text or text.startswith("~"):
        return _resolve_path(text, base)
    return text


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_VISITS


def _as_optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_timeout(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return number if number > 0 else DEFAULT_TIMEOUT


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"无法读取 AI 配置 {path}：{error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"AI 配置不是合法 JSON：{path}（{error}）") from error
    if not isinstance(data, dict):
        raise ValueError(f"AI 配置必须是 JSON 对象：{path}")
    return data


def _env_overrides() -> dict:
    mapping = {
        "binary": "KATAGO_BIN",
        "model": "KATAGO_MODEL",
        "gtp_config": "KATAGO_CONFIG",
        "analysis_config": "KATAGO_ANALYSIS_CONFIG",
        "max_visits": "KATAGO_VISITS",
        "max_time": "KATAGO_TIME",
        "timeout": "KATAGO_TIMEOUT",
    }
    values = {}
    for key, env_name in mapping.items():
        value = os.environ.get(env_name)
        if value not in (None, ""):
            values[key] = value
    return values


def _model_dirs(binary: str) -> list[Path]:
    dirs: list[Path] = []
    if binary:
        resolved = Path(binary).expanduser().resolve()
        dirs.extend(
            [
                resolved.parent / "models",
                resolved.parent.parent / "share" / "katago",
                resolved.parent.parent / "share" / "katago" / "models",
            ]
        )
    brew = shutil.which("brew")
    if brew:
        try:
            result = subprocess.run(
                [brew, "--prefix", "katago"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            prefix = Path(result.stdout.strip())
            dirs.extend(
                [
                    prefix / "share" / "katago",
                    prefix / "share" / "katago" / "models",
                ]
            )
    dirs.append(Path.cwd() / "models")
    seen = set()
    unique = []
    for directory in dirs:
        key = str(directory)
        if key not in seen:
            seen.add(key)
            unique.append(directory)
    return unique


def _model_rank(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if "human" in name:
        return (9, name)
    if "b18c384nbt" in name:
        return (0, name)
    if "b15" in name:
        return (1, name)
    if "b10" in name:
        return (2, name)
    if "b20" in name:
        return (3, name)
    if "b40" in name:
        return (4, name)
    return (5, name)


def _find_model(binary: str) -> str:
    candidates: list[Path] = []
    for directory in _model_dirs(binary):
        if directory.is_dir():
            candidates.extend(directory.glob("*.bin.gz"))
    if not candidates:
        return ""
    return str(sorted(candidates, key=_model_rank)[0])


def _find_gtp_config(binary: str) -> str:
    names = (
        "configs/gtp_example.cfg",
        "configs/gtp.cfg",
        "configs/default_gtp.cfg",
        "gtp_example.cfg",
        "gtp.cfg",
        "default_gtp.cfg",
    )
    for directory in _model_dirs(binary):
        for name in names:
            path = directory / name
            if path.is_file():
                return str(path)
    return ""


def _find_analysis_config(binary: str) -> str:
    names = (
        "configs/analysis_example.cfg",
        "configs/analysis.cfg",
        "analysis_example.cfg",
        "analysis.cfg",
    )
    for directory in _model_dirs(binary):
        for name in names:
            path = directory / name
            if path.is_file():
                return str(path)
    return ""


def discover_config(overrides: dict | None = None, config_path=None) -> AIConfig | None:
    """按 CLI > 环境变量 > ai.json > 自动发现 的顺序组装配置。

    没有任何线索时返回 ``None``；找到线索但缺模型时仍返回配置，
    以便界面显示具体缺什么。
    """
    overrides = dict(overrides or {})
    file_data: dict = {}
    base = Path.cwd()
    if config_path not in (None, ""):
        path = Path(str(config_path)).expanduser()
        if not path.is_absolute():
            path = base / path
        if not path.is_file():
            raise ValueError(f"AI 配置文件不存在：{path}")
        file_data = _read_json(path)
        base = path.parent
    else:
        path = base / "ai.json"
        if path.is_file():
            file_data = _read_json(path)
            base = path.parent

    merged: dict = {}
    for key in ("binary", "model", "gtp_config", "analysis_config"):
        value = file_data.get(key)
        if value not in (None, ""):
            merged[key] = (
                _resolve_binary(value, base)
                if key == "binary"
                else _resolve_path(value, base)
            )
    for key in ("max_visits", "max_time", "timeout"):
        if key in file_data:
            merged[key] = file_data[key]
    merged.update(_env_overrides())
    merged.update({key: value for key, value in overrides.items() if value is not None})

    binary = _resolve_binary(merged.get("binary"), base)
    if not binary:
        binary = shutil.which("katago") or ""
    model = _resolve_path(merged.get("model"), base)
    gtp_config = _resolve_path(merged.get("gtp_config"), base)
    analysis_config = _resolve_path(merged.get("analysis_config"), base)

    had_hint = bool(
        binary or model or gtp_config or analysis_config or file_data or overrides
    )
    if not had_hint:
        return None
    if not model and binary:
        model = _find_model(binary)
    if not gtp_config and binary:
        gtp_config = _find_gtp_config(binary)
    if not analysis_config and binary:
        analysis_config = _find_analysis_config(binary)

    return AIConfig(
        binary=binary,
        model=model,
        gtp_config=gtp_config,
        analysis_config=analysis_config,
        max_visits=_as_int(merged.get("max_visits", DEFAULT_VISITS)),
        max_time=_as_optional_float(merged.get("max_time")),
        timeout=_as_timeout(merged.get("timeout", DEFAULT_TIMEOUT)),
    )


def add_cli_arguments(parser) -> None:
    parser.add_argument("--ai-bin", help="KataGo 可执行文件路径（默认自动查找）")
    parser.add_argument("--ai-model", help="KataGo 模型 .bin.gz 路径")
    parser.add_argument("--ai-gtp-config", help="KataGo gtp.cfg 路径")
    parser.add_argument("--ai-analysis-config", help="KataGo analysis_example.cfg 路径")
    parser.add_argument("--ai-config", help="AI 配置文件 ai.json 的路径")
    parser.add_argument("--ai-visits", type=int, default=None, help="每手最大访问数（默认 300）")
    parser.add_argument("--ai-time", type=float, default=None, help="每手最大思考秒数")
    parser.add_argument("--ai-timeout", type=float, default=None, help="等待引擎响应的超时秒数（默认 30）")


def overrides_from_args(args) -> dict:
    mapping = {
        "binary": "ai_bin",
        "model": "ai_model",
        "gtp_config": "ai_gtp_config",
        "analysis_config": "ai_analysis_config",
        "max_visits": "ai_visits",
        "max_time": "ai_time",
        "timeout": "ai_timeout",
    }
    values = {}
    for key, attr in mapping.items():
        value = getattr(args, attr, None)
        if value is not None:
            values[key] = value
    return values
