// M3 赔率模块截图: #/odds + #/match/1 + 抽屉
const { chromium } = require('playwright');
const path = require('path');

const OUT_DIR = 'D:/WorkBuddy/2026FIFA/.workbuddy/screenshots/M3';

(async () => {
  const fs = require('fs');
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 414, height: 896 },  // 移动端尺寸
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();

  const PAGES = [
    { name: '01-odds-page', hash: '#/odds', desc: '赔率分析页 (含价值投注)' },
    { name: '02-match-detail-with-odds', hash: '#/match/1', desc: 'MEX vs RSA 比赛详情(含赔率卡)' },
    { name: '03-drawer-odds-link', hash: '#/', desc: '首页(抽屉含赔率入口)', action: 'open-drawer' },
  ];

  for (const p of PAGES) {
    const url = `http://localhost:8000/${p.hash}`;
    console.log(`>>> ${p.name}: ${p.desc}`);
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(1500);

      if (p.action === 'open-drawer') {
        // 打开抽屉
        await page.locator('button[aria-label="菜单"]').click();
        await page.waitForTimeout(500);
      }

      const file = path.join(OUT_DIR, `${p.name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`    saved: ${file}`);
    } catch (e) {
      console.error(`    FAILED: ${e.message}`);
    }
  }
  await browser.close();
  console.log('done');
})();
