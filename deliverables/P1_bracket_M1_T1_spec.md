# P1 阶段方案：晋级路线图 + M1 + T1

> **版本**：v1.0  | **日期**：2026-06-13
> **执行模式**：串行（先 Bracket，再 M1，最后 T1）
> **关联**：[P0 完成报告](./P0_batch1_report.md) | [Cockpit 交付](../deliverables/cockpit-*.png)

---

## 一、任务边界

| 任务 | 路径 | 来源 | 工时估算 | 依赖 |
|---|---|---|---|---|
| **B1 晋级路线图** | Path B（数据展示） | 本次新增 | 6-8h | 无 |
| **M1 4年FIFA排名历史** | Path A（数据） | 上次延期 | 4-5h | 数据源决策 |
| **T1 Alembic 迁移** | Path C（工程） | 上次延期 | 2-3h | 无 |

---

## 二、B1 晋级路线图 — 完整规格

### 2.1 数据真相

```
当前 DB 状态：
  ✓ 小组赛 72 场（已确定主客队）→ 可展示
  ✓ 小组赛 32 场（占位符 match 73-104）→ 其实是 R32 占位
  ✗ 淘汰赛 R16/QF/SF/F/3rd 共 49 场 → DB 里完全没有
  ✗ 32 强球队 → 小组赛出结果前无法确定
```

**结论**：现在能展示"完整路线图"但 R32+ 都是空节点。这不是 bug 而是**现实**——世界杯 6/11 开幕，6/26 才出 32 强。所以路线图本身是"框架就绪 + 数据滚动更新"。

### 2.2 页面结构（单页 P0-P1 混合复杂度）

```
┌─────────────────────────────────────────────────┐
│  Header: 🏆 2026 世界杯晋级路线图                │
│  [刷新] [展开小组赛] [折叠小组赛]  最后更新: ... │
├─────────────────────────────────────────────────┤
│  阶段一：12 小组赛 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│  ┌──A──┐ ┌──B──┐ ┌──C──┐ ... ┌──L──┐           │
│  │ 4队  │ │ 4队  │ │ 4队  │     │ 4队  │           │
│  │ 已晋级  │ │ 晋级中│ │  │ │ │  │           │
│  └──┬───┘ └──┬───┘ └──┬───┘     └──┬───┘           │
│     │        │        │            │               │
│  [小组第3择优 8 队]                                  │
├─────────────────────────────────────────────────┤
│  阶段二：32 强 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│  (1) (2) (3) (4) (5) (6) (7) (8)              │
│  (9) (10) (11) (12) (13) (14) (15) (16)      │
│  [每个节点=2队+比分(若有)+下一场箭头]              │
├─────────────────────────────────────────────────┤
│  阶段三：16 强 → 8强 → 4强 → 决赛 → 冠军 ━━━━━━━│
│  (中心放射式布局)                                    │
│  16 ──→ 8 ──→ 4 ──→ 2 ──→ 🏆                  │
├─────────────────────────────────────────────────┤
│  Bottom Nav: 6 个大按钮（重新设计）                │
└─────────────────────────────────────────────────┘
```

### 2.3 视觉设计

**配色方案**（暗色主题，统一 Cockpit 风格）：
- 背景：`#020617` (slate-950)
- 卡片：`#0f172a` (slate-900) + `border: 1px solid #1e293b` (slate-800)
- 已晋级：`#10b981` (emerald-500) 描边 + 轻微绿底
- 已淘汰：`#475569` (slate-600) 描边 + 透明度 0.5
- 进行中：`#ef4444` (red-500) 脉冲描边
- 冠军：`#fbbf24` (amber-400) 金色 + 闪光动画
- 比分：大字号 28px + 粗体
- 国旗 emoji：固定 24px

**节点卡片规格**（基础尺寸 200×80px）：
```
┌──────────────────────────┐
│ 🇦🇷  阿根廷    06/26 21:00│  ← 上方队
│ ────────────────────      │
│ 🇫🇷  法国      [vs]      │  ← 下方队
│ 状态: 已完赛 2-1 (90')  │  ← 状态条
└──────────────────────────┘
```

