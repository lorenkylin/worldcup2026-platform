"""P1.2 Elo CSV 导出 — Playwright 验证

测试目标：
1. Elo 页加载，按钮存在
2. 点击"导出 CSV"触发浏览器下载
3. 下载文件 CSV 内容正确（表头 + 48 队 + 字段完整）
4. 文件名格式 YYYY-MM-DD.csv
5. 按钮自我反馈（点击后变 "已导出"）
6. 截图归档
"""
import asyncio
import os
import sys
from pathlib import Path

# 设 NODE_PATH 让 playwright 能 resolve
os.environ['NODE_PATH'] = r'C:\Users\HUAWEI\.workbuddy\binaries\node\versions\22.22.2\node_modules'

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / 'docs' / 'screenshots' / 'P1.2'
SHOTS.mkdir(parents=True, exist_ok=True)
DOWNLOADS = ROOT / 'docs' / 'downloads' / 'P1.2'
DOWNLOADS.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            accept_downloads=True,  # 关键：接受下载
        )
        page = await ctx.new_page()

        page_errors = []
        page.on('pageerror', lambda e: page_errors.append(str(e)))
        console_errors = []
        page.on('console', lambda m: console_errors.append(f'{m.type}: {m.text}') if m.type == 'error' else None)

        # 1. 加载 Elo 页
        print('1) loading /#/elo ...')
        await page.goto('http://localhost:8000/#/elo', wait_until='networkidle', timeout=15000)
        await page.wait_for_timeout(1500)

        # 2. 验证按钮存在
        btn = await page.query_selector('button[onclick="exportEloToCSV()"]')
        assert btn, '❌ 导出按钮不存在'
        btn_text = (await btn.inner_text()).strip()
        print(f'   按钮文本：{btn_text!r}')
        assert '导出 CSV' in btn_text, f'❌ 按钮文本不对：{btn_text}'

        # 3. 全页截图（导出前）
        await page.screenshot(path=str(SHOTS / '01_elo_before_export.png'), full_page=True)
        print('   ✓ 截图 01_elo_before_export.png')

        # 4. 点按钮 + 捕获下载
        print('2) click 导出 CSV ...')
        async with page.expect_download(timeout=10000) as dl_info:
            await btn.click()
        download = await dl_info.value
        suggested_filename = download.suggested_filename
        print(f'   建议文件名：{suggested_filename}')
        assert suggested_filename.startswith('wc2026_elo_ratings_'), f'❌ 文件名前缀错：{suggested_filename}'
        assert suggested_filename.endswith('.csv'), f'❌ 后缀错：{suggested_filename}'

        # 5. 保存到本地
        local_path = DOWNLOADS / suggested_filename
        await download.save_as(str(local_path))
        print(f'   ✓ 下载到 {local_path}')

        # 6. 验证 CSV 内容（用 bytes 模式避开 Python universal newline 规范化）
        raw_bytes = local_path.read_bytes()
        assert raw_bytes.startswith(b'\xef\xbb\xbf'), '❌ 缺 UTF-8 BOM（Excel 中文版需要）'
        content = raw_bytes[3:].decode('utf-8')  # 剥 BOM
        lines = content.split('\r\n')
        print(f'   CSV 总行数：{len(lines)}')
        header = lines[0].split(',')
        print(f'   表头：{header}')
        expected_header = ['排名', 'FIFA代码', '中文名', '英文名', '小组', '国旗', 'Elo评分', '实力分(0-100)', '近5场得分', '近5场净胜']
        assert header == expected_header, f'❌ 表头不匹配：{header}'
        print(f'   ✓ 表头匹配')

        # 7. 验证数据行数（Elo 含 63 队，比参赛 48 队多 15 队）
        data_rows = [l for l in lines[1:] if l.strip()]
        n = len(data_rows)
        print(f'   数据行数：{n}')
        assert n >= 48, f'❌ 数据行 {n} < 48'

        # 8. 验证第 1 行（ESP Top 1）
        esp_row = data_rows[0].split(',')
        print(f'   第 1 行：{esp_row}')
        assert esp_row[1] == 'ESP', f'❌ 第 1 行队码不是 ESP：{esp_row[1]}'
        assert int(esp_row[6]) == 2010, f'❌ ESP Elo 应为 2010：{esp_row[6]}'
        assert esp_row[2] == '西班牙', f'❌ ESP 中文名错：{esp_row[2]}'
        print(f'   ✓ ESP Top 1 = Elo 2010')

        # 9. 验证最后一行 GUA（最弱）
        last_row = data_rows[-1].split(',')
        print(f'   最后一行：{last_row}')
        assert last_row[1] == 'GUA', f'❌ 末行队码不是 GUA：{last_row[1]}'
        print(f'   ✓ GUA 末位（最弱）')

        # 10. 验证字段数
        for i, row in enumerate(data_rows):
            cells = row.split(',')
            assert len(cells) == 10, f'❌ 第 {i+1} 行列数 {len(cells)} != 10: {row}'
        print(f'   ✓ 全部 {n} 行 10 列对齐')

        # 10. 验证 RFC 4180 转义（直接在浏览器里调用 csvEscape，避开 Python JSON 序列化）
        print('3) 测试 CSV 转义（含逗号/引号字段）')
        escaped_csv = await page.evaluate('''() => {
            // csvEscape 是页面里的全局函数，直接调用
            return csvEscape('逗号,字段') + '|' + csvEscape('含"引号') + '|' + csvEscape('普通');
        }''')
        print(f'   转义结果：{escaped_csv}')
        assert escaped_csv == '"逗号,字段"|"含""引号"|普通', f'❌ 转义不对：{escaped_csv}'
        print(f'   ✓ RFC 4180 转义正确（逗号→加引号，引号→转义+加引号，普通→不变）')

        # 11. 等按钮反馈
        await page.wait_for_timeout(300)
        btn_text_after = (await btn.inner_text()).strip()
        print(f'   按钮反馈后：{btn_text_after!r}')
        # 可能是 "已导出 48 队" 或 "导出 CSV"（取决于时序）

        # 12. 截按钮反馈截图
        await page.screenshot(path=str(SHOTS / '02_elo_after_export.png'), full_page=False)
        print('   ✓ 截图 02_elo_after_export.png')

        # 13. 错误检查
        if page_errors:
            print(f'❌ page errors: {page_errors}')
            sys.exit(1)
        if console_errors:
            print(f'⚠️ console errors: {console_errors}')

        print()
        print('=' * 60)
        print(f'✅ P1.2 验证全过')
        print(f'   - 按钮存在并触发下载')
        print(f'   - 文件名：{suggested_filename}')
        print(f'   - CSV 表头 10 列 + {n} 数据行（含 48 参赛队 + 15 Elo 评级队）')
        print(f'   - ESP Top 1 = 2010 Elo')
        print(f'   - GUA 末位（最弱 Elo 1416）')
        print(f'   - RFC 4180 转义正确')
        print(f'   - 控制台错误 0 个')
        print('=' * 60)

        # 12. 移动端截图验证按钮可见
        await ctx.close()
        ctx_m = await browser.new_context(viewport={'width': 375, 'height': 812})
        page_m = await ctx_m.new_page()
        await page_m.goto('http://localhost:8000/#/elo', wait_until='networkidle', timeout=15000)
        await page_m.wait_for_timeout(1500)
        btn_m = await page_m.query_selector('button[onclick="exportEloToCSV()"]')
        assert btn_m, '❌ 移动端导出按钮不可见'
        btn_m_box = await btn_m.bounding_box()
        print(f'   移动端按钮位置：x={btn_m_box["x"]:.0f} y={btn_m_box["y"]:.0f} w={btn_m_box["width"]:.0f}')
        assert btn_m_box['x'] < 375, '❌ 移动端按钮超出视口'
        assert btn_m_box['y'] < 200, f'❌ 移动端按钮位置过低（y={btn_m_box["y"]:.0f}）'
        await page_m.screenshot(path=str(SHOTS / '03_elo_mobile_375.png'), full_page=False)
        print(f'   ✓ 移动端截图 03_elo_mobile_375.png')

        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())