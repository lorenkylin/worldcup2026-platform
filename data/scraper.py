"""worldcupstats.football 赛程/球队/球场数据抓取与清洗.

说明：
- 仅抓取公开赛程页（/schedule/）中的文本信息。
- 队徽/国旗 SVG 不下载，避免版权风险；使用 emoji 国旗替代。
- 队名中文化映射基于 FIFA 官方 48 强名单手工维护；若新增队名则回退英文名。
"""

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup


BASE_URL = "https://worldcupstats.football"
SCHEDULE_URL = f"{BASE_URL}/schedule/"
OUTPUT_DIR = Path(__file__).resolve().parent / "fixtures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 球队英文名 -> (中文名, FIFA 代码)
TEAM_MAP = {
    "Mexico": ("墨西哥", "MEX"),
    "South Africa": ("南非", "RSA"),
    "Egypt": ("埃及", "EGY"),
    "Spain": ("西班牙", "ESP"),
    "Morocco": ("摩洛哥", "MAR"),
    "New Zealand": ("新西兰", "NZL"),
    "Brazil": ("巴西", "BRA"),
    "Italy": ("意大利", "ITA"),
    "United States": ("美国", "USA"),
    "Colombia": ("哥伦比亚", "COL"),
    "Germany": ("德国", "GER"),
    "Jamaica": ("牙买加", "JAM"),
    "Switzerland": ("瑞士", "SUI"),
    "Senegal": ("塞内加尔", "SEN"),
    "Argentina": ("阿根廷", "ARG"),
    "Croatia": ("克罗地亚", "CRO"),
    "France": ("法国", "FRA"),
    "Uzbekistan": ("乌兹别克斯坦", "UZB"),
    "England": ("英格兰", "ENG"),
    "Saudi Arabia": ("沙特阿拉伯", "KSA"),
    "Tunisia": ("突尼斯", "TUN"),
    "Iran": ("伊朗", "IRN"),
    "Japan": ("日本", "JPN"),
    "Qatar": ("卡塔尔", "QAT"),
    "Canada": ("加拿大", "CAN"),
    "Netherlands": ("荷兰", "NED"),
    "Australia": ("澳大利亚", "AUS"),
    "Denmark": ("丹麦", "DEN"),
    "Uruguay": ("乌拉圭", "URU"),
    "Korea Republic": ("韩国", "KOR"),
    "Portugal": ("葡萄牙", "POR"),
    "Ukraine": ("乌克兰", "UKR"),
    "Belgium": ("比利时", "BEL"),
    "Ecuador": ("厄瓜多尔", "ECU"),
    "Paraguay": ("巴拉圭", "PAR"),
    "Panama": ("巴拿马", "PAN"),
    "Algeria": ("阿尔及利亚", "ALG"),
    "Norway": ("挪威", "NOR"),
    "Serbia": ("塞尔维亚", "SRB"),
    "Turkey": ("土耳其", "TUR"),
    "Cameroon": ("喀麦隆", "CMR"),
    "Nigeria": ("尼日利亚", "NGA"),
    "Ghana": ("加纳", "GHA"),
    "Costa Rica": ("哥斯达黎加", "CRC"),
    "Honduras": ("洪都拉斯", "HON"),
    "Iraq": ("伊拉克", "IRQ"),
    "Indonesia": ("印度尼西亚", "IDN"),
    "Poland": ("波兰", "POL"),
    "Venezuela": ("委内瑞拉", "VEN"),
    "Sweden": ("瑞典", "SWE"),
    "Czech Republic": ("捷克", "CZE"),
    "Peru": ("秘鲁", "PER"),
    "Russia": ("俄罗斯", "RUS"),
    "Greece": ("希腊", "GRE"),
    "Chile": ("智利", "CHI"),
    "Wales": ("威尔士", "WAL"),
    "Scotland": ("苏格兰", "SCO"),
    "Hungary": ("匈牙利", "HUN"),
    "Austria": ("奥地利", "AUT"),
    "South Korea": ("韩国", "KOR"),
    "Bosnia & Herzegovina": ("波黑", "BIH"),
    "Haiti": ("海地", "HAI"),
    "Curacao": ("库拉索", "CUW"),
    "Ivory Coast": ("科特迪瓦", "CIV"),
    "Cape Verde": ("佛得角", "CPV"),
    "Jordan": ("约旦", "JOR"),
    "DR Congo": ("民主刚果", "COD"),
}

