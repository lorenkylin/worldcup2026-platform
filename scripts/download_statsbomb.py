"""下载 StatsBomb Open Data 国际赛并训练 Elo 评分.

用法:
    python scripts/download_statsbomb.py
    python scripts/download_statsbomb.py --force-download
"""
import argparse

from app.services.statsbomb_elo import build_statsbomb_elo_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Download StatsBomb data and build Elo ratings")
    parser.add_argument("--force-download", action="store_true", help="强制重新下载 raw 文件")
    args = parser.parse_args()

    path = build_statsbomb_elo_json(force_download=args.force_download)
    print(f"[done] StatsBomb Elo ratings written to {path}")


if __name__ == "__main__":
    main()
