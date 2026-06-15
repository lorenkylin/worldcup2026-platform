# P0 第三批交付报告：A2/A4/A5/A6 数据浏览增强

## 完成项

### A2 焦点战"换一换"
- 模块级状态 `_homeFocusIdx` 跟踪当前焦点战索引
- 标题栏右侧加 `🎲 换一换` 按钮，点击 `nextFocusMatch()` 切换
- 显示 `(1/3)` 当前位置标签
- 首页截图验证：从 QA vs CH (34.2%) 切换到 BR vs MA (58.8%)

### A4 粒度筛选芯片
- 4 个 chip：今日 / 明日 / 本周 / 全部，每个带数量徽章
- 选中态：绿色背景 + 黑字
- 模块级状态 `_scheduleFilter`：`today`/`tomorrow`/`week`/`all`/`date`
- 全局函数 `setScheduleFilter(f)` 切换后自动重新渲染

### A5 日期 chip 横滚条
- 从全部 matches 提取唯一日期（YYYY-MM-DD），按字典序排序
- 横向滚动，前 30 天
- 选中态：橙色背景 + 黑字
- "今天"特殊高亮：绿色文字 + 边框
- 显示格式：`MM/DD 周X`，如 `06/13 周六 ·今天`
- 全局函数 `setScheduleDate(d)`，再点同一天取消选择

### A6 球队搜索 + 排序
- 模块级 `_teamsKeyword` + `_teamsSort` 状态
- 搜索：input 实时过滤，匹配 name_zh / name_en / fifa_code / group_name
- 排序：4 个选项 - Elo 降序 / FIFA 升序 / 名称 A-Z / 按组
- 验证：搜"巴"→ 3 队（巴西/巴拿马/巴拉圭）；A-Z 排序按拼音

## 验证截图（10张）

| 截图 | 验证项 | 状态 |
|---|---|---|
| `p0-A2-focus-1.png` | 焦点战 (1/3) QA vs CH | ✅ |
| `p0-A2-focus-2.png` | 换一换后 (2/3) BR vs MA | ✅ |
| `p0-A4-schedule-all.png` | 全部 104 场 + 4 chip + 日期条 | ✅ |
| `p0-A4-schedule-today.png` | 今日 chip 高亮 + 仅 3 场 | ✅ |
| `p0-A4-schedule-tomorrow.png` | 明日 chip + 仅明日比赛 | ✅ |
| `p0-A5-schedule-by-date.png` | 06/11 周四 chip 橙色高亮 + 2 场 | ✅ |
| `p0-A6-teams-default.png` | 48 队 + 搜索框 + 排序 | ✅ |
| `p0-A6-teams-search-ba.png` | 搜"巴"剩 3 队 | ✅ |
| `p0-A6-teams-sort-az.png` | A-Z 排序，48 队完整 | ✅ |
| `p0-A6-teams-pc.png` | PC 视口 1440 排版 | ✅ |

## 复盘审查

| 检查项 | 结果 |
|---|---|
| 语法检查 | ✅ SYNTAX OK |
| app.js 行数 | 1534 行 (+171) |
| 切换焦点战 | ✅ 1/3 → 2/3，预测从 34.2%/25.8%/40% → 58.8%/22.8%/18.3% |
| 筛选 + 日期联动 | ✅ 切粒度清日期，选日期自动切到"按日期"模式 |
| 搜索过滤 | ✅ 中文/拼音/英文/fifa code 全部命中 |
| A-Z 中文排序 | ✅ 阿尔及利亚/阿根廷/埃及/奥地利...正确 |

## 下一步

进入第四批（最后一批）：A11 移动端导航抽屉