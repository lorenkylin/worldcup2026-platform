"""球场天气查询服务.

使用 Open-Meteo 免费 API（无需 key）查询比赛当日天气。
缓存策略：每个球场每日仅查一次，结果缓存到内存。
"""

import time
from typing import Optional

import httpx


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10.0
_cache: dict[tuple[float, float, str], tuple[float, dict]] = {}  # (lat, lng, date) -> (ts, data)
CACHE_TTL = 3600 * 6  # 6 小时


def _cache_key(lat: float, lng: float, date_str: str) -> tuple:
    return (round(lat, 4), round(lng, 4), date_str)


def get_weather_for_match(lat: float, lng: float, date_str: str) -> Optional[dict]:
    """查询比赛当日天气（hourly 步长）.

    返回字段：temperature_2m / precipitation / windspeed_10m / weathercode。
    """
    if lat is None or lng is None:
        return None
    key = _cache_key(lat, lng, date_str)
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    params = {
        "latitude": lat,
        "longitude": lng,
        "hourly": "temperature_2m,precipitation,windspeed_10m,weathercode",
        "start_date": date_str,
        "end_date": date_str,
        "timezone": "auto",
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(OPEN_METEO_URL, params=params)
        if resp.status_code != 200:
            return None
        data = resp.json()
        # 提取开球时刻附近的小时（默认 18:00，或可外部传入 hour）
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        idx = next((i for i, t in enumerate(times) if "T18:00" in t), 0)
        weather = {
            "temperature": hourly.get("temperature_2m", [None])[idx],
            "precipitation": hourly.get("precipitation", [0])[idx] or 0,
            "windspeed": hourly.get("windspeed_10m", [None])[idx],
            "weathercode": hourly.get("weathercode", [None])[idx],
            "updated_at": time.time(),
        }
        _cache[key] = (now, weather)
        return weather
    except Exception:  # noqa: BLE001
        return None


def weather_label(code: Optional[int]) -> str:
    """WMO weathercode -> 中文描述."""
    if code is None:
        return "未知"
    mapping = {
        0: "晴朗",
        1: "少云", 2: "多云", 3: "阴天",
        45: "雾", 48: "冰雾",
        51: "小毛雨", 53: "毛雨", 55: "大毛雨",
        61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪",
        80: "阵雨", 81: "强阵雨", 82: "暴阵雨",
        95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
    }
    return mapping.get(code, f"代码{code}")