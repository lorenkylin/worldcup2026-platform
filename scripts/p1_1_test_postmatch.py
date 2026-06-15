"""P1.1 验证赛后复盘卡片 + 截图."""
from playwright.sync_api import sync_playwright
import os, time

OUT = r"D:\WorkBuddy\2026FIFA\worldcup2026-platform\docs\screenshots\P1.1"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 测试完赛比赛详情：MEX vs RSA (2-0)
    page.goto("http://localhost:8000/#/match/1")
    time.sleep(3)

    body = page.content()
    print("[MEX vs RSA 完赛详情]")
    checks = {
        "赛后复盘 section": "赛后复盘" in body,
        "预测比分": "1:0" in body or "2:0" in body,
        "实际比分 2:0": "2:0" in body,
        "命中/偏离 verdict": "比分命中" in body or "方向命中" in body or "偏离" in body,
        "进球差": "进球差" in body,
        "模型注解": "Elo" in body or "模型" in body,
    }
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")

    page.screenshot(path=os.path.join(OUT, "01_postmatch_mex_rsa.png"), full_page=True)
    print(f"  [SAVED] 01_postmatch_mex_rsa.png")

    # 测试 KOR vs CZE (2-1)
    page.goto("http://localhost:8000/#/match/2")
    time.sleep(3)
    body2 = page.content()
    print("\n[KOR vs CZE 完赛详情]")
    print(f"  [{'OK' if '2:1' in body2 else 'FAIL'}] 实际比分 2:1")
    print(f"  [{'OK' if '赛后复盘' in body2 else 'FAIL'}] 赛后复盘 section")
    page.screenshot(path=os.path.join(OUT, "02_postmatch_kor_cze.png"), full_page=True)
    print(f"  [SAVED] 02_postmatch_kor_cze.png")

    # 测试未完赛（应该不显示复盘卡片）
    page.goto("http://localhost:8000/#/match/3")
    time.sleep(2)
    body3 = page.content()
    print("\n[未完赛比赛 #3]")
    print(f"  [{'OK' if '赛后复盘' not in body3 else 'FAIL'}] 不显示复盘卡片")

    print(f"\n[页面错误] {len(errors)} 条")
    for e in errors: print(f"  {e}")

    browser.close()
