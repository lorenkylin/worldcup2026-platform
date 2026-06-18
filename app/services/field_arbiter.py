"""字段级置信度仲裁器（v0.14.4）.

对同一场比赛的同一字段，从多个数据源候选值中按置信度和时效选出最优值，
并记录冲突。不新增 DB 表，仲裁日志写入 `data/field_arbitration_log.jsonl`。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services import data_quality

logger = logging.getLogger(__name__)

# 字段级数据源置信度（0-100），数字越大越可信。
# 同一字段不同源的置信度差异应足够大，避免微小波动导致反复切换。
FIELD_CONFIDENCE: Dict[str, Dict[str, int]] = {
    # 静态权威字段：官方赛程/球队/球场为最高权威
    "home_team_id": {
        "fixtures": 100,
        "api-football": 90,
        "worldcup26.ir": 70,
        "manual": 110,
    },
    "away_team_id": {
        "fixtures": 100,
        "api-football": 90,
        "worldcup26.ir": 70,
        "manual": 110,
    },
    "stadium_id": {
        "fixtures": 100,
        "api-football": 90,
        "worldcup26.ir": 70,
        "manual": 110,
    },
    "kickoff_at": {
        "fixtures": 100,
        "api-football": 90,
        "worldcup26.ir": 70,
        "manual": 110,
    },
    "stage": {
        "fixtures": 100,
        "api-football": 90,
        "worldcup26.ir": 70,
        "manual": 110,
    },
    "group_name": {
        "fixtures": 100,
        "api-football": 90,
        "worldcup26.ir": 70,
        "manual": 110,
    },
    "round_number": {
        "fixtures": 100,
        "api-football": 90,
        "worldcup26.ir": 70,
        "manual": 110,
    },
    # 动态实时字段：实时 API 与 wc26 同等重要，时效优先
    "status": {
        "api-football": 95,
        "worldcup26.ir": 95,
        "manual": 110,
    },
    "time_elapsed": {
        "api-football": 95,
        "worldcup26.ir": 95,
        "manual": 110,
    },
    "home_score": {
        "api-football": 95,
        "worldcup26.ir": 95,
        "manual": 110,
    },
    "away_score": {
        "api-football": 95,
        "worldcup26.ir": 95,
        "manual": 110,
    },
}

# 允许参与仲裁的字段集合
ARBITRABLE_FIELDS = set(FIELD_CONFIDENCE.keys())


@dataclass
class FieldCandidate:
    """单个字段候选值."""

    field: str
    value: Any
    source: str
    recorded_at: Optional[datetime] = None
    confidence: int = 0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "source": self.source,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class FieldDecision:
    """单个字段仲裁结果."""

    field: str
    value: Any
    source: str
    confidence: int
    candidates: List[FieldCandidate]
    had_conflict: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "had_conflict": self.had_conflict,
            "reason": self.reason,
            "candidates": [c.to_dict() for c in self.candidates],
        }


@dataclass
class ArbitrationResult:
    """一场比赛的整体仲裁结果."""

    match_number: int
    decisions: Dict[str, FieldDecision]
    conflicts: List[Dict[str, Any]] = dc_field(default_factory=list)
    arbitrated_at: datetime = dc_field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_number": self.match_number,
            "arbitrated_at": self.arbitrated_at.isoformat(),
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "conflicts": self.conflicts,
        }


def get_confidence(field: str, source: str) -> int:
    """获取某字段某数据源的置信度."""
    return FIELD_CONFIDENCE.get(field, {}).get(source, 0)


def _parse_recorded_at(value: Any) -> Optional[datetime]:
    """安全解析时间戳."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return data_quality.as_utc(value)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return data_quality.as_utc(dt)
    except Exception:  # noqa: BLE001
        return None


def _is_value_valid_for_field(field: str, value: Any, match_status: Optional[str] = None) -> bool:
    """字段级业务校验."""
    if value is None:
        return False
    if field == "kickoff_at":
        return data_quality.validate_kickoff_window(value, context="arbitration")
    if field in ("home_score", "away_score"):
        # 比分只在 live/finished 时有效；finished 后禁止回退到 None 已在调用方处理
        if match_status in ("live", "finished"):
            return True
        # 未开始比赛若有比分，可能是脏数据，拒绝
        return False
    return True


