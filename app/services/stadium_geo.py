"""球场地理信息管理服务.

将 STADIUM_COORDS 写入 DB，供天气查询、地图、用户参考。
"""

from app.db import SessionLocal
from data.seed.stadium_coordinates import STADIUM_COORDS
from app.models import Stadium


def fill_stadium_coordinates() -> dict:
    """将所有球场经纬度补全. 已存在的不会被覆盖."""
    db = SessionLocal()
    try:
        updated = 0
        skipped = 0
        for name_en, (lat, lng, tz) in STADIUM_COORDS.items():
            stadium = db.query(Stadium).filter(Stadium.name_en == name_en).first()
            if not stadium:
                skipped += 1
                continue
            if stadium.latitude is None or stadium.longitude is None:
                stadium.latitude = lat
                stadium.longitude = lng
                stadium.timezone = tz
                updated += 1
            else:
                skipped += 1
        db.commit()
        return {
            "updated": updated,
            "skipped": skipped,
            "total_coords": len(STADIUM_COORDS),
        }
    finally:
        db.close()