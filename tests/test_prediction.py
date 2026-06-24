"""预测服务单元测试 v1.

覆盖：
- Elo 转 Poisson λ
- Poisson 概率合理性
- 比分分布单调性
- 星级与理由生成
- B1: FIFA 排名 → Elo 校准
- B2: 近期状态因子对 λ 的微调
- B3: 历史交锋 H2H 查询
- 边界条件（未知球队、缺数据）
"""

import pytest

from app.services.elo_params import elo_to_lambda
from app.services.prediction import (
    _poisson_prob,
    _predict_score_distribution,
    _apply_recent_form,
    _stars,
    _reasons,
    predict_match,
    elo_from_fifa_rank,
)


# ---------- Elo -> λ ----------

class TestEloToLambda:
    def test_equal_elo_both_near_base(self):
        h, a = elo_to_lambda(1500, 1500)
        # 含主场优势：home > away
        assert h > a
        assert 1.0 < h < 1.8
        assert 0.8 < a < 1.5

    def test_strong_home_team_higher_lambda(self):
        h, a = elo_to_lambda(1900, 1500)
        assert h > a + 0.5

    def test_lambda_never_below_minimum(self):
        h, a = elo_to_lambda(1200, 2000)
        assert h >= 0.3
        assert a >= 0.3


# ---------- B1: FIFA 排名 → Elo 校准 ----------

class TestEloFromFifaRank:
    """B1: 验证对数曲线映射的合理性."""

    def test_rank_1_top_elo(self):
        # rank 1 应进入 2050 上限
        assert elo_from_fifa_rank(1) == 2050

    def test_rank_5_near_top(self):
        # rank 5: 2200 - 230*log10(5) = 2200 - 230*0.699 = 2039
        elo = elo_from_fifa_rank(5)
        assert 2030 <= elo <= 2050

    def test_rank_10_strong_team(self):
        # rank 10: 2200 - 230*1.0 = 1970
        elo = elo_from_fifa_rank(10)
        assert 1960 <= elo <= 1980

    def test_rank_50_mid_field(self):
        # rank 50: 2200 - 230*1.699 = 1809
        elo = elo_from_fifa_rank(50)
        assert 1800 <= elo <= 1820

    def test_rank_100_lower(self):
        # rank 100: 2200 - 230*2.0 = 1740
        elo = elo_from_fifa_rank(100)
        assert 1730 <= elo <= 1750

    def test_rank_200_bottom(self):
        # rank 200: 2200 - 230*2.301 = 1671
        elo = elo_from_fifa_rank(200)
        assert 1660 <= elo <= 1680

    def test_none_rank_fallback(self):
        # 无排名 → 1750 兜底
        assert elo_from_fifa_rank(None) == 1750

    def test_zero_rank_fallback(self):
        # rank=0 当 None 处理
        assert elo_from_fifa_rank(0) == 1750

    def test_negative_rank_fallback(self):
        assert elo_from_fifa_rank(-1) == 1750

    def test_monotonically_decreasing(self):
        """排名越高 → Elo 越低（单调递减）."""
        prev = 9999
        for r in [1, 5, 10, 20, 50, 100, 200, 500, 1000]:
            cur = elo_from_fifa_rank(r)
            assert cur <= prev, f"rank {r} should be <= rank {r-1}"
            prev = cur

    def test_top_stronger_than_bottom(self):
        # 排名 1 vs 排名 100，分差应至少 300
        assert elo_from_fifa_rank(1) - elo_from_fifa_rank(100) >= 300


# ---------- B2: 近期状态因子 ----------

