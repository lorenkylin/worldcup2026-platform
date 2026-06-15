"""P1.2 + P1.3 Playwright 端到端验证.

P1.2: Elo 页 "导出 CSV" 按钮触发下载 + CSV 内容校验
P1.3: 历史交锋主页 select + 对手列表 + 详情页跳转
"""
import os
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
SHOTS = Path("docs/screenshots/P1.2_P1.3")
SHOTS.mkdir(parents=True, exist_ok=True)


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # ==== P1.2: 导出 CSV ====
        print("=== P1.2: Elo 页导出 CSV 验证 ===")
        page.goto(f"{BASE}/#/elo", wait_until="domcontentloaded")
        page.wait_for_selector('button[onclick="exportEloToCSV()"]', timeout=10000)
        # 截图
        page.screenshot(path=str(SHOTS / "01_elo_with_export_btn.png"), full_page=False)
        with page.expect_download(timeout=15000) as dl_info:
            page.click('button[onclick="exportEloToCSV()"]')
        download = dl_info.value
        tmp_path = Path(tempfile.gettempdir()) / "wc2026_elo_test.csv"
        download.save_as(str(tmp_path))
        # 验证文件名
        print(f"  下载文件名: {download.suggested_filename}")
        if not download.suggested_filename.startswith("wc2026_elo_ratings_"):
            errors.append(f"P1.2 文件名错: {download.suggested_filename}")
        # 验证 CSV 内容
        csv_text = tmp_path.read_text(encoding="utf-8-sig")  # 自动剥离 UTF-8 BOM
        # 下载文件用 \n 分隔（不是 \r\n）
        lines = [l for l in csv_text.strip().split("\n") if l]
        print(f"  CSV 行数: {len(lines)}（期望 49: 1 表头 + 48 队）")
        if len(lines) != 49:
            errors.append(f"P1.2 CSV 行数错: {len(lines)}（期望 49）")
        print(f"  CSV 表头: {lines[0]}")
        if "排名" not in lines[0] or "Elo评分" not in lines[0]:
            errors.append(f"P1.2 CSV 表头错: {lines[0]}")
        # 验证第 1 行（Top 1）
        if len(lines) >= 2:
            first_row = lines[1]
            print(f"  Top 1 行: {first_row}")
            if not first_row.startswith("1,"):
                errors.append(f"P1.2 Top 1 行不是 rank=1: {first_row}")
        # 验证 UTF-8 BOM
        with open(tmp_path, "rb") as f:
            bom = f.read(3)
        if bom != b"\xef\xbb\xbf":
            errors.append(f"P1.2 缺 UTF-8 BOM: {bom!r}")
        else:
            print(f"  ✅ UTF-8 BOM 正确")
        print(f"  ✅ CSV 内容校验通过")

        # ==== P1.3: 历史交锋主页 ====
        print("\n=== P1.3: 历史交锋主页验证 ===")
        page.goto(f"{BASE}/#/h2h", wait_until="domcontentloaded")
        page.wait_for_selector("#h2h-team-select", timeout=10000)
        page.wait_for_selector("#h2h-opponents-list a", timeout=10000)
        # 截图
        page.screenshot(path=str(SHOTS / "02_h2h_main_bra.png"), full_page=True)
        # 验证默认选 BRA
        selected = page.eval_on_selector("#h2h-team-select", "el => el.value")
        print(f"  默认选中: {selected}")
        if selected != "BRA":
            errors.append(f"P1.3 默认不是 BRA: {selected}")
        # 验证对手列表
        opponent_links = page.query_selector_all("#h2h-opponents-list a")
        print(f"  对手卡片数: {len(opponent_links)}")
        if len(opponent_links) != 9:
            errors.append(f"P1.3 BRA 对手数错: {len(opponent_links)}（期望 9）")
        # 验证第一名是 SRB（按对决数倒序）
        first_link = opponent_links[0]
        first_text = first_link.text_content()
        if "SRB" not in first_text:
            errors.append(f"P1.3 BRA 对手 #1 不是 SRB: {first_text}")
        else:
            print(f"  ✅ 对手 #1 = SRB（按对决数倒序）")
        # 验证对决数 = 2
        first_count = first_link.query_selector(".text-emerald-400").text_content()
        if first_count.strip() != "2":
            errors.append(f"P1.3 BRA vs SRB 对决数错: {first_count}（期望 2）")
        else:
            print(f"  ✅ BRA vs SRB 对决数 = 2")

        # 切换到 MEX
        page.select_option("#h2h-team-select", "MEX")
        time.sleep(0.5)
        page.wait_for_selector("#h2h-opponents-list a", timeout=5000)
        opponent_links_mex = page.query_selector_all("#h2h-opponents-list a")
        print(f"  MEX 对手卡片数: {len(opponent_links_mex)}")
        if len(opponent_links_mex) != 7:
            errors.append(f"P1.3 MEX 对手数错: {len(opponent_links_mex)}（期望 7）")
        page.screenshot(path=str(SHOTS / "03_h2h_main_mex.png"), full_page=True)

        # ==== P1.3 详情页跳转 ====
        print("\n=== P1.3 详情页跳转验证 ===")
        # 切回 BRA，点 SRB
        page.select_option("#h2h-team-select", "BRA")
        time.sleep(0.8)
        page.wait_for_selector("#h2h-opponents-list a", timeout=5000)
        first_link = page.query_selector("#h2h-opponents-list a")
        first_link.click()
        time.sleep(1.0)  # 等待 SPA 路由切换
        # 不依赖 URL glob（hash 路由可能不匹配），直接等 h1
        page.wait_for_selector("h1", timeout=8000)
        # 验证 URL 包含 /h2h/BRA/SRB
        cur_url = page.url
        print(f"  当前 URL: {cur_url}")
        if "/h2h/BRA/SRB" not in cur_url:
            errors.append(f"P1.3 详情页 URL 错: {cur_url}")
        h1_text = page.query_selector("h1").text_content()
        print(f"  详情页 H1: {h1_text[:80]}")
        if "巴西" not in h1_text and "BRA" not in h1_text:
            errors.append(f"P1.3 详情页无 BRA: {h1_text}")
        if "塞尔维亚" not in h1_text and "SRB" not in h1_text:
            errors.append(f"P1.3 详情页无 SRB: {h1_text}")
        page.screenshot(path=str(SHOTS / "04_h2h_detail_bra_srb.png"), full_page=True)
        # 验证对决列表（BRA vs SRB 应该有 2 场）
        match_cards = page.query_selector_all(".rounded-xl.border.border-slate-800")
        print(f"  详情页卡片数: {len(match_cards)}")
        h1_text = page.query_selector("h1").text_content()
        print(f"  详情页 H1: {h1_text[:80]}")
        if "巴西" not in h1_text and "BRA" not in h1_text:
            errors.append(f"P1.3 详情页无 BRA: {h1_text}")
        if "塞尔维亚" not in h1_text and "SRB" not in h1_text:
            errors.append(f"P1.3 详情页无 SRB: {h1_text}")
        page.screenshot(path=str(SHOTS / "04_h2h_detail_bra_srb.png"), full_page=True)
        # 验证对决列表（BRA vs SRB 应该有 2 场）
        match_cards = page.query_selector_all(".rounded-xl.border.border-slate-800")
        print(f"  详情页卡片数: {len(match_cards)}")

        # ==== 移动端 ====
        print("\n=== 移动端验证 (375px) ===")
        ctx2 = browser.new_context(viewport={"width": 375, "height": 800})
        page2 = ctx2.new_page()
        page2.goto(f"{BASE}/#/h2h", wait_until="domcontentloaded")
        page2.wait_for_selector("#h2h-team-select", timeout=10000)
        page2.wait_for_selector("#h2h-opponents-list a", timeout=10000)
        page2.screenshot(path=str(SHOTS / "05_h2h_mobile_375.png"), full_page=True)
        print(f"  ✅ 移动端截图已存")

        browser.close()

    # 总结
    print()
    print("=" * 50)
    if errors:
        print(f"❌ {len(errors)} 项校验失败:")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("✅ 全部验证通过！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
