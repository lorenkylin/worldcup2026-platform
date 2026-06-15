"""worldcup26.ir 解析单元测试."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.worldcup26_sync import _parse_scorers, _extract_minute


def test_parse_scorers_actual_format():
    """测试真实数据格式（花括号包引号、Unicode 引号）。"""
    # 真实数据：{“J. Quiñones 9'”,”R. Jiménez 67'”}
    raw = "{" + chr(0x201C) + "J. Quiñones 9'" + chr(0x201D) + "," + chr(0x201C) + "R. Jiménez 67'" + chr(0x201D) + "}"
    result = _parse_scorers(raw)
    assert len(result) == 2, f"应解析出 2 个，但拿到 {len(result)}: {result}"


def test_parse_scorers_null():
    assert _parse_scorers("null") == []
    assert _parse_scorers("") == []
    assert _parse_scorers("[]") == []


def test_parse_scorers_standard_json():
    result = _parse_scorers('["Player A 12\'", "Player B 45\'"]')
    assert len(result) == 2


def test_extract_minute():
    assert _extract_minute("J. Quiñones 9'") == 9
    assert _extract_minute("R. Jiménez 67'") == 67
    assert _extract_minute("Unknown Player") == 0
    assert _extract_minute("Player 90'") == 90


if __name__ == "__main__":
    test_parse_scorers_actual_format()
    test_parse_scorers_null()
    test_parse_scorers_standard_json()
    test_extract_minute()
    print("All passed")