# 国旗 emoji（部分国家队）
FLAG_EMOJI = {
    "MEX": "🇲🇽", "RSA": "🇿🇦", "EGY": "🇪🇬", "ESP": "🇪🇸", "MAR": "🇲🇦",
    "NZL": "🇳🇿", "BRA": "🇧🇷", "ITA": "🇮🇹", "USA": "🇺🇸", "COL": "🇨🇴",
    "GER": "🇩🇪", "JAM": "🇯🇲", "SUI": "🇨🇭", "SEN": "🇸🇳", "ARG": "🇦🇷",
    "CRO": "🇭🇷", "FRA": "🇫🇷", "UZB": "🇺🇿", "ENG": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "KSA": "🇸🇦",
    "TUN": "🇹🇳", "IRN": "🇮🇷", "JPN": "🇯🇵", "QAT": "🇶🇦", "CAN": "🇨🇦",
    "NED": "🇳🇱", "AUS": "🇦🇺", "DEN": "🇩🇰", "URU": "🇺🇾", "KOR": "🇰🇷",
    "POR": "🇵🇹", "UKR": "🇺🇦", "BEL": "🇧🇪", "ECU": "🇪🇨", "PAR": "🇵🇾",
    "PAN": "🇵🇦", "ALG": "🇩🇿", "NOR": "🇳🇴", "SRB": "🇷🇸", "TUR": "🇹🇷",
    "CMR": "🇨🇲", "NGA": "🇳🇬", "GHA": "🇬🇭", "CRC": "🇨🇷", "HON": "🇭🇳",
    "IRQ": "🇮🇶", "IDN": "🇮🇩", "POL": "🇵🇱", "VEN": "🇻🇪", "SWE": "🇸🇪",
    "CZE": "🇨🇿", "PER": "🇵🇪", "RUS": "🇷🇺", "GRE": "🇬🇷", "CHI": "🇨🇱",
    "WAL": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "SCO": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "HUN": "🇭🇺", "AUT": "🇦🇹",
}