def _pick_winner(candidates: List[FieldCandidate], field: str, current_status: Optional[str]) -> FieldDecision:
    """从候选值中选出最优值."""
    if not candidates:
        raise ValueError("候选值列表为空")

    # 按置信度降序、时间戳降序排序
    def _sort_key(c: FieldCandidate) -> tuple:
        ts = c.recorded_at or datetime.min.replace(tzinfo=timezone.utc)
        return (c.confidence, ts)

    sorted_candidates = sorted(candidates, key=_sort_key, reverse=True)
    winner = sorted_candidates[0]

    # 检测冲突：存在与 winner 值不同且置信度/时间接近的候选
    conflicts = [
        c for c in sorted_candidates[1:]
        if c.value != winner.value and c.confidence >= winner.confidence - 10
    ]
    had_conflict = len(conflicts) > 0

    reason = (
        f"置信度最高 ({winner.confidence})"
        if winner.confidence >= max((c.confidence for c in sorted_candidates[1:]), default=0)
        else "时间戳最新"
    )
    if winner.source == "manual":
        reason = "manual 源永远胜出"

    return FieldDecision(
        field=field,
        value=winner.value,
        source=winner.source,
        confidence=winner.confidence,
        candidates=sorted_candidates,
        had_conflict=had_conflict,
        reason=reason,
    )


def arbitrate(
    match_number: int,
    candidates: List[FieldCandidate],
    current_status: Optional[str] = None,
) -> ArbitrationResult:
    """对一场比赛的字段候选值做仲裁.

    Args:
        match_number: 比赛编号。
        candidates: 该比赛所有字段的所有候选值。
        current_status: 当前数据库中的比赛状态，用于业务校验。

    Returns:
        ArbitrationResult，包含每个字段的胜出值和冲突记录。
    """
    by_field: Dict[str, List[FieldCandidate]] = {}
    for c in candidates:
        if c.field not in ARBITRABLE_FIELDS:
            continue
        # 补充置信度
        if c.confidence == 0:
            c.confidence = get_confidence(c.field, c.source)
        # 业务校验
        if not _is_value_valid_for_field(c.field, c.value, current_status):
            c.reason = "业务校验未通过"
            continue
        by_field.setdefault(c.field, []).append(c)

    decisions: Dict[str, FieldDecision] = {}
    conflicts: List[Dict[str, Any]] = []

    for field, field_candidates in by_field.items():
        if not field_candidates:
            continue

        # 状态字段额外校验
        if field == "status":
            valid = []
            for c in field_candidates:
                if data_quality.is_status_transition_allowed(current_status, c.value):
                    valid.append(c)
                else:
                    c.reason = f"状态回退: {current_status} -> {c.value} 不允许"
            field_candidates = valid
            if not field_candidates:
                continue

        decision = _pick_winner(field_candidates, field, current_status)
        decisions[field] = decision

        if decision.had_conflict:
            conflicts.append({
                "match_number": match_number,
                "field": field,
                "winner": {
                    "value": decision.value,
                    "source": decision.source,
                    "confidence": decision.confidence,
                },
                "losers": [
                    {
                        "value": c.value,
                        "source": c.source,
                        "confidence": c.confidence,
                        "reason": c.reason,
                    }
                    for c in decision.candidates[1:] if c.value != decision.value
                ],
                "arbitrated_at": datetime.now(timezone.utc).isoformat(),
            })

    return ArbitrationResult(
        match_number=match_number,
        decisions=decisions,
        conflicts=conflicts,
    )


def _default_log_path() -> Path:
    """默认冲突日志路径."""
    data_dir = Path(getattr(settings, "data_dir", "./data"))
    return data_dir / "field_arbitration_log.jsonl"


def log_conflicts(conflicts: List[Dict[str, Any]], log_path: Optional[Path] = None) -> None:
    """将冲突记录追加到 JSONL 文件."""
    if not conflicts:
        return
    path = log_path or _default_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for conflict in conflicts:
                f.write(json.dumps(conflict, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[field_arbiter] 写入冲突日志失败: %s", exc)


def read_recent_conflicts(limit: int = 100, log_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """读取最近 N 条冲突记录."""
    path = log_path or _default_log_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        # 最后 limit 条
        recent = lines[-limit:] if len(lines) > limit else lines
        return [json.loads(line) for line in recent if line.strip()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[field_arbiter] 读取冲突日志失败: %s", exc)
        return []
