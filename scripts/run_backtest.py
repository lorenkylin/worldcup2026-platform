"""B6 命令行回测脚本.

用法：
    python scripts/run_backtest.py

输出：
    - 控制台打印 Markdown 报告
    - 同时写入 deliverables/backtest_report.md
"""

import os
import sys
from pathlib import Path

# 项目根路径加入 sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import SessionLocal
from app.services.backtest import run_backtest, render_markdown_report


def main() -> int:
    """执行回测并输出报告."""
    db = SessionLocal()
    try:
        print("🚀 B6 启动回测...")
        print("   数据源: H2HHistoricalMatch（2018+2022 世界杯种子）")
        print("   方法: Elo-Poisson v1（用当前 FIFA 排名作为实力代理）\n")

        report = run_backtest(db, lookback=999)
        md = render_markdown_report(report)

        # 打印到控制台
        print(md)

        # 写入 deliverables
        out_path = ROOT / "deliverables" / "backtest_report.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"\n✅ 报告已保存到: {out_path}")

        # 退出码
        if report.brier_score < 0.6:
            print(f"✅ Brier Score = {report.brier_score:.3f} < 0.6，模型校准优秀")
            return 0
        elif report.brier_score < 0.667:
            print(f"⚠️ Brier Score = {report.brier_score:.3f}，优于随机但仍可改进")
            return 0
        else:
            print(f"❌ Brier Score = {report.brier_score:.3f} ≥ 0.667，需要调优")
            return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
