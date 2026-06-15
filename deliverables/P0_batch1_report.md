# P0 第一批交付报告：A8/A9/A10 基础设施

## 完成项

### A8 404 / 空状态
- 新增 `renderNotFound()` 函数：🧭 emoji + 标题 + 6 个推荐导航格子（首页/总览/赛程/积分/出线/48队）
- 新增 `renderEmpty(emoji, title, hint, ctaHash, ctaLabel)` 通用组件
- 应用到 7 处：Home（今日无比赛）、Schedule、Groups、Teams、TeamDetail（无赛程）、Simulator、Cockpit

### A9 加载骨架屏
- 新增 `showSkeleton(type)` 函数，9 种骨架类型（home/schedule/teams/match-detail/team-detail/groups/simulator/cockpit/generic）
- 在 router 入口根据 hash 自动切换对应骨架
- CSS 动画：1.4s 渐变 shimmer 效果，颜色 slate-800 → slate-700 → slate-800

### A10 错误重试
- 新增 `apiWithRetry(path, options)` 封装：默认 1 次重试 + 600ms 延迟
- 新增 `renderError(err, retryFn)` 通用错误页：😵 + 错误信息 + [重试] + [返回首页]
- 替换 7 处 `api()` 为 `apiWithRetry()`：Home/Schedule/Groups/Teams/TeamDetail/MatchDetail/Simulator/Cockpit/PredictionMini

## 验证截图（7张）

| 截图 | 验证项 | 视口 | 状态 |
|---|---|---|---|
| `p0-A9-skeleton-mobile.png` | 5 条骨架矩形 + shimmer 动画 | 414×896 | ✅ |
| `p0-A9-skeleton-pc.png` | 宽屏骨架（cockpit 类型） | 1920×1080 | ✅ |
| `p0-A8-notfound-mobile.png` | 🧭 + 6 导航格子 | 414×896 | ✅ |
| `p0-A8-notfound-pc.png` | 同上 PC 版 | 1440×900 | ✅ |
| `p0-A10-error-mobile.png` | 😵 + [重试][返回首页] | 414×896 | ✅ |
| `p0-A10-error-pc.png` | 同上 PC 版 | 1440×900 | ✅ |
| `p0-regression-home-mobile.png` | 正常首页未破坏 | 414×2663 fullPage | ✅ |

## 复盘审查

| 检查项 | 结果 |
|---|---|
| 语法检查 (`new Function(code)`) | ✅ SYNTAX OK |
| 服务端 app.js 加载 | ✅ HTTP 200, 58663 bytes, 1288 行 |
| 5 个新函数全部存在 | ✅ showSkeleton/renderError/renderNotFound/renderEmpty/apiWithRetry |
| 回归首页正常 | ✅ 今日3场 + 焦点战预测 + 出线 + 12组积分完整渲染 |
| 移动端 + PC 视口均工作 | ✅ |

## 文件改动

- `app/static/css/styles.css`: 282 行（+116：骨架屏 + 按钮 + 404 样式）
- `app/static/js/app.js`: 1288 行（+183：5 个新函数 + router 改写 + 7 处空状态保护 + 7 处 apiWithRetry）

## 下一步

进入第二批：A1 列表刷新 + A3 详情返回 + A7 上一场/下一场