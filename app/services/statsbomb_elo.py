"""StatsBomb Open Data Elo 评分训练与加载.

数据源: StatsBomb Open Data (https://github.com/statsbomb/open-data)
覆盖赛事: 世界杯 2018/2022、欧洲杯 2020/2024、美洲杯 2024、非洲杯 2023
总场数: ~314 场国际赛
使用条款: 公开研究/分析需标注 StatsBomb 并使用其 logo

由于 StatsBomb Open Data 缺少 2023-2026 友谊赛/预选赛, 且部分 2026 参赛队无数据,
本模块训练的 Elo 仅作为 Hicruben 主模型的对比数据源, 不作为默认模型.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from app.services.elo import INIT_RATING, K_FACTOR_WC, elo_update

# === 配置 ===
RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seed" / "statsbomb" / "raw"
OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seed" / "statsbomb" / "statsbomb_elo.json"

# competition_id / season_id -> 赛事名称
COMPETITIONS: List[Tuple[int, int, str]] = [
    (43, 3, "FIFA World Cup 2018"),
    (43, 106, "FIFA World Cup 2022"),
    (55, 43, "UEFA Euro 2020"),
    (55, 282, "UEFA Euro 2024"),
    (223, 282, "Copa América 2024"),
    (1267, 107, "Africa Cup of Nations 2023"),
]

# StatsBomb 英文队名 -> FIFA 3-letter code
# 注意: 名称以 StatsBomb Open Data 实际出现的为准
SB_NAME_TO_FIFA: Dict[str, str] = {
    # CONMEBOL
    "Argentina": "ARG",
    "Bolivia": "BOL",
    "Brazil": "BRA",
    "Chile": "CHI",
    "Colombia": "COL",
    "Ecuador": "ECU",
    "Paraguay": "PAR",
    "Peru": "PER",
    "Uruguay": "URU",
    "Venezuela": "VEN",
    # CONCACAF
    "Canada": "CAN",
    "Costa Rica": "CRC",
    "Jamaica": "JAM",
    "Mexico": "MEX",
    "Panama": "PAN",
    "United States": "USA",
    # UEFA
    "Albania": "ALB",
    "Austria": "AUT",
    "Belgium": "BEL",
    "Croatia": "CRO",
    "Czech Republic": "CZE",
    "Denmark": "DEN",
    "England": "ENG",
    "Finland": "FIN",
    "France": "FRA",
    "Georgia": "GEO",
    "Germany": "GER",
    "Hungary": "HUN",
    "Iceland": "ISL",
    "Italy": "ITA",
    "Netherlands": "NED",
    "North Macedonia": "MKD",
    "Poland": "POL",
    "Portugal": "POR",
    "Romania": "ROU",
    "Russia": "RUS",
    "Scotland": "SCO",
    "Serbia": "SRB",
    "Slovakia": "SVK",
    "Slovenia": "SVN",
    "Spain": "ESP",
    "Sweden": "SWE",
    "Switzerland": "SUI",
    "Turkey": "TUR",
    "Ukraine": "UKR",
    "Wales": "WAL",
    # CAF
    "Algeria": "ALG",
    "Angola": "ANG",
    "Burkina Faso": "BFA",
    "Cameroon": "CMR",
    "Cape Verde Islands": "CPV",
    "Congo DR": "COD",
    "Côte d'Ivoire": "CIV",
    "Egypt": "EGY",
    "Equatorial Guinea": "EQG",
    "Gambia": "GAM",
    "Ghana": "GHA",
    "Guinea": "GUI",
    "Guinea-Bissau": "GNB",
    "Mali": "MLI",
    "Mauritania": "MTN",
    "Morocco": "MAR",
    "Mozambique": "MOZ",
    "Namibia": "NAM",
    "Nigeria": "NGA",
    "Senegal": "SEN",
    "South Africa": "RSA",
    "Tanzania": "TAN",
    "Tunisia": "TUN",
    "Zambia": "ZAM",
    # AFC / OFC
    "Australia": "AUS",
    "Iran": "IRN",
    "Japan": "JPN",
    "Qatar": "QAT",
    "Saudi Arabia": "KSA",
    "South Korea": "KOR",
}

# 反向映射，用于调试/日志
FIFA_TO_SB_NAME: Dict[str, str] = {v: k for k, v in SB_NAME_TO_FIFA.items()}


def _raw_path(comp_id: int, season_id: int) -> Path:
    return RAW_DIR / f"{comp_id}_{season_id}.json"


def _download_url(comp_id: int, season_id: int) -> str:
    return (
        "https://raw.githubusercontent.com/statsbomb/open-data/master"
        f"/data/matches/{comp_id}/{season_id}.json"
    )


def ensure_raw_files(max_retries: int = 3) -> List[Path]:
    """下载 StatsBomb 比赛文件到 data/seed/statsbomb/raw/.

    返回已存在的文件路径列表。下载失败时打印警告但继续。
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for comp_id, season_id, name in COMPETITIONS:
        path = _raw_path(comp_id, season_id)
        if path.exists():
            paths.append(path)
            continue
        url = _download_url(comp_id, season_id)
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                path.write_bytes(resp.content)
                paths.append(path)
                print(f"[statsbomb] 已下载 {name}: {path}")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[statsbomb] 下载 {name} 第 {attempt}/{max_retries} 次失败: {exc}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                else:
                    print(f"[statsbomb] {name} 下载跳过")
    return paths


