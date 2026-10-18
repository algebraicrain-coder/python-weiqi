from __future__ import annotations

from .analysis import Analysis, AnalysisCancelled, AnalysisService, KataGoAnalysis, MoveEval
from .base import (
    Engine,
    EngineError,
    EnginePlayer,
    EngineUnavailable,
    Position,
)
from .config import (
    AIConfig,
    add_cli_arguments,
    discover_config,
    overrides_from_args,
)
from .katago import KATAGO_RULES, KataGoGTP


def make_engine(config: AIConfig | None = None):
    """根据配置创建引擎；不可用时返回 None。"""
    config = config if config is not None else discover_config()
    if config is None or not config.available():
        return None
    return KataGoGTP(config)


__all__ = [
    "AIConfig",
    "Analysis",
    "AnalysisCancelled",
    "AnalysisService",
    "Engine",
    "EngineError",
    "KataGoAnalysis",
    "MoveEval",
    "EnginePlayer",
    "EngineUnavailable",
    "KATAGO_RULES",
    "KataGoGTP",
    "Position",
    "add_cli_arguments",
    "discover_config",
    "make_engine",
    "overrides_from_args",
]