class TestRecentForm:
    """B2: 验证 recent_form 对 λ 的微调逻辑."""

    def test_no_form_returns_unchanged(self):
        # 两队都没 form → λ 应保持原值
        h, a = _apply_recent_form(1.5, 1.2, None, None)
        assert abs(h - 1.5) < 1e-6
        assert abs(a - 1.2) < 1e-6

    def test_strong_home_form_boosts_home(self):
        # 主场 5 场全胜（15分），客场 0 分
        h, a = _apply_recent_form(1.5, 1.2, 15, 0)
        assert h > 1.5
        assert a < 1.2

    def test_weak_home_form_reduces_home(self):
        h, a = _apply_recent_form(1.5, 1.2, 0, 15)
        assert h < 1.5
        assert a > 1.2

    def test_equal_form_no_change(self):
        h, a = _apply_recent_form(1.5, 1.2, 8, 8)
        # 双方 form 相同 → λ 应保持原值
        assert abs(h - 1.5) < 1e-6
        assert abs(a - 1.2) < 1e-6

    def test_form_effect_bounded_10pct(self):
        """最大影响不超过 ±10%."""
        h, a = _apply_recent_form(1.0, 1.0, 15, 0)
        # home_lambda 最多上调 10% = 1.1
        assert h <= 1.1
        # away_lambda 最多下调 10% = 0.9
        assert a >= 0.9

    def test_lambda_floor_at_0_3(self):
        """极端情况 λ 不能低于 0.3."""
        h, a = _apply_recent_form(0.5, 0.5, 0, 15)
        assert h >= 0.3
        assert a >= 0.3


# ---------- Poisson 概率 ----------

class TestPoissonProb:
    def test_probabilities_sum_to_one_when_infinite(self):
        probs = [_poisson_prob(1.35, k) for k in range(15)]
        assert sum(probs) > 0.999

    def test_peak_around_lambda(self):
        assert _poisson_prob(2.0, 2) > _poisson_prob(2.0, 0)
        assert _poisson_prob(2.0, 2) > _poisson_prob(2.0, 6)

    def test_negative_k_is_zero(self):
        assert _poisson_prob(2.0, -1) == 0.0


# ---------- 比分分布 ----------

class TestScoreDistribution:
    def test_probabilities_sum_to_one(self):
        h, d, a, *_ = _predict_score_distribution(1.5, 1.2)
        assert abs(h + d + a - 1.0) < 1e-6

    def test_strong_favorite_high_home_win(self):
        h, d, a, *_ = _predict_score_distribution(2.5, 0.7)
        assert h > 0.7
        assert a < 0.15

    def test_recommended_score_format(self):
        _, _, _, best, outcome_aligned, top_scores, conf = _predict_score_distribution(1.5, 1.2)
        assert ":" in best
        home, away = best.split(":")
        assert home.isdigit() and away.isdigit()
        assert ":" in outcome_aligned
        assert len(top_scores) == 3
        assert top_scores[0]["probability"] >= top_scores[1]["probability"] >= top_scores[2]["probability"]
        assert 0.0 < conf <= 1.0

    def test_outcome_aligned_matches_predicted_outcome(self):
        h, d, a, _, outcome_aligned, _, _ = _predict_score_distribution(2.5, 0.7)
        pred_outcome = "H" if h > d and h > a else ("D" if d >= h and d >= a else "A")
        oh, oa = map(int, outcome_aligned.split(":"))
        aligned_outcome = "H" if oh > oa else ("D" if oh == oa else "A")
        assert aligned_outcome == pred_outcome

    def test_top_scores_probabilities_sum_less_than_one(self):
        _, _, _, _, _, top_scores, _ = _predict_score_distribution(1.5, 1.2)
        assert sum(s["probability"] for s in top_scores) < 1.0


# ---------- 星级 ----------

class TestStars:
    def test_strong_favorite_5_stars(self):
        h, d, a, *_ = _predict_score_distribution(2.5, 0.7)
        assert _stars(h, d, a) == 5

    def test_balanced_match_low_stars(self):
        h, d, a, *_ = _predict_score_distribution(1.4, 1.4)
        assert _stars(h, d, a) <= 3


# ---------- 理由生成 ----------

