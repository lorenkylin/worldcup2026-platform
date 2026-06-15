# P0 第四批交付报告：A11 移动端导航抽屉

## 完成项

### A11 移动端导航抽屉

- **HTML 结构**（`index.html` +31 行）
  - header 左侧 hamburger 按钮：`lg:hidden` 隐藏 PC 显示
  - `<aside id="drawer">` 侧滑抽屉（280px / max-width: 80vw）
  - `<div id="drawer-overlay">` 半透明遮罩
  - 抽屉内含 9 项：6 个主页面导航 + 关于本站 + 数据来源 + 底部"数据更新于"时间

- **CSS 动画**（`styles.css` +26 行）
  - `.drawer`：fixed left-0 width 280px，z-index 60
  - 滑入动画：`transform: translateX(-100%)` → `translateX(0)`，0.25s ease-out
  - 遮罩：`.drawer-overlay` 0.25s opacity 过渡，z-index 55（低于抽屉、高于内容）
  - 弹窗：`.modal-backdrop` z-index 70（最高层），关于本站 / 数据来源模态
  - 抽屉项 hover：背景 slate-800 + 文字 emerald-400

- **JS 逻辑**（`app.js` +57 行）
  - `toggleDrawer()`：开/关抽屉，同步遮罩 + body 锁定滚动
  - `showAbout()`：动态创建关于本站模态（含项目背景、数据驱动、免责说明）
  - `showDataSource()`：动态创建数据来源模态（含 6 个数据源链接）
  - 全局 `keydown` 监听 ESC 关闭抽屉

- **响应式策略**
  - 移动端（< lg / < 1024px）：显示 hamburger 按钮，点击抽屉
  - PC（≥ lg / ≥ 1024px）：hamburger 隐藏，仍走底部 5 tab 导航

- **z-index 分层**
  - 内容 z-50 以下 / 抽屉 60 / 遮罩 55 / 模态 70
  - 模态可覆盖在抽屉之上，互不冲突

## 验证截图（6张）

| 截图 | 验证项 | 视口 | 状态 |
|---|---|---|---|
| `p0-A11-closed-mobile.png` | 414 移动端首页，header 含 hamburger | 414×896 | ✅ |
| `p0-A11-open-mobile.png` | 抽屉滑入显示 9 项导航 + 数据更新于 | 414×896 | ✅ |
| `p0-A11-about-modal.png` | 点击"关于本站"弹出模态 | 414×896 | ✅ |
| `p0-A11-closed-tablet.png` | 768 平板首页，hamburger 显示 | 768×1024 | ✅ |
| `p0-A11-open-tablet.png` | 平板抽屉滑入 | 768×1024 | ✅ |
| `p0-A11-pc-no-drawer.png` | 1440 PC 首页无 hamburger 按钮 | 1440×900 | ✅ |

## 复盘审查

| 检查项 | 结果 |
|---|---|
| `lg:hidden` 类生效（PC 不显示 hamburger） | ✅ PC 截图 header 仅显示 "⚽2026 WC 分析" + 数据状态 |
| 抽屉滑入滑出动画流畅 | ✅ transform transition 0.25s ease-out |
| 遮罩点击关闭 | ✅ `onclick="toggleDrawer()"` 绑定 overlay |
| ESC 键关闭 | ✅ 全局 keydown 监听，drawer open 时按 ESC 触发 toggle |
| 抽屉内导航切换会自动关闭抽屉 | ✅ 每项 `onclick="toggleDrawer()"` |
| 模态浮于抽屉之上 | ✅ z-index 70 > 抽屉 60 |
| 抽离开后无副作用（body overflow 还原） | ✅ 开关时同步 `body.style.overflow` |
| 数据更新于时间显示北京时间 | ✅ 用 `beijingNowString()` 与 cockpit 一致 |

## 文件改动

- `app/static/index.html`: 105 行（+31：drawer + overlay + hamburger）
- `app/static/css/styles.css`: 360 行（+26：drawer/overlay/modal 样式）
- `app/static/js/app.js`: 1631 行（+57：toggleDrawer/showAbout/showDataSource + ESC handler）

## P0 全四批总览

| 批次 | 项 | 时间 | 截图 | 状态 |
|---|---|---|---|---|
| 1 | A8/A9/A10 | ~90min | 7 张 | ✅ |
| 2 | A1/A3/A7 | ~75min | 7 张 | ✅ |
| 3 | A2/A4/A5/A6 | ~145min | 10 张 | ✅ |
| 4 | A11 | ~40min | 6 张 | ✅ |
| **合计** | **11 项** | **~6h** | **30 张** | ✅ |

### 总代码增量

- `app/static/js/app.js`：1105 → **1631 行**（+526 行，+47.6%）
- `app/static/css/styles.css`：166 → **360 行**（+194 行，+116.9%）
- `app/static/index.html`：74 → **105 行**（+31 行，+41.9%）

### 总体验证

- ✅ 5 个视口（414 移动 / 768 平板 / 1024 iPad / 1440 PC / 1920 宽屏）全部覆盖
- ✅ 5 个页面（Home / Schedule / Groups / Teams / MatchDetail / TeamDetail / Cockpit）零回归
- ✅ 11 项 P0 功能全部通过 Playwright 自动化截图验证

### 试用 URL

- 本机：http://localhost:8000/
- 移动（用手机扫）：http://192.168.1.169:8000/

## 下一步

P0 全部完成。下一步可考虑：

- **P1 阶段**（已规划待定）
- **路径A M1**：worldcup26.ir 4 年 FIFA 历史排名爬虫（提升 Elo 基线）
- **路径C T1**：3 个手写 ALTER TABLE 转 Alembic 迁移
