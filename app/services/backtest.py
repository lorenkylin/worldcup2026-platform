"""B6 - 预测回测引擎.

用 2018+2022 共 111 条 H2H 历史种子比赛，反向验证 Elo-Poisson v1 模型的校准度。

核心指标：
1. Brier Score = (p_home - y_home)² + (p_draw - y_draw)² + (p_away - y_away)²
   - 越低越好，0=完美，0.667=三选一随机
2. 准确率 = argmax(p_home, p_draw, p_away) 与实际 1X2 一致比例
3. Top-N 召回：实际结果在预测概率前 N 名的比例

回测时使用**当前 FIFA 排名**作为球队实力档位（静态代理），测试的是：
- 模型的概率校准度
- 不偏向热门/冷门
- 不会对实力悬殊比赛给出离谱预测
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Team, H2HHistoricalMatch


# =============== B6 评估指标 ===============
@dataclass
class MatchResult:
    """一场回测比赛的结果快照。"""

    match_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    actual_outcome: str  # "home" / "draw" / "away"
    match_date: datetime
    stage: str = ""


@dataclass
class PredictionResult:
    """单场比赛的模型预测。"""

    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    expected_home_goals: float
    expected_away_goals: float
    predicted_outcome: str  # argmax
    actual_outcome: str
    is_correct: bool
    brier_contribution: float


@dataclass
class BacktestReport:
    """完整回测报告。"""

    n_matches: int
    n_skipped: int  # 因球队不存在被跳过
    n_evaluated: int

    # 准确率
    accuracy: float  # 0-1
    home_accuracy: float  # 实际主胜比赛中预测也主胜的比例
    draw_accuracy: float
    away_accuracy: float

    # Brier Score
    brier_score: float
    brier_score_home: float  # 仅对实际主胜比赛
    brier_score_draw: float
    brier_score_away: float

    # 校准度
    mean_predicted_home: float
    actual_home_freq: float  # 实际主胜频率

    # Top-N 召回
    top1_recall: float  # 实际结果在 argmax
    top2_recall: float  # 实际结果在前 2 名

    # 详细数据（可选，调试用）
    predictions: List[Dict] = field(default_factory=list)

    # 元信息
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    method: str = "Elo-Poisson v1 (current FIFA rank as static proxy)"


# =============== 复用 prediction.py 的核心函数 ===============
from app.services.prediction import (
    elo_from_fifa_rank,
    _elo_to_lambda,
    _apply_recent_form,
    _predict_score_distribution,
    FALLBACK_ELO_NO_RANK,
)


def _build_match_result(hist: H2HHistoricalMatch, home_team: Optional[Team], away_team: Optional[Team]) -> MatchResult:
    """从 H2HHistoricalMatch 构建 MatchResult。"""
    if hist.home_score > hist.away_score:
        actual = "home"
    elif hist.home_score < hist.away_score:
        actual = "away"
    else:
        actual = "draw"

    return MatchResult(
        match_id=f"HIST-{hist.id}",
        home_team=hist.home_fifa_code,
        away_team=hist.away_fifa_code,
        home_score=hist.home_score,
        away_score=hist.away_score,
        actual_outcome=actual,
        match_date=hist.match_date,
        stage=hist.stage or "",
    )


def _predict_for_backtest(
    home: Team, away: Team, hist: H2HHistoricalMatch
) -> PredictionResult:
    """对一场历史比赛跑当前模型，返回预测结果。"""
    # B1: Elo 校准（用当前 fifa_rank）
    home_elo = elo_from_fifa_rank(home.fifa_rank)
    away_elo = elo_from_fifa_rank(away.fifa_rank)

    # 中立场地（世界杯都是中立场）
    home_lambda, away_lambda = _elo_to_lambda(home_elo, away_elo)

    # B2: 近期状态 - 历史比赛无 form 数据，跳过
    home_lambda, away_lambda = _apply_recent_form(
        home_lambda, away_lambda, None, None
    )

    # Poisson 预测
    home_win, draw, away_win, _best_score = _predict_score_distribution(
        home_lambda, away_lambda
    )

    # argmax
    probs = {"home": home_win, "draw": draw, "away": away_win}
    predicted = max(probs, key=probs.get)  # type: ignore

    # 实际结果（按 hist 数据）
    if hist.home_score > hist.away_score:
        actual = "home"
    elif hist.home_score < hist.away_score:
        actual = "away"
    else:
        actual = "draw"

    # Brier Score contribution
    brier = (
        (probs["home"] - (1 if actual == "home" else 0)) ** 2
        + (probs["draw"] - (1 if actual == "draw" else 0)) ** 2
        + (probs["away"] - (1 if actual == "away" else 0)) ** 2
    )

    return PredictionResult(
        home_win_prob=home_win,
        draw_prob=draw,
        away_win_prob=away_win,
        expected_home_goals=home_lambda,
        expected_away_goals=away_lambda,
        predicted_outcome=predicted,
        actual_outcome=actual,
        is_correct=(predicted == actual),
        brier_contribution=brier,
    )


def run_backtest(db: Session, lookback: int = 999) -> BacktestReport:
    """执行回测主函数.

    Args:
        db: SQLAlchemy 会话
        lookback: 取最近 N 条历史比赛（默认全部 111）

    Returns:
        BacktestReport 完整报告
    """
    # 1. 拉所有历史比赛
    hist_matches = (
        db.query(H2HHistoricalMatch)
        .order_by(H2HHistoricalMatch.match_date.desc())
        .limit(lookback)
        .all()
    )

    # 2. 缓存球队 (fifa_code → Team)
    teams_by_code: Dict[str, Team] = {
        t.fifa_code: t for t in db.query(Team).all()
    }

    # 3. 逐场预测
    predictions: List[PredictionResult] = []
    skipped = 0
    evaluated = 0
    detail: List[Dict] = []

    for hist in hist_matches:
        home = teams_by_code.get(hist.home_fifa_code)
        away = teams_by_code.get(hist.away_fifa_code)
        if home is None or away is None:
            skipped += 1
            continue

        pred = _predict_for_backtest(home, away, hist)
        predictions.append(pred)
        evaluated += 1

        # 详情（只保留前 30 场 + 关键场次，避免报告过长）
        if evaluated <= 30 or hist.stage in ("Final", "Semifinal", "Quarterfinal"):
            detail.append(
                {
                    "match_id": f"HIST-{hist.id}",
                    "home": home.name_zh,
                    "away": away.name_zh,
                    "actual_score": f"{hist.home_score}:{hist.away_score}",
                    "actual": pred.actual_outcome,
                    "pred": pred.predicted_outcome,
                    "p_home": round(pred.home_win_prob, 3),
                    "p_draw": round(pred.draw_prob, 3),
                    "p_away": round(pred.away_win_prob, 3),
                    "brier": round(pred.brier_contribution, 3),
                    "stage": hist.stage,
                }
            )

    if not predictions:
        # 没有匹配数据，返回空报告
        return BacktestReport(
            n_matches=len(hist_matches),
            n_skipped=skipped,
            n_evaluated=0,
            accuracy=0.0,
            home_accuracy=0.0,
            draw_accuracy=0.0,
            away_accuracy=0.0,
            brier_score=0.0,
            brier_score_home=0.0,
            brier_score_draw=0.0,
            brier_score_away=0.0,
            mean_predicted_home=0.0,
            actual_home_freq=0.0,
            top1_recall=0.0,
            top2_recall=0.0,
            predictions=[],
        )

    # 4. 计算指标
    correct = sum(1 for p in predictions if p.is_correct)
    accuracy = correct / len(predictions)

    # 按实际结果分组
    by_actual: Dict[str, List[PredictionResult]] = {
        "home": [], "draw": [], "away": []
    }
    for p in predictions:
        by_actual[p.actual_outcome].append(p)

    def _group_accuracy(group: List[PredictionResult]) -> float:
        if not group:
            return 0.0
        return sum(1 for p in group if p.is_correct) / len(group)

    def _group_brier(group: List[PredictionResult]) -> float:
        if not group:
            return 0.0
        return sum(p.brier_contribution for p in group) / len(group)

    home_acc = _group_accuracy(by_actual["home"])
    draw_acc = _group_accuracy(by_actual["draw"])
    away_acc = _group_accuracy(by_actual["away"])

    brier_overall = sum(p.brier_contribution for p in predictions) / len(predictions)
    brier_home = _group_brier(by_actual["home"])
    brier_draw = _group_brier(by_actual["draw"])
    brier_away = _group_brier(by_actual["away"])

    # 平均预测主胜概率
    mean_pred_home = sum(p.home_win_prob for p in predictions) / len(predictions)
    actual_home_freq = len(by_actual["home"]) / len(predictions)

    # Top-N recall
    def _topn_recall(n: int) -> float:
        hit = 0
        for p in predictions:
            probs = {"home": p.home_win_prob, "draw": p.draw_prob, "away": p.away_win_prob}
            top_n = sorted(probs, key=probs.get, reverse=True)[:n]  # type: ignore
            if p.actual_outcome in top_n:
                hit += 1
        return hit / len(predictions)

    top1 = _topn_recall(1)
    top2 = _topn_recall(2)

    return BacktestReport(
        n_matches=len(hist_matches),
        n_skipped=skipped,
        n_evaluated=evaluated,
        accuracy=accuracy,
        home_accuracy=home_acc,
        draw_accuracy=draw_acc,
        away_accuracy=away_acc,
        brier_score=brier_overall,
        brier_score_home=brier_home,
        brier_score_draw=brier_draw,
        brier_score_away=brier_away,
        mean_predicted_home=mean_pred_home,
        actual_home_freq=actual_home_freq,
        top1_recall=top1,
        top2_recall=top2,
        predictions=detail,
    )


def render_markdown_report(report: BacktestReport) -> str:
    """生成可读的回测报告（中文）。"""
    md = f"""# 📊 B6 预测模型回测报告