**已完成场次**特殊处理：
- 胜方：加粗 + 国旗放大 + 背景微亮
- 负方：opacity 0.5
- 平局需点球：标 `(点球 4-3)` 角标
- 比分：单字段 `2`（左）vs `1`（右），居中

**PC / 移动双布局**：
- **PC ≥ 1024px**：水平完整版（小组赛顶部 + 6 段向右的连线 + 居中决赛 + 冠军）
- **移动 < 1024px**：垂直分段版（按阶段折叠，每个阶段内水平排布，横向滚动）

### 2.4 底部导航重新设计

**当前**（5 个 36px 小 tab）：
```
🏠首页 | 🎛总览 | 📅赛程 | 📊积分 | ⚽球队
```

**新设计**（6 个 64px 大圆角按钮 + 渐变）：
```
┌─────────────────────────────────────────────────┐
│  [🏠首页] [🎛总览] [🏆路线图] [📅赛程] [📊积分] [⚽球队]  │
│  ↑ 当前激活态：渐变背景 + 阴影 + 缩放1.05       │
└─────────────────────────────────────────────────┘
```

样式规格：
- 高度：64px
- 圆角：16px
- 默认：`bg-slate-900 / border-slate-800 / text-slate-400`
- 激活：`bg-gradient-to-br from-emerald-500 to-cyan-500 / text-slate-950 / shadow-lg / scale-105`
- 顶部新增 🏆路线图（bracket 图标）作为本任务入口
- 移动端：横向滑动，固定高度 64px

### 2.5 API 端点需求

**现有足够**（无需新增后端）：
- `GET /api/matches?limit=200` — 拿全部 169 场（前端按 stage 过滤）
- `GET /api/teams` — 拿全部 48 队（前端按 fifa_code 匹配）

**前端自计算**：
- 32 强对阵推导：根据 group_name 排序 + match_number（数据已有规则）
- 晋级链路：通过 match_number 链式 lookup（#73-88 是 R32，#89-96 是 R16，#97-100 是 QF，#101-102 是 SF，#103 是 3rd，#104 是 Final）

> 但实际看 DB，match 73-104 是 32 个 TBD，没有分组。所以现在**只有 R32 占位，没有 R16+**。这意味着路线图的右侧（16 强以后）暂时是空白框架，需要等数据补齐。我会**预留框架 + 明确空态提示**。

### 2.6 交互细节

1. **点击节点** → 跳转 `#/match/{id}` 详情页（保留现有逻辑）
2. **悬停节点** → 阴影提升 + 边框变色
3. **点击小组** → 跳转 `#/groups?focus=A` 积分页（带高亮）
4. **状态过滤芯片**：全部 / 进行中 / 已完赛 / 未开始（影响哪些节点高亮）
5. **"展开/折叠" 小组赛** → 节省纵向空间
6. **底部新增 [🎲模拟晋级]** → 调用现有 `/api/simulator` 用模拟结果填空

### 2.7 文件影响

| 文件 | 增量 | 内容 |
|---|---|---|
| `app/static/js/app.js` | +500~600 行 | `renderBracket()` + 6 个 helper |
| `app/static/css/styles.css` | +100~150 行 | 路线图连接线、节点卡片、底部 nav 新样式 |
| `app/static/index.html` | +20 行 | 底部 nav 加 🏆路线图 tab |

### 2.8 验收标准