class TestReasons:
    def _mk_team(self, name_zh, elo=1500, fifa_rank=20, id=1, form=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            id=id, name_zh=name_zh, elo_rating=elo,
            fifa_rank=fifa_rank, recent_form_points=form,
        )

    def _call_reasons(self, home, away, hl=1.5, al=1.5, hw=0.4, d=0.3, aw=0.3, home_form=None, away_form=None, h2h=None, primary="2:1", secondary="1:1", score_stars=3):
        if h2h is None:
            h2h = {"home_wins": 0, "away_wins": 0, "draws": 0, "sample": 0, "summary": ""}
        return _reasons(home, away, hl, al, hw, d, aw, home_form, away_form, h2h, primary, secondary, score_stars)

    def test_includes_elo_advantage(self):
        home = self._mk_team("巴西", elo=2050)
        away = self._mk_team("巴拉圭", elo=1500)
        reasons = self._call_reasons(home, away, hw=0.6)
        assert any("Elo" in r for r in reasons)

    def test_includes_score_prediction(self):
        home = self._mk_team("巴西", elo=2050)
        away = self._mk_team("巴拉圭", elo=1500)
        reasons = self._call_reasons(home, away, primary="2:1", secondary="1:0", score_stars=4)
        assert any("首选比分" in r and "2:1" in r for r in reasons)
        assert any("推荐度" in r and "4 星" in r for r in reasons)
        assert any("次选比分" in r and "1:0" in r for r in reasons)

    def test_includes_recent_form_when_present(self):
        home = self._mk_team("巴西", elo=1800, form=12)
        away = self._mk_team("阿根廷", elo=1800, form=3)
        reasons = self._call_reasons(home, away, home_form=12, away_form=3)
        assert any("近 5 场" in r for r in reasons)

    def test_includes_h2h_when_data_exists(self):
        home = self._mk_team("巴西", elo=1800, id=1)
        away = self._mk_team("阿根廷", elo=1800, id=2)
        h2h = {
            "home_wins": 2, "away_wins": 1, "draws": 1, "sample": 4,
            "summary": "近 4 次交锋 巴西2胜1平1负",
        }
        reasons = self._call_reasons(home, away, h2h=h2h)
        assert any("历史交锋" in r and "巴西" in r for r in reasons)

    def test_returns_between_3_and_5_reasons(self):
        home = self._mk_team("巴西", elo=1500)
        away = self._mk_team("韩国", elo=1500)
        reasons = self._call_reasons(home, away)
        assert 3 <= len(reasons) <= 5


# ---------- B3: 历史交锋 H2H ----------

class TestH2H:
    def _setup_db_with_match(self, home_id, away_id, home_score, away_score, status="finished"):
        from app.db import Base, engine, SessionLocal
        from app.models import Team, Match
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        # 清掉这些队的旧历史
        db.query(Match).filter(
            ((Match.home_team_id == home_id) & (Match.away_team_id == away_id))
            | ((Match.home_team_id == away_id) & (Match.away_team_id == home_id))
        ).delete()
        from datetime import datetime, timezone
        m = Match(
            match_number=9999,
            stage="测试",
            kickoff_at=datetime.now(timezone.utc),
            home_team_id=home_id,
            away_team_id=away_id,
            home_score=home_score,
            away_score=away_score,
            status=status,
        )
        db.add(m)
        db.commit()
        return db, m.id

    def test_h2h_finds_past_match(self):
        from app.services.prediction import _query_h2h
        from app.db import Base, engine, SessionLocal
        from app.models import Team

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()

        # 创建两支测试队
        db.query(Team).filter(Team.fifa_code.in_(["H2H_H", "H2H_A"])).delete()
        h = Team(fifa_code="H2H_H", name_zh="H队", name_en="H", group_name="X", elo_rating=1500)
        a = Team(fifa_code="H2H_A", name_zh="A队", name_en="A", group_name="X", elo_rating=1500)
        db.add(h)
        db.add(a)
        db.commit()

        # 制造历史交锋：H 1-0 A
        self._setup_db_with_match(h.id, a.id, 1, 0)
        result = _query_h2h(db, h, a, lookback=5)
        db.close()

        assert result["sample"] == 1
        assert result["home_wins"] == 1
        assert result["away_wins"] == 0
        assert result["draws"] == 0
        assert "H队" in result["summary"]

    def test_h2h_handles_reversed_home_away(self):
        """H2H 应该不区分主客队，按 home 视角归一胜平负."""
        from app.services.prediction import _query_h2h
        from app.db import Base, engine, SessionLocal
        from app.models import Team, Match
        from datetime import datetime, timezone

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()

        db.query(Team).filter(Team.fifa_code.in_(["H2H_H2", "H2H_A2"])).delete()
        h = Team(fifa_code="H2H_H2", name_zh="H2", name_en="H2", group_name="X", elo_rating=1500)
        a = Team(fifa_code="H2H_A2", name_zh="A2", name_en="A2", group_name="X", elo_rating=1500)
        db.add(h); db.add(a); db.commit()

        # 旧比赛：A(此时是主队) 1-3 H(此时是客队) → H 视角应胜
        db.query(Match).filter(
            ((Match.home_team_id == a.id) & (Match.away_team_id == h.id))
        ).delete()
        m = Match(
            match_number=9998, stage="测试", kickoff_at=datetime.now(timezone.utc),
            home_team_id=a.id, away_team_id=h.id,
            home_score=1, away_score=3, status="finished",
        )
        db.add(m); db.commit()

        result = _query_h2h(db, h, a, lookback=5)
        db.close()

        # H 视角应记 1 胜
        assert result["sample"] == 1
        assert result["home_wins"] == 1
        assert result["away_wins"] == 0

    def test_h2h_no_data(self):
        from app.services.prediction import _query_h2h
        from app.db import Base, engine, SessionLocal
        from app.models import Team

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        db.query(Team).filter(Team.fifa_code.in_(["H2H_X1", "H2H_X2"])).delete()
        h = Team(fifa_code="H2H_X1", name_zh="X1", name_en="X1", group_name="X", elo_rating=1500)
        a = Team(fifa_code="H2H_X2", name_zh="X2", name_en="X2", group_name="X", elo_rating=1500)
        db.add(h); db.add(a); db.commit()

        result = _query_h2h(db, h, a, lookback=5)
        db.close()

        assert result["sample"] == 0
        assert result["summary"] == ""


