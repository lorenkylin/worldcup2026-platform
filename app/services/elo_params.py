"""统一的 Elo→Poisson λ 参数转换.

所有依赖 Elo 分差计算期望进球 λ 的服务都应从此模块导入 elo_to_lambda，
避免 prediction.py / monte_carlo.py 之间出现参数漂移。
"""

from app.config import settings


def elo_to_lambda(home_elo: float, away_elo: float) -> tuple[float, float]:
    """将 Elo 分差转换为两队期望进球（含中立/主场优势）。"""
    diff = home_elo - away_elo + settings.poisson_home_advantage
    home_lambda = settings.poisson_base_lambda + diff * settings.poisson_goal_per_elo_diff
    away_lambda = settings.poisson_base_lambda - diff * settings.poisson_goal_per_elo_diff
    floor = settings.poisson_lambda_floor
    return max(floor, home_lambda), max(floor, away_lambda)