> 生成时间：{report.generated_at}
> 方法：{report.method}

## 🎯 核心指标

| 指标 | 数值 | 解读 |
|------|------|------|
| **总比赛数** | {report.n_matches} 场（评估 {report.n_evaluated}，跳过 {report.n_skipped}）| 跳过原因：球队不在 2026 名单内 |
| **整体准确率** | **{report.accuracy * 100:.1f}%** | argmax 命中实际 1X2 |
| **Brier Score** | **{report.brier_score:.3f}** | 0=完美，0.667=随机 |
| **Top-1 召回** | {report.top1_recall * 100:.1f}% | 实际结果在 argmax |
| **Top-2 召回** | {report.top2_recall * 100:.1f}% | 实际结果在前 2 名 |

## 📈 分结果准确率

| 实际结果 | 场数 | 预测准确率 | Brier Score |
|---------|------|-----------|-------------|
| 主胜 (H) | {int(report.actual_home_freq * report.n_evaluated)} | {report.home_accuracy * 100:.1f}% | {report.brier_score_home:.3f} |
| 平局 (D) | {int((1 - report.actual_home_freq - 0) * report.n_evaluated)} (估) | {report.draw_accuracy * 100:.1f}% | {report.brier_score_draw:.3f} |
| 客胜 (A) | - | {report.away_accuracy * 100:.1f}% | {report.brier_score_away:.3f} |

