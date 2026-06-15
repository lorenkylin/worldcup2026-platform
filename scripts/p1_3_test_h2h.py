"""P1.3: 历史交锋详情页 + match detail 链接 验证脚本.

测试覆盖:
  1. 路由可达: 浏览器跳转到 #/h2h/ARG/FRA → 渲染详情页
  2. 数据正确: 胜负条 + 2 场历史交锋
  3. 边界 case: #/h2h/BRA/ARG (无对决) → 显示空态
  4. 边界 case: #/h2h/MEX/RSA → 含 1 场 2026 完赛
  5. 入口可达: match detail 页 H2H 卡片有"📜 完整历史 →"链接
  6. 移动端 375px 布局不破

运行: 先确保 uvicorn 启动在 127.0.0.1:8000
"""
import asyncio
import sys
import json
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots" / "P1.3"
OUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("=" * 60)
    print("P1.3 历史交锋详情页验证")
    print("=" * 60)
    checks_passed = 0
    checks_total = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # ===== Test 1: 路由可达 + 数据正确（ARG vs FRA 2场）=====
        checks_total += 1
        print(f"\n[Test 1] #/h2h/ARG/FRA — 2022决赛 + 2018 16强")
        await page.goto(f"{BASE}/#/h2h/ARG/FRA", wait_until="networkidle")
        await page.wait_for_timeout(500)
        # 检查标题
        h1_text = await page.locator("h1").first.text_content()
        assert "阿根廷" in h1_text and "法国" in h1_text, f"❌ 标题错误: {h1_text}"
        print(f"  标题: {h1_text.strip()[:50]}")
        # 检查胜负条
        summary_text = await page.locator("text=共 2 场").first.text_content()
        assert "2 场" in summary_text, f"❌ 胜负条 summary 错误"
        print(f"  胜负条: {summary_text.strip()}")
        # 检查场次列表
        match_cards = await page.locator("text=2022-12-18").count()
        assert match_cards > 0, "❌ 未找到 2022-12-18 决赛"
        match_cards2 = await page.locator("text=2018-07-03").count()
        assert match_cards2 > 0, "❌ 未找到 2018-07-03 16强"
        print(f"  场次列表: 2 场历史交锋齐全 ✓")
        # 截图
        await page.screenshot(path=str(OUT_DIR / "01_h2h_arg_fra_1440.png"), full_page=True)
        print(f"  📸 截图: 01_h2h_arg_fra_1440.png")
        print(f"  ✅ Test 1 PASSED")
        checks_passed += 1

        # ===== Test 2: 边界 - 无对决 (BRA vs ARG) =====
        checks_total += 1
        print(f"\n[Test 2] #/h2h/BRA/ARG — 无对决 → 空态")
        await page.goto(f"{BASE}/#/h2h/BRA/ARG", wait_until="networkidle")
        await page.wait_for_timeout(500)
        empty_text = await page.locator("text=两队暂无历史交锋数据").count()
        assert empty_text > 0, "❌ 空态文案缺失"
        print(f"  空态显示 ✓")
        await page.screenshot(path=str(OUT_DIR / "02_h2h_empty_bra_arg.png"), full_page=True)
        print(f"  📸 截图: 02_h2h_empty_bra_arg.png")
        print(f"  ✅ Test 2 PASSED")
        checks_passed += 1

        # ===== Test 3: 2026 已完赛 (MEX vs RSA) =====
        checks_total += 1
        print(f"\n[Test 3] #/h2h/MEX/RSA — 2026 完赛 1 场")
        await page.goto(f"{BASE}/#/h2h/MEX/RSA", wait_until="networkidle")
        await page.wait_for_timeout(500)
        # 胜负条 summary 应包含 "本届 1 场"
        total_text = await page.locator("text=共 1 场").first.text_content()
        assert "1 场" in total_text, f"❌ 1 场 summary 错误: {total_text}"
        # 应有"本届"标签
        ben_biao_qian = await page.locator("text=本届").count()
        assert ben_biao_qian > 0, "❌ 未找到 '本届' 标签"
        print(f"  summary: {total_text.strip()}")
        print(f"  本届标签: ✓")
        await page.screenshot(path=str(OUT_DIR / "03_h2h_2026_mex_rsa.png"), full_page=True)
        print(f"  📸 截图: 03_h2h_2026_mex_rsa.png")
        print(f"  ✅ Test 3 PASSED")
        checks_passed += 1

        # ===== Test 4: 入口可达 - match detail H2H 卡片链接 =====
        checks_total += 1
        print(f"\n[Test 4] match detail H2H 卡片入口链接")
        # 找一场已完赛 + 有预测的比赛 — MEX vs RSA (id=1)
        await page.goto(f"{BASE}/#/match/1", wait_until="networkidle")
        await page.wait_for_timeout(500)
        # 等"⚔️ 历史交锋"卡片
        link = page.locator("a[href*='h2h/MEX']")
        link_count = await link.count()
        assert link_count > 0, "❌ match detail H2H 卡片未找到完整历史链接"
        link_text = await link.first.text_content()
        link_href = await link.first.get_attribute("href")
        print(f"  链接文案: {link_text.strip()}")
        print(f"  链接 href: {link_href}")
        # 点击进入
        await link.first.click()
        await page.wait_for_timeout(800)
        # 验证跳转
        h1_text2 = await page.locator("h1").first.text_content()
        assert "墨西哥" in h1_text2 or "RSA" in h1_text2 or "南非" in h1_text2, f"❌ 跳转后标题错误: {h1_text2}"
        print(f"  点击后跳转 ✓ 标题: {h1_text2.strip()[:50]}")
        await page.screenshot(path=str(OUT_DIR / "04_entry_from_match_detail.png"), full_page=True)
        print(f"  📸 截图: 04_entry_from_match_detail.png")
        print(f"  ✅ Test 4 PASSED")
        checks_passed += 1

        # ===== Test 5: 移动端 375px =====
        checks_total += 1
        print(f"\n[Test 5] 移动端 375px 布局")
        mobile_context = await browser.new_context(viewport={"width": 375, "height": 812})
        mobile_page = await mobile_context.new_page()
        await mobile_page.goto(f"{BASE}/#/h2h/ARG/FRA", wait_until="networkidle")
        await mobile_page.wait_for_timeout(500)
        # 检查 h1 不溢出
        h1 = mobile_page.locator("h1").first
        h1_box = await h1.bounding_box()
        assert h1_box and h1_box["width"] < 360, f"❌ 移动端 h1 宽度溢出: {h1_box}"
        print(f"  h1 宽度: {h1_box['width']:.0f}px < 360px ✓")
        await mobile_page.screenshot(path=str(OUT_DIR / "05_h2h_mobile_375.png"), full_page=True)
        print(f"  📸 截图: 05_h2h_mobile_375.png")
        await mobile_context.close()
        print(f"  ✅ Test 5 PASSED")
        checks_passed += 1

        # ===== Test 6: API 直接验证边界 (404 + 400) =====
        checks_total += 1
        print(f"\n[Test 6] API 边界 case (server-side)")
        # 200: ARG vs FRA
        r = await page.evaluate("""async () => {
          const r1 = await fetch('/api/h2h/ARG/FRA');
          const r2 = await fetch('/api/h2h/ARG/ARG');
          const r3 = await fetch('/api/h2h/ZZZ/ARG');
          return {ok1: r1.status, err1: r2.status, err2: r3.status};
        }""")
        print(f"  ARG/FRA: {r['ok1']} (期望 200), ARG/ARG: {r['err1']} (期望 400), ZZZ/ARG: {r['err2']} (期望 404)")
        assert r["ok1"] == 200, f"❌ 期望 200, 实际 {r['ok1']}"
        assert r["err1"] == 400, f"❌ 期望 400, 实际 {r['err1']}"
        assert r["err2"] == 404, f"❌ 期望 404, 实际 {r['err2']}"
        print(f"  ✅ Test 6 PASSED")
        checks_passed += 1

        await browser.close()

    print("\n" + "=" * 60)
    print(f"P1.3 验证: {checks_passed}/{checks_total} 通过")
    print("=" * 60)
    if checks_passed == checks_total:
        print("✅ 全部测试通过")
        return 0
    else:
        print(f"❌ {checks_total - checks_passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