- [ ] 桌面 1440×900 截图：完整 6 段（小组赛 + R32 + R16 + QF + SF + F）可一屏看
- [ ] 移动 375×812 截图：分段折叠版可操作
- [ ] 已完赛场次：胜方高亮 + 比分大字号
- [ ] 进行中：脉冲红边 + 实时分钟
- [ ] 未开始：北京时间 + 倒计时（参考 Cockpit 的 `countdownText`）
- [ ] 点击节点 → 跳详情页
- [ ] 底部新 nav：6 按钮 64px 高，激活态渐变 + 缩放
- [ ] 路线图 tab 在 5 → 6 tab 中正确插入
- [ ] 5 视口回归（1440 / 1024 / 768 / 414 / 375）零破坏
- [ ] Lighthouse 性能分 ≥ 90

---

## 三、M1：4 年 FIFA 排名历史爬虫

### 3.1 数据源决策树

| 选项 | 源 | 频次 | 难度 | 价值 |
|---|---|---|---|---|
| (a) FIFA 官方 CSV | `fifa.com/fifa-world-ranking` 归档 | 每月 1 期 | 中 | 高（权威） |
| (b) Wikipedia | `World_Rankings_(men)` 历史表 | 每月 1 期 | 低 | 中（够用） |
| (c) 国际足联 Elo | `eloratings.net` | 每天 | 中 | 极高（细粒度） |
| (d) **不爬历史，只爬当前** | 现有 worldcup26.ir | 实时 | 0 | 0（已有） |

**推荐 (a)+(b) 组合**：F 官方 CSV 拉不到就用 Wikipedia，每月 1 期，48 期 = 4 年。

### 3.2 数据模型

新增表 `fifa_ranking_history`：
```sql
CREATE TABLE fifa_ranking_history (
    id INTEGER PRIMARY KEY,
    fifa_code VARCHAR(10) NOT NULL,
    rank INTEGER NOT NULL,
    points INTEGER NOT NULL,  -- 评分
    snapshot_date DATE NOT NULL,  -- YYYY-MM-DD 月度
    source VARCHAR(20) DEFAULT 'fifa.com',
    UNIQUE(fifa_code, snapshot_date)
);
CREATE INDEX idx_fifa_history_code_date ON fifa_ranking_history(fifa_code, snapshot_date);
```

### 3.3 爬虫规格

- 入口：`scripts/fifa_ranking_scraper.py`（独立脚本，不像 worldcup26_sync 进 FastAPI）
- 范围：2022-06 → 2026-06 共 48 期 × 48 队 = ~2300 条
- 速率：1 req / 3s 礼貌延迟，10 req 突发后 sleep 30s
- 失败重试：3 次指数退避
- 干跑模式：`--dry-run` 只打印不入库
- 增量模式：`--since 2025-01` 只拉指定日期后

### 3.4 落地

- 数据：写入 `fifa_ranking_history` 表
- 集成：扩展 `teams.elo_rating` 计算逻辑，叠加"近 12 个月 FIFA 均值"作为新因子
- 预测：`prediction.py` 读取时按需 join（不强制，影响小）

### 3.5 工时
- 爬虫本体：2h
- 表迁移 + 入库：1h
- 集成到 prediction：1h
- 测试 + 验证：1h
- **小计：5h**

---

## 四、T1：Alembic 迁移 + 3 个 schema 变更固化

### 4.1 现状

- 项目无 Alembic，schema 全靠 `Base.metadata.create_all`
- 3 个 schema 变更都已生效（通过 `Base.metadata.create_all` 后又手动 SQL 加字段）：
  - `teams`：`recent_form_points` + `recent_goal_diff` (B2)
  - `prediction_cache`：`payload_json` + `home_team_fingerprint` + `away_team_fingerprint` (F1)
  - `h2h_historical_matches`：新建表 (B3)

### 4.2 目标

1. 引入 Alembic（`pip install alembic` + `alembic init`）
2. 配置 `alembic/env.py` 指向项目 `Base.metadata`
3. **首次 migration**（stamp 已存在的 schema 为 baseline）：
   - 创建所有 9 个表的完整 `upgrade()` 脚本
   - 用 `alembic stamp head` 标记当前 DB 状态