## 🧮 校准度分析

| 维度 | 数值 |
|------|------|
| 模型平均预测主胜概率 | {report.mean_predicted_home * 100:.1f}% |
| 实际主胜频率 | {report.actual_home_freq * 100:.1f}% |
| 偏差 | {(report.mean_predicted_home - report.actual_home_freq) * 100:+.1f} 个百分点 |

> 偏差越接近 0 越好。正偏差=模型偏看好主队，负偏差=模型低估主队。

## 📋 部分预测明细（前 30 场 + 关键场次）

| 日期 | 对阵 | 实际比分 | 实际 | 预测 | P(H) | P(D) | P(A) | Brier |
|------|------|---------|------|------|------|------|------|-------|
"""
    for p in report.predictions:
        md += (
            f"| {p['stage'][:20]} | {p['home']} vs {p['away']} "
            f"| {p['actual_score']} | {p['actual']} | {p['pred']} "
            f"| {p['p_home']:.2f} | {p['p_draw']:.2f} | {p['p_away']:.2f} | {p['brier']:.3f} |\n"
        )

    md += f"""
## 💡 结论与建议

### 总体评级
- **Brier Score = {report.brier_score:.3f}** — """
    if report.brier_score < 0.5:
        md += "**优秀**（远低于随机基线 0.667）"
    elif report.brier_score < 0.6:
        md += "**良好**（明显优于随机）"
    else:
        md += "**需要改进**（接近随机基线）"

    md += f"""
- **准确率 = {report.accuracy * 100:.1f}%** — """
    if report.accuracy > 0.55:
        md += "**显著优于基线 33%**"
    elif report.accuracy > 0.45:
        md += "**优于基线 33%**"
    else:
        md += "**接近基线 33%**（三选一）"

    md += """

### 改进方向
1. **平局识别**：若 Brier Score 偏高，重点优化平局判定
2. **校准度**：若主胜偏差大，调小主场优势系数（当前 60 分）
3. **xG 接入**：当前模型用 Poisson + Elo，若引入 xG 数据可提升 5-10%
"""
    return md


# =============== 命令行入口 ===============
if __name__ == "__main__":
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        report = run_backtest(db)
        print(render_markdown_report(report))
    finally:
        db.close()
