"""M1.5 前端 Elo 页面 Playwright 渲染测试 + 截图."""
from playwright.sync_api import sync_playwright
import time, sys, os

OUT = r"D:\WorkBuddy\2026FIFA\worldcup2026-platform\docs\screenshots\M1.5"
URL = "http://localhost:8000/#/elo"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # PC 1440
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console_msgs = []
        page_errors = []
        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(URL)
        time.sleep(3)  # wait for API calls

        # 检查关键元素
        checks = {
            "Header": "Elo 实力榜",
            "1v1 section": "1v1 实力对比",
            "48 队全榜": "48 队 Elo 全榜",
            "回测卡片": "4 年 walk-forward 回测指标",
            "KPI 准确率": "回测准确率",
        }

        body = page.content()
        print("=" * 60)
        print("[M1.5 Elo 页渲染检查]")
        print("=" * 60)
        all_ok = True
        for name, kw in checks.items():
            ok = kw in body
            mark = "[OK]" if ok else "[FAIL]"
            print(f"  {mark} {name}: '{kw}' {'found' if ok else 'NOT FOUND'}")
            if not ok:
                all_ok = False

        # 检查 select 选项数（应该有 48）
        opts = page.locator("#elo-home option").count()
        print(f"  [{'OK' if opts == 48 else 'FAIL'}] 主队 select 选项数: {opts} (期望 48)")

        # 截图 1：默认状态
        page.screenshot(path=os.path.join(OUT, "01_elo_default.png"), full_page=True)
        print(f"  [SAVED] 01_elo_default.png")

        # 交互测试 1：选 BRA vs ARG
        page.select_option("#elo-home", "BRA")
        page.select_option("#elo-away", "ARG")
        time.sleep(2)
        body_after = page.content()
        has_bra_arg = "客胜" in body_after and "主胜" in body_after
        print(f"  [{'OK' if has_bra_arg else 'FAIL'}] 1v1 交互后有概率结果: {has_bra_arg}")
        page.screenshot(path=os.path.join(OUT, "02_elo_predict_bra_arg.png"), full_page=True)
        print(f"  [SAVED] 02_elo_predict_bra_arg.png")

        # 交互测试 2：选 ESP vs GUA（强弱最悬殊）
        page.select_option("#elo-home", "ESP")
        page.select_option("#elo-away", "GUA")
        time.sleep(2)
        body2 = page.content()
        # 提取主胜概率
        if "主胜" in body2:
            import re
            m = re.search(r"主胜\s*<b[^>]*>([0-9.]+)%</b>", body2)
            if m:
                p = float(m.group(1))
                print(f"  [INFO] ESP vs GUA 主胜概率: {p}% (期望 > 80%)")
        page.screenshot(path=os.path.join(OUT, "03_elo_predict_esp_gua.png"), full_page=True)
        print(f"  [SAVED] 03_elo_predict_esp_gua.png")

        # 移动端 375 测试
        ctx2 = browser.new_context(viewport={"width": 375, "height": 667})
        page2 = ctx2.new_page()
        page2.goto(URL)
        time.sleep(3)
        page2.screenshot(path=os.path.join(OUT, "04_elo_mobile_375.png"), full_page=True)
        print(f"  [SAVED] 04_elo_mobile_375.png")

        # 控制台错误
        print("\n" + "=" * 60)
        print(f"[控制台消息] 共 {len(console_msgs)} 条")
        for m in console_msgs:
            if "error" in m.lower() or "warn" in m.lower():
                print(f"  {m}")
        print(f"\n[页面错误] 共 {len(page_errors)} 条")
        for e in page_errors:
            print(f"  {e}")

        browser.close()

        print("\n" + "=" * 60)
        if all_ok and not page_errors:
            print("[PASS] M1.5 Elo 页面渲染通过")
        else:
            print("[FAIL] 检查到问题")
            sys.exit(1)

if __name__ == "__main__":
    main()