def _parse_match(m: dict) -> Optional[dict]:
    """从 StatsBomb match JSON 或精简格式提取训练所需字段.

    支持两种输入格式:
    1. 完整 StatsBomb JSON: {"home_team": {"home_team_name": ...}, "away_team": {...}, ...}
    2. 精简 JSON: {"date": "...", "home": "...", "away": "...", "hg": int, "ag": int}
    """
    # 精简格式
    if "home" in m and "away" in m:
        home_name = m.get("home")
        away_name = m.get("away")
        home_score = m.get("hg")
        away_score = m.get("ag")
        match_date = m.get("date")
        competition = m.get("competition", "StatsBomb")
    else:
        # 完整 StatsBomb 格式
        home_name = m.get("home_team", {}).get("home_team_name")
        away_name = m.get("away_team", {}).get("away_team_name")
        home_score = m.get("home_score")
        away_score = m.get("away_score")
        match_date = m.get("match_date")
        competition = m.get("competition", {}).get("competition_name", "Unknown")

    if not all([home_name, away_name, home_score is not None, away_score is not None, match_date]):
        return None
    home_code = SB_NAME_TO_FIFA.get(home_name)
    away_code = SB_NAME_TO_FIFA.get(away_name)
    if home_code is None or away_code is None:
        # 未知队名仅记录，不中断
        return None
    if home_score > away_score:
        home_result = 1.0
    elif home_score == away_score:
        home_result = 0.5
    else:
        home_result = 0.0
    return {
        "date": match_date,
        "home_code": home_code,
        "away_code": away_code,
        "home_score": int(home_score),
        "away_score": int(away_score),
        "home_result": home_result,
        "competition": competition,
    }


def load_parsed_matches() -> List[dict]:
    """加载所有已下载的 raw 文件并解析为统一格式."""
    matches: List[dict] = []
    unknown_names: set = set()
    for comp_id, season_id, _ in COMPETITIONS:
        path = _raw_path(comp_id, season_id)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[statsbomb] 解析 {path} 失败: {exc}")
            continue
        for m in data:
            # 判断格式，提取原始队名用于未知队名报告
            if "home" in m and "away" in m:
                home_name = m.get("home")
                away_name = m.get("away")
            else:
                home_name = m.get("home_team", {}).get("home_team_name")
                away_name = m.get("away_team", {}).get("away_team_name")
            parsed = _parse_match(m)
            if parsed:
                matches.append(parsed)
            else:
                if home_name and home_name not in SB_NAME_TO_FIFA:
                    unknown_names.add(home_name)
                if away_name and away_name not in SB_NAME_TO_FIFA:
                    unknown_names.add(away_name)
    if unknown_names:
        print(f"[statsbomb] 警告: 以下 {len(unknown_names)} 个队名未映射: {sorted(unknown_names)}")
    matches.sort(key=lambda x: x["date"])
    return matches


