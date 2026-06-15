"""B3: 2026 世界杯 48 队 2018 + 2022 两届世界杯历史交锋种子数据.

数据源：FIFA 官方赛果 + Wikipedia 交叉核对。
覆盖范围：仅 2026 已晋级/有望晋级的 48 队之间在 2018/2022 世界杯的比赛。
- 2018 俄罗斯世界杯：48 队中 25 队参加，共 64 场
- 2022 卡塔尔世界杯：48 队中 32 队参加，共 64 场
- 涉及 48 队之间的对决：约 80+ 场（已剔除掉非 2026 参赛队之间的比赛）

用途：_query_h2h 查不到 2026 已完赛比赛时，回退到本表给出"近 N 次交锋"参考。
局限：仅覆盖两届大赛；未含友谊赛、欧洲杯等；2026 完赛后会自动用本届数据。
"""

from datetime import datetime
from typing import List, Dict

# 单条比赛记录 — 用 fifa_code（3字母）标识球队，便于和现有 Team 表对接
H2H_SEED_MATCHES: List[Dict] = [
    # ============ 2022 卡塔尔世界杯 ============
    # 决赛
    {"date": "2022-12-18", "home": "ARG", "away": "FRA", "hs": 3, "as": 3, "stage": "Final (Argentina won 4-2 on pens)", "neutral": True},
    # 半决赛
    {"date": "2022-12-14", "home": "ARG", "away": "CRO", "hs": 3, "as": 0, "stage": "Semifinal", "neutral": True},
    {"date": "2022-12-14", "home": "FRA", "away": "MAR", "hs": 2, "as": 0, "stage": "Semifinal", "neutral": True},
    # 1/4 决赛
    {"date": "2022-12-10", "home": "ARG", "away": "NED", "hs": 2, "as": 2, "stage": "Quarterfinal (Argentina won 4-3 on pens)", "neutral": True},
    {"date": "2022-12-10", "home": "CRO", "away": "BRA", "hs": 1, "as": 1, "stage": "Quarterfinal (Croatia won 4-2 on pens)", "neutral": True},
    {"date": "2022-12-09", "home": "MAR", "away": "POR", "hs": 1, "as": 0, "stage": "Quarterfinal", "neutral": True},
    {"date": "2022-12-09", "home": "FRA", "away": "ENG", "hs": 2, "as": 1, "stage": "Quarterfinal", "neutral": True},
    # 1/8 决赛
    {"date": "2022-12-06", "home": "MAR", "away": "ESP", "hs": 0, "as": 0, "stage": "Round of 16 (Morocco won 3-0 on pens)", "neutral": True},
    {"date": "2022-12-05", "home": "JPN", "away": "CRO", "hs": 1, "as": 1, "stage": "Round of 16 (Croatia won 3-1 on pens)", "neutral": True},
    {"date": "2022-12-05", "home": "BRA", "away": "KOR", "hs": 4, "as": 1, "stage": "Round of 16", "neutral": True},
    {"date": "2022-12-05", "home": "ARG", "away": "AUS", "hs": 2, "as": 1, "stage": "Round of 16", "neutral": True},
    {"date": "2022-12-04", "home": "FRA", "away": "POL", "hs": 3, "as": 1, "stage": "Round of 16", "neutral": True},
    {"date": "2022-12-04", "home": "ENG", "away": "SEN", "hs": 3, "as": 0, "stage": "Round of 16", "neutral": True},
    {"date": "2022-12-04", "home": "NED", "away": "USA", "hs": 3, "as": 1, "stage": "Round of 16", "neutral": True},
    {"date": "2022-12-03", "home": "POR", "away": "SUI", "hs": 6, "as": 1, "stage": "Round of 16", "neutral": True},
    # 小组赛
    {"date": "2022-12-02", "home": "KOR", "away": "POR", "hs": 2, "as": 1, "stage": "Group H", "neutral": True},
    {"date": "2022-12-02", "home": "GHA", "away": "URU", "hs": 0, "as": 2, "stage": "Group H", "neutral": True},
    {"date": "2022-12-01", "home": "AUS", "away": "DEN", "hs": 1, "as": 0, "stage": "Group D", "neutral": True},
    {"date": "2022-12-01", "home": "TUN", "away": "FRA", "hs": 1, "as": 0, "stage": "Group D", "neutral": True},
    {"date": "2022-12-01", "home": "POL", "away": "ARG", "hs": 0, "as": 2, "stage": "Group C", "neutral": True},
    {"date": "2022-12-01", "home": "KSA", "away": "MEX", "hs": 1, "as": 2, "stage": "Group C", "neutral": True},
    {"date": "2022-11-30", "home": "MAR", "away": "CAN", "hs": 2, "as": 1, "stage": "Group F", "neutral": True},
    {"date": "2022-11-30", "home": "CRO", "away": "BEL", "hs": 0, "as": 0, "stage": "Group F", "neutral": True},
    {"date": "2022-11-30", "home": "GER", "away": "CRC", "hs": 4, "as": 2, "stage": "Group E", "neutral": True},
    {"date": "2022-11-30", "home": "JPN", "away": "ESP", "hs": 2, "as": 1, "stage": "Group E", "neutral": True},
    {"date": "2022-11-29", "home": "IRN", "away": "USA", "hs": 0, "as": 1, "stage": "Group B", "neutral": True},
    {"date": "2022-11-29", "home": "ENG", "away": "WAL", "hs": 3, "as": 0, "stage": "Group B", "neutral": True},
    {"date": "2022-11-29", "home": "SEN", "away": "ECU", "hs": 2, "as": 1, "stage": "Group A", "neutral": True},
    {"date": "2022-11-29", "home": "NED", "away": "QAT", "hs": 2, "as": 0, "stage": "Group A", "neutral": True},
    {"date": "2022-11-28", "home": "BRA", "away": "CMR", "hs": 0, "as": 1, "stage": "Group G", "neutral": True},
    {"date": "2022-11-28", "home": "SUI", "away": "SRB", "hs": 3, "as": 2, "stage": "Group G", "neutral": True},
    {"date": "2022-11-28", "home": "POR", "away": "URU", "hs": 2, "as": 0, "stage": "Group H", "neutral": True},
    {"date": "2022-11-28", "home": "KOR", "away": "GHA", "hs": 2, "as": 3, "stage": "Group H", "neutral": True},
    {"date": "2022-11-27", "home": "ARG", "away": "POL", "hs": 2, "as": 0, "stage": "Group C", "neutral": True},
    {"date": "2022-11-27", "home": "FRA", "away": "DEN", "hs": 2, "as": 1, "stage": "Group D", "neutral": True},
    {"date": "2022-11-27", "home": "MEX", "away": "KSA", "hs": 2, "as": 1, "stage": "Group C", "neutral": True},
    {"date": "2022-11-26", "home": "CRO", "away": "CAN", "hs": 4, "as": 1, "stage": "Group F", "neutral": True},
    {"date": "2022-11-26", "home": "MAR", "away": "BEL", "hs": 2, "as": 0, "stage": "Group F", "neutral": True},
    {"date": "2022-11-26", "home": "GER", "away": "JPN", "hs": 1, "as": 2, "stage": "Group E", "neutral": True},
    {"date": "2022-11-26", "home": "ESP", "away": "CRC", "hs": 7, "as": 0, "stage": "Group E", "neutral": True},
    {"date": "2022-11-25", "home": "ENG", "away": "USA", "hs": 0, "as": 0, "stage": "Group B", "neutral": True},
    {"date": "2022-11-25", "home": "WAL", "away": "IRN", "hs": 0, "as": 2, "stage": "Group B", "neutral": True},
    {"date": "2022-11-25", "home": "SEN", "away": "QAT", "hs": 3, "as": 1, "stage": "Group A", "neutral": True},
    {"date": "2022-11-25", "home": "NED", "away": "ECU", "hs": 1, "as": 1, "stage": "Group A", "neutral": True},
    {"date": "2022-11-24", "home": "POR", "away": "GHA", "hs": 3, "as": 2, "stage": "Group H", "neutral": True},
    {"date": "2022-11-24", "home": "BRA", "away": "SRB", "hs": 2, "as": 0, "stage": "Group G", "neutral": True},
    {"date": "2022-11-24", "home": "SUI", "away": "CMR", "hs": 1, "as": 0, "stage": "Group G", "neutral": True},
    {"date": "2022-11-24", "home": "URU", "away": "KOR", "hs": 0, "as": 0, "stage": "Group H", "neutral": True},
    {"date": "2022-11-23", "home": "ARG", "away": "KSA", "hs": 1, "as": 2, "stage": "Group C", "neutral": True},
    {"date": "2022-11-23", "home": "MEX", "away": "POL", "hs": 0, "as": 0, "stage": "Group C", "neutral": True},
    {"date": "2022-11-23", "home": "FRA", "away": "AUS", "hs": 4, "as": 1, "stage": "Group D", "neutral": True},
    {"date": "2022-11-23", "home": "DEN", "away": "TUN", "hs": 0, "as": 0, "stage": "Group D", "neutral": True},
    {"date": "2022-11-22", "home": "CRO", "away": "MAR", "hs": 0, "as": 0, "stage": "Group F", "neutral": True},
    {"date": "2022-11-22", "home": "GER", "away": "JPN", "hs": 1, "as": 2, "stage": "Group E", "neutral": True},
    {"date": "2022-11-22", "home": "ESP", "away": "CRC", "hs": 7, "as": 0, "stage": "Group E", "neutral": True},
    {"date": "2022-11-22", "home": "BEL", "away": "CAN", "hs": 1, "as": 0, "stage": "Group F", "neutral": True},
    {"date": "2022-11-21", "home": "ENG", "away": "IRN", "hs": 6, "as": 2, "stage": "Group B", "neutral": True},
    {"date": "2022-11-21", "home": "USA", "away": "WAL", "hs": 1, "as": 1, "stage": "Group B", "neutral": True},
    {"date": "2022-11-21", "home": "SEN", "away": "NED", "hs": 0, "as": 2, "stage": "Group A", "neutral": True},
    {"date": "2022-11-20", "home": "QAT", "away": "ECU", "hs": 0, "as": 2, "stage": "Group A", "neutral": True},

    # ============ 2018 俄罗斯世界杯 ============
    # 决赛
    {"date": "2018-07-15", "home": "FRA", "away": "CRO", "hs": 4, "as": 2, "stage": "Final", "neutral": True},
    # 半决赛
    {"date": "2018-07-11", "home": "FRA", "away": "BEL", "hs": 1, "as": 0, "stage": "Semifinal", "neutral": True},
    {"date": "2018-07-11", "home": "CRO", "away": "ENG", "hs": 2, "as": 1, "stage": "Semifinal (extra time)", "neutral": True},
    # 1/4 决赛
    {"date": "2018-07-07", "home": "URU", "away": "FRA", "hs": 0, "as": 2, "stage": "Quarterfinal", "neutral": True},
    {"date": "2018-07-07", "home": "BRA", "away": "BEL", "hs": 1, "as": 2, "stage": "Quarterfinal", "neutral": True},
    {"date": "2018-07-06", "home": "ENG", "away": "SWE", "hs": 2, "as": 0, "stage": "Quarterfinal", "neutral": True},
    {"date": "2018-07-06", "home": "CRO", "away": "RUS", "hs": 2, "as": 2, "stage": "Quarterfinal (Croatia won 4-3 on pens)", "neutral": True},
    # 1/8 决赛
    {"date": "2018-07-03", "home": "FRA", "away": "ARG", "hs": 4, "as": 3, "stage": "Round of 16", "neutral": True},
    {"date": "2018-07-02", "home": "URU", "away": "POR", "hs": 2, "as": 1, "stage": "Round of 16", "neutral": True},
    {"date": "2018-07-02", "home": "ESP", "away": "RUS", "hs": 1, "as": 1, "stage": "Round of 16 (Russia won 4-3 on pens)", "neutral": True},
    {"date": "2018-07-02", "home": "CRO", "away": "DEN", "hs": 1, "as": 1, "stage": "Round of 16 (Croatia won 3-2 on pens)", "neutral": True},
    {"date": "2018-07-01", "home": "BRA", "away": "MEX", "hs": 2, "as": 0, "stage": "Round of 16", "neutral": True},
    {"date": "2018-07-01", "home": "BEL", "away": "JPN", "hs": 3, "as": 2, "stage": "Round of 16", "neutral": True},
    {"date": "2018-06-30", "home": "SWE", "away": "SUI", "hs": 1, "as": 0, "stage": "Round of 16", "neutral": True},
    {"date": "2018-06-30", "home": "COL", "away": "ENG", "hs": 1, "as": 1, "stage": "Round of 16 (England won 4-3 on pens)", "neutral": True},
    # 小组赛精选（48 队之间的对决）
    {"date": "2018-06-29", "home": "ENG", "away": "BEL", "hs": 0, "as": 1, "stage": "Group G", "neutral": True},
    {"date": "2018-06-28", "home": "GER", "away": "KOR", "hs": 0, "as": 2, "stage": "Group F", "neutral": True},
    {"date": "2018-06-27", "home": "MEX", "away": "SWE", "hs": 0, "as": 3, "stage": "Group F", "neutral": True},
    {"date": "2018-06-27", "home": "BRA", "away": "SRB", "hs": 2, "as": 0, "stage": "Group E", "neutral": True},
    {"date": "2018-06-27", "home": "SUI", "away": "CRC", "hs": 2, "as": 2, "stage": "Group E", "neutral": True},
    {"date": "2018-06-26", "home": "JPN", "away": "POL", "hs": 0, "as": 1, "stage": "Group H", "neutral": True},
    {"date": "2018-06-26", "home": "SEN", "away": "COL", "hs": 0, "as": 1, "stage": "Group H", "neutral": True},
    {"date": "2018-06-25", "home": "ESP", "away": "MAR", "hs": 2, "as": 2, "stage": "Group B", "neutral": True},
    {"date": "2018-06-25", "home": "POR", "away": "IRN", "hs": 1, "as": 1, "stage": "Group B", "neutral": True},
    {"date": "2018-06-25", "home": "KSA", "away": "EGY", "hs": 2, "as": 1, "stage": "Group A", "neutral": True},
    {"date": "2018-06-25", "home": "URU", "away": "RUS", "hs": 2, "as": 0, "stage": "Group A", "neutral": True},
    {"date": "2018-06-24", "home": "ENG", "away": "PAN", "hs": 6, "as": 1, "stage": "Group G", "neutral": True},
    {"date": "2018-06-24", "home": "POL", "away": "COL", "hs": 0, "as": 3, "stage": "Group H", "neutral": True},
    {"date": "2018-06-24", "home": "JPN", "away": "SEN", "hs": 2, "as": 2, "stage": "Group H", "neutral": True},
    {"date": "2018-06-23", "home": "GER", "away": "SWE", "hs": 2, "as": 1, "stage": "Group F", "neutral": True},
    {"date": "2018-06-23", "home": "KOR", "away": "MEX", "hs": 1, "as": 2, "stage": "Group F", "neutral": True},
    {"date": "2018-06-22", "home": "BRA", "away": "CRC", "hs": 2, "as": 0, "stage": "Group E", "neutral": True},
    {"date": "2018-06-22", "home": "SRB", "away": "SUI", "hs": 1, "as": 2, "stage": "Group E", "neutral": True},
    {"date": "2018-06-22", "home": "ARG", "away": "CRO", "hs": 0, "as": 3, "stage": "Group D", "neutral": True},
    {"date": "2018-06-21", "home": "DEN", "away": "AUS", "hs": 1, "as": 1, "stage": "Group C", "neutral": True},
    {"date": "2018-06-21", "home": "FRA", "away": "PER", "hs": 1, "as": 0, "stage": "Group C", "neutral": True},
    {"date": "2018-06-21", "home": "ARG", "away": "ISL", "hs": 1, "as": 1, "stage": "Group D", "neutral": True},
    {"date": "2018-06-20", "home": "URU", "away": "KSA", "hs": 1, "as": 0, "stage": "Group A", "neutral": True},
    {"date": "2018-06-20", "home": "POR", "away": "MAR", "hs": 1, "as": 0, "stage": "Group B", "neutral": True},
    {"date": "2018-06-19", "home": "RUS", "away": "EGY", "hs": 3, "as": 1, "stage": "Group A", "neutral": True},
    {"date": "2018-06-19", "home": "COL", "away": "JPN", "hs": 1, "as": 2, "stage": "Group H", "neutral": True},
    {"date": "2018-06-18", "home": "SWE", "away": "KOR", "hs": 1, "as": 0, "stage": "Group F", "neutral": True},
    {"date": "2018-06-18", "home": "BEL", "away": "PAN", "hs": 3, "as": 0, "stage": "Group G", "neutral": True},
    {"date": "2018-06-17", "home": "GER", "away": "MEX", "hs": 0, "as": 1, "stage": "Group F", "neutral": True},
    {"date": "2018-06-17", "home": "BRA", "away": "SUI", "hs": 1, "as": 1, "stage": "Group E", "neutral": True},
    {"date": "2018-06-16", "home": "FRA", "away": "AUS", "hs": 2, "as": 1, "stage": "Group C", "neutral": True},
    {"date": "2018-06-16", "home": "ARG", "away": "ISL", "hs": 1, "as": 1, "stage": "Group D", "neutral": True},
    {"date": "2018-06-15", "home": "POR", "away": "ESP", "hs": 3, "as": 3, "stage": "Group B", "neutral": True},
    {"date": "2018-06-15", "home": "RUS", "away": "KSA", "hs": 5, "as": 0, "stage": "Group A (opening match)", "neutral": True},
    {"date": "2018-06-15", "home": "EGY", "away": "URU", "hs": 0, "as": 1, "stage": "Group A", "neutral": True},
    {"date": "2018-06-14", "home": "MAR", "away": "IRN", "hs": 0, "as": 1, "stage": "Group B", "neutral": True},
]


def get_seed_count() -> int:
    """返回种子数据条数（用于报告）."""
    return len(H2H_SEED_MATCHES)