# ---------- 端到端 ----------

class TestPredictMatch:
    def _mk_team(self, name_zh, elo=1500, fifa_rank=20, id=1, form=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            id=id, name_zh=name_zh, elo_rating=elo, fifa_rank=fifa_rank,
            recent_form_points=form,
        )

    def test_returns_pydantic_model(self):
        home = self._mk_team("巴西", elo=2050, fifa_rank=7, id=1)
        away = self._mk_team("巴拉圭", elo=1671, fifa_rank=32, id=2)
        match = self._mk_match()
        p = predict_match(home, away, match)
        assert p.match_id == 1
        # 概率已归一化，100 附近误差应极小
        assert abs(p.home_win_prob + p.draw_prob + p.away_win_prob - 100) < 0.1
        assert 1 <= p.stars <= 5
        assert len(p.reasons) >= 3
        assert ":" in p.recommended_score
        # v2 新字段
        assert ":" in p.outcome_aligned_score
        assert len(p.top_scores) == 3
        assert p.top_scores[0]["probability"] >= p.top_scores[1]["probability"]
        assert 0.0 < p.score_confidence <= 1.0
        # v2.1 新字段
        assert ":" in p.primary_score
        assert ":" in p.secondary_score
        assert 1 <= p.score_reliability_stars <= 5
        assert any("首选比分" in r for r in p.reasons)

    def test_predict_match_with_form_data(self):
        """有 form 数据时 λ 调整生效，h2h_summary=None."""
        home = self._mk_team("法国", elo=2050, fifa_rank=3, id=10, form=13)
        away = self._mk_team("德国", elo=2050, fifa_rank=9, id=11, form=5)
        match = self._mk_match()
        p = predict_match(home, away, match)
        # 主场 form 优势 → home_win 应当显著 > away_win
        assert p.home_win_prob > p.away_win_prob
        # 理由中应包含 form 信息
        assert any("近 5 场" in r for r in p.reasons)
        # recent_form 字段应填充
        assert p.home_recent_form is not None
        assert p.away_recent_form is not None

    def test_predict_match_without_form_data(self):
        """无 form 数据时预测不崩."""
        home = self._mk_team("法国", elo=2050, fifa_rank=3, id=20)
        away = self._mk_team("德国", elo=2050, fifa_rank=9, id=21)
        match = self._mk_match()
        p = predict_match(home, away, match)
        assert p.home_recent_form is None
        assert p.away_recent_form is None
        # 理由中应不出现 form 相关
        assert not any("近 5 场" in r for r in p.reasons)

    def _mk_match(self):
        from types import SimpleNamespace
        return SimpleNamespace(id=1)