def train_statsbomb_elo() -> Dict:
    """用 StatsBomb 国际赛结果训练 Elo 评分.

    使用与 Hicruben 相同的 K=60, 但 home_bonus=0(大赛均为中立场).
    返回包含 ratings / 元数据 / 缺失球队的字典。
    """
    matches = load_parsed_matches()
    if not matches:
        return {
            "ratings": {},
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "matchesApplied": 0,
            "sourceCompetitions": [name for _, _, name in COMPETITIONS],
            "missingTeams": [],
            "note": "No StatsBomb raw data found. Run scripts/download_statsbomb.py first.",
        }

    ratings: Dict[str, float] = {}
    for m in matches:
        hc, ac = m["home_code"], m["away_code"]
        ra = ratings.get(hc, INIT_RATING)
        rb = ratings.get(ac, INIT_RATING)
        new_a, new_b = elo_update(ra, rb, m["home_result"], home_bonus_a=0.0, k=K_FACTOR_WC)
        ratings[hc] = new_a
        ratings[ac] = new_b

    # 转为整数并只保留出现在 2026 DB 的 48 队？不，保留所有训练过的队，便于通用查询
    int_ratings = {code: int(round(rating)) for code, rating in ratings.items()}

    return {
        "ratings": int_ratings,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "matchesApplied": len(matches),
        "sourceCompetitions": [name for _, _, name in COMPETITIONS],
        "missingTeams": [],  # 运行时由调用方与当前球队列表比对
        "extractionNote": (
            "Data extracted from StatsBomb Open Data via WebFetch. "
            "Some matches may be missing due to extraction limits. "
            "Run scripts/download_statsbomb.py in an internet-enabled environment for the complete dataset."
        ),
    }


def build_statsbomb_elo_json(force_download: bool = False) -> Path:
    """确保 raw 文件存在、训练 Elo 并写入 JSON."""
    if force_download:
        ensure_raw_files()
    else:
        # 如果没有任何 raw 文件，尝试下载
        if not any(_raw_path(cid, sid).exists() for cid, sid, _ in COMPETITIONS):
            print("[statsbomb] 未发现 raw 文件，开始下载...")
            ensure_raw_files()

    result = train_statsbomb_elo()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[statsbomb] 已生成 Elo 文件: {OUTPUT_PATH} ({result['matchesApplied']} 场)")
    return OUTPUT_PATH


# === 运行时加载 ===

_statsbomb_cache: Optional[Dict] = None


def load_statsbomb_ratings() -> Dict:
    """加载生成的 StatsBomb Elo JSON（带内存缓存）."""
    global _statsbomb_cache
    if _statsbomb_cache is not None:
        return _statsbomb_cache
    if not OUTPUT_PATH.exists():
        # 尝试生成一次
        try:
            build_statsbomb_elo_json()
        except Exception as exc:  # noqa: BLE001
            print(f"[statsbomb] 自动生成失败: {exc}")
            return {"ratings": {}, "generatedAt": None, "matchesApplied": 0}
    data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    _statsbomb_cache = data
    return data


def get_statsbomb_team_elo(fifa_code: str) -> Optional[int]:
    """根据 FIFA 3-letter code 查 StatsBomb Elo 评分."""
    data = load_statsbomb_ratings()
    return data.get("ratings", {}).get(fifa_code.upper())


def clear_statsbomb_cache() -> None:
    """清除内存缓存（用于测试或数据更新后）."""
    global _statsbomb_cache
    _statsbomb_cache = None