4. **新增 3 个 migration 模拟 3 个变更**（让历史看起来正确）：
   - `001_add_teams_recent_form.py`：`ALTER TABLE teams ADD COLUMN recent_form_points, recent_goal_diff`
   - `002_extend_prediction_cache.py`：`ALTER TABLE prediction_cache ADD COLUMN payload_json, home_team_fingerprint, away_team_fingerprint`
   - `003_create_h2h_historical_matches.py`：`CREATE TABLE h2h_historical_matches ...`
5. **未来 schema 演进走 Alembic 正轨**（文档化约定）
6. **保留 `Base.metadata.create_all`** 作为零依赖启动兜底（但 dev/CI 走 alembic）

### 4.3 文件影响

| 文件 | 类型 | 增量 |
|---|---|---|
| `alembic.ini` | 新增 | ~30 行（默认） |
| `alembic/env.py` | 新增 | ~40 行（指向 Base） |
| `alembic/versions/0001_baseline.py` | 新增 | ~150 行（9 表 schema） |
| `alembic/versions/0002_teams_recent_form.py` | 新增 | ~30 行 |
| `alembic/versions/0003_prediction_cache_extend.py` | 新增 | ~30 行 |
| `alembic/versions/0004_h2h_historical_matches.py` | 新增 | ~40 行 |
| `requirements.txt` | 修改 | +1 行（alembic） |
| `app/main.py` | 修改 | +5 行（启动时跑 alembic check） |
| `app/db.py` | 不改 | 保留 Base.metadata.create_all |
| `docs/migrations.md` | 新增 | ~50 行（团队使用约定） |

### 4.4 验收标准

- [ ] `alembic current` → `004_h2h_historical (head)`
- [ ] `alembic history` → 显示 4 个 revision
- [ ] 全新 DB 执行 `alembic upgrade head` → 9 表齐全，字段无遗漏
- [ ] 现有 DB 执行 `alembic upgrade head` → 无差异（已 baseline）
- [ ] `alembic downgrade -1` 可回滚（验证 migration 可逆）
- [ ] `app/main.py` 启动时跑 `alembic upgrade head`（生产安全）

### 4.5 工时
- alembic 引入 + 配置：0.5h
- 4 个 migration 写：1.5h
- 验证（全新DB+现有DB）：1h
- **小计：3h**

---

## 五、总体执行顺序

```
Day 1（今天）
  ┌─ Phase 1: Define & Plan（本文件 + 用户确认）     0.5h
  ├─ Phase 2: B1 路线图                               6-8h
  └─ Phase 3: B1 验证（截图 × 5 视口）                1h
Day 2（明天）
  ├─ Phase 4: M1 爬虫 + 表 + 集成                     5h
  ├─ Phase 5: T1 alembic + 4 migration                3h
  └─ Phase 6: 总复盘 + 4 份验收报告                   1h
```

**总工时：约 17h**（含验证和文档）

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| worldcup26.ir 周末限流 | 中 | 路线图实时数据延迟 | 已实现 1 retry + 5min 缓存 |
| FIFA 官方 CSV 不可用 | 中 | M1 数据缺失 | fallback Wikipedia |
| Alembic baseline 与现 DB 不一致 | 中 | 启动报错 | 用 `alembic stamp` + 谨慎比对 |
| 32 强后节点全空 → 视觉空洞 | 高 | 用户体验差 | 明确空态卡 "等待小组赛出结果" + 模拟器联动 |
| 移动端 6 tab 太挤 | 中 | 操作困难 | 移动端折叠为抽屉入口（已实现 A11） |

---

## 七、待你拍板的 3 个问题

1. **M1 数据源**：选 (a) FIFA 官方 / (b) Wikipedia / (c) Elo 细粒度 / (d) 先不做？
2. **T1 含义**：我猜的对吗（B2/F1/B3 三个变更）？
3. **B1 路线图范围**：只做路线图（接受 R32+ 暂时空态） vs 顺便补充 R16/QF/SF/F 占位数据 vs 一起做路线图 + 补全数据？