def fetch_html(url: str) -> BeautifulSoup:
    """获取页面并解析为 BeautifulSoup."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        html = response.read()
    return BeautifulSoup(html, "html.parser")


def parse_utc(attr: str) -> datetime:
    """解析 worldcupstats 的 data-utc 属性.

    示例：2026-06-11T15:00:00:00-04:00 -> 2026-06-11T19:00:00+00:00
    """
    # 去除秒与毫秒之间多余的分隔
    cleaned = re.sub(r"T(\d{2}):(\d{2}):(\d{2}):(\d{2})", r"T\1:\2:\3.\4", attr)
    # 尝试直接解析
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        # 兜底：按原格式提取时间戳与时区
        m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}):(\d{2})([+-]\d{2}:\d{2})", attr)
        if m:
            iso = f"{m.group(1)}{m.group(3)}"
            return datetime.fromisoformat(iso)
        raise


def extract_score(score_text: str) -> tuple:
    """从比分文本提取主客得分，未开始返回 None."""
    score_text = score_text.replace("—", "-").strip()
    parts = [p.strip() for p in score_text.split("-")]
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return None, None


def team_info(en_name: str) -> tuple:
    """根据英文队名返回中文名与 FIFA 代码."""
    en_name = en_name.strip()
    if en_name in TEAM_MAP:
        return TEAM_MAP[en_name]
    # 尝试模糊匹配（忽略大小写/空格）
    for key, value in TEAM_MAP.items():
        if key.lower() == en_name.lower():
            return value
    return en_name, en_name[:3].upper()


def scrape_schedule() -> tuple:
    """抓取赛程页，返回 (matches, teams, stadiums)."""
    print(f"抓取 {SCHEDULE_URL}")
    soup = fetch_html(SCHEDULE_URL)

    teams: dict[str, dict] = {}
    stadiums: dict[str, dict] = {}
    matches: list[dict] = []
    match_counter = 0

    date_groups = soup.find_all("div", class_="date-group")
    for group in date_groups:
        header = group.find("div", class_="date-group__header")
        if not header:
            continue
        date_text = header.get_text(strip=True)

        team_cards = group.find_all("div", class_="match-card__teams")
        meta_cards = group.find_all("div", class_="match-card__meta")

        for teams_card, meta_card in zip(team_cards, meta_cards):
            match_counter += 1
            spans = teams_card.find_all("span", class_="match-card__team")
            home_en = spans[0].get_text(strip=True) if len(spans) > 0 else "TBD"
            away_en = spans[1].get_text(strip=True) if len(spans) > 1 else "TBD"

            score_span = teams_card.find("span", class_="match-card__score")
            score_text = score_span.get_text(strip=True) if score_span else "vs"
            home_score, away_score = extract_score(score_text)

            meta_spans = meta_card.find_all("span")
            kickoff_at = None
            stadium_name = ""
            group_name = ""
            status = "scheduled"

            for span in meta_spans:
                cls = span.get("class", [])
                if "match-time" in cls:
                    utc_attr = span.get("data-utc")
                    if utc_attr:
                        kickoff_at = parse_utc(utc_attr)
                elif "badge" in cls:
                    badge = span.get_text(strip=True).lower()
                    if badge in ("finished", "ft"):
                        status = "finished"
                    elif badge in ("live", "in progress"):
                        status = "live"
                else:
                    text = span.get_text(strip=True)
                    if text.startswith("Group"):
                        group_name = text.replace("Group", "").strip()
                    elif text.startswith("Round of"):
                        group_name = ""
                    elif text and not stadium_name:
                        stadium_name = text

            # 球队去重并补全
            for en_name in (home_en, away_en):
                if en_name == "TBD" or not en_name:
                    continue
                if en_name not in teams:
                    zh, code = team_info(en_name)
                    teams[en_name] = {
                        "fifa_code": code,
                        "name_zh": zh,
                        "name_en": en_name,
                        "group_name": group_name,
                        "flag_emoji": FLAG_EMOJI.get(code, ""),
                    }
                elif group_name and not teams[en_name].get("group_name"):
                    teams[en_name]["group_name"] = group_name

            # 球场去重
            if stadium_name and stadium_name not in stadiums:
                stadiums[stadium_name] = {
                    "name_en": stadium_name,
                    "name_zh": stadium_name,
                    "city": stadium_name.split(",")[0].strip(),
                    "country": "USA",
                    "timezone": "America/New_York",
                }

            stage = "小组赛"
            if "Round of" in (group_name or ""):
                stage = "16强"
            elif any(x in date_text for x in ["Quarter", "Semi", "Final"]):
                # 简化：后续手动修正淘汰赛阶段
                stage = "淘汰赛"

            matches.append(
                {
                    "match_number": match_counter,
                    "stage": stage,
                    "group_name": group_name,
                    "round_number": 1,
                    "kickoff_at": kickoff_at.isoformat() if kickoff_at else None,
                    "stadium_name": stadium_name,
                    "home_team_en": home_en if home_en != "TBD" else None,
                    "away_team_en": away_en if away_en != "TBD" else None,
                    "home_team_placeholder": "" if home_en != "TBD" else home_en,
                    "away_team_placeholder": "" if away_en != "TBD" else away_en,
                    "home_score": home_score,
                    "away_score": away_score,
                    "status": status,
                    "time_elapsed": "",
                }
            )

        time.sleep(0.5)  # 礼貌爬取

    print(f"共解析 {len(matches)} 场比赛，{len(teams)} 支球队，{len(stadiums)} 座球场")
    return matches, list(teams.values()), list(stadiums.values())


def save_json(data, filename: str) -> None:
    """保存 JSON 文件."""
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存 {path}")


def main() -> None:
    """抓取入口."""
    matches, teams, stadiums = scrape_schedule()
    save_json(matches, "matches_raw.json")
    save_json(teams, "teams_raw.json")
    save_json(stadiums, "stadiums_raw.json")


if __name__ == "__main__":
    main()
