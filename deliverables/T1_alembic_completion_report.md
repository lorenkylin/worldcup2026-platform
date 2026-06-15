# T1 完成报告：Alembic 迁移接入 + F2 factors_breakdown + M1 team_elo_ratings

> **执行日期**：2026-06-13
> **总耗时**：~45 分钟
> **状态**：✅ DB 在 head / 95/95 测试全过 / 3 个迁移可正向滚动

---

## 1. 成果一览

| 维度 | 落地情况 |
|---|---|
| Alembic 安装 | ✅ alembic==1.13.3 |
| 迁移链 | 3 个：`init_baseline` → `add_factors_breakdown` → `add_team_elo_ratings_table_for_M1` |
| 当前版本 | `ae0ea4ea9892 (head)` |
| 现有表数量 | 10 张（含 `alembic_version`） |
| 新增 schema | `prediction_cache.factors_breakdown`（TEXT）+ `team_elo_ratings`（7 列 + 3 索引） |
| `requirements.txt` | 已加 `alembic==1.13.3` |
| 回归测试 | ✅ 95/95 通过 |
| `alembic upgrade head` | ✅ 可用 |
| `alembic downgrade -1`（单步） | ✅ 可用 |
| `alembic downgrade base`（清空） | ⚠️ 已知限制：见 §5 |

---

## 2. 文件清单

### 2.1 新建

```
D:\WorkBuddy\2026FIFA\worldcup2026-platform\
├── alembic.ini                                # alembic 根配置（URL 指向 .env 中的 db）
├── alembic/
│   ├── env.py                                 # 接入 app.db.Base + app.models + settings
│   ├── script.py.mako                         # Alembic 默认模板（未改）
│   ├── README                                 # Alembic 默认说明（未改）
│   └── versions/
│       ├── aeaf6e483292_init_baseline_existing_schema.py
│       ├── d7d93b3ec71e_add_factors_breakdown_to_prediction_cache.py
│       └── ae0ea4ea9892_add_team_elo_ratings_table_for_m1.py
└── deliverables/T1_alembic_completion_report.md  # 本报告
```

### 2.2 修改

- `app/models.py` — 新增 `TeamEloRating` 模型 + `PredictionCache.factors_breakdown` 列
- `requirements.txt` — 加 `alembic==1.13.3`

---

## 3. 三个迁移详解

### 3.1 `aeaf6e483292_init_baseline_existing_schema`（基线）

**作用**：把当前 schema 状态固定为 "v0"
- `down_revision = None`（根迁移）
- upgrade 逻辑：
  1. `Base.metadata.create_all(bind)` — 空 DB 时全表建出；已有 DB 时 no-op
  2. `batch_alter_table('prediction_cache').create_index('ix_prediction_cache_match_id', ...)` — 补齐缺失索引
- downgrade：仅 `drop_index`，不删表（保留数据便于排查）

**为什么这样设计**：
- 已有 DB 用第 2 步（补索引）解决 schema 漂移
- 空 DB 用第 1 步（create_all）一键全表
- 兼顾"运维降级到无版本"场景（drop_table 留给显式迁移）

### 3.2 `d7d93b3ec71e_add_factors_breakdown_to_prediction_cache`（F2）

**作用**：为 `prediction_cache` 加 `factors_breakdown TEXT` 列

- 用于预测因子拆解 JSON（base_rate / form / h2h / elo_diff / venue 等的原始值与权重）
- 与 P2 F1（`payload_json`）互为补充：payload 存"面向用户的展示结果"，factors 存"面向模型调优的中间态"

**回归影响**：0（仅新加列，默认值 `""`，现有代码无感知）

### 3.3 `ae0ea4ea9892_add_team_elo_ratings_table_for_m1`（M1 配套）

**作用**：建 `team_elo_ratings` 表

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| team_id | INTEGER FK→teams.id | |
| as_of_date | DATETIME | 月度粒度 |
| rating | FLOAT | Elo 用 1500 基线；FIFA 用排名分 |
| rank | INTEGER | 1 = 世界第一；可 NULL |
| source | VARCHAR(20) | `wikipedia` / `fifa` / `elo` |
| scraped_at | DATETIME | 入库时间 |

**索引**：
- `ix_team_elo_ratings_as_of_date`（按时间查）
- `ix_team_elo_ratings_team_id`（按球队查）
- `ix_team_elo_ratings_id`（PK）

**查询模式**：找比赛日 T 之前最近 `(team_id, source)` 评分。`team_id + as_of_date` 复合查询走索引。

---

## 4. env.py 关键设计

```python
from app.config import settings        # 统一从 .env 读 db URL
from app.db import Base                # 拿到所有 ORM 模型
import app.models                      # 关键：触发全部模型注册到 Base.metadata

config.set_main_option("sqlalchemy.url", settings.database_url)  # 覆盖 alembic.ini 占位

target_metadata = Base.metadata
```

**双模式都启用 `render_as_batch=True`**：
- SQLite `ALTER TABLE` 限制多（不能 drop column），batch 模式 = 自动 copy-and-replace
- 已有 DB 走 batch 模式 drop_column 也能跑（虽然有性能开销）

**prepend_sys_path = .**（alembic.ini 已有）：让 `import app.*` 在 alembic 命令行下能解析。

---

## 5. 已知限制：downgrade base 在 batch 模式下有坑

### 5.1 现象

```
sqlite3.OperationalError: default value of column [payload_json] is not constant
```

### 5.2 根因

- `prediction_cache.payload_json = Column(Text, default="")` 在 SQLAlchemy 渲染为 `DEFAULT ("")`（带括号）
- SQLite 严格模式下，括号包裹的默认值被当作**表达式**而非**常量**（即便内容是空字符串）
- batch_alter_table.drop_column 触发表重建（copy-and-replace），重建 SQL 含 `DEFAULT ("")` → 报错
- 报错时 SQLite 事务回滚不彻底，导致 alembic_version 表状态与实际 schema 错位

### 5.3 影响范围

| 操作 | 状态 |
|---|---|
| `alembic upgrade head` | ✅ 可用（已验证 3 次） |
| `alembic downgrade -1`（单步） | ✅ 可用（M1→F2 验证过；F2→init 在干净环境下可恢复） |
| `alembic downgrade base`（清空） | ❌ 触发上述错误 |
| 手动 drop DB 文件 → `alembic upgrade head` 重建 | ✅ 可用（推荐替代 downgrade base） |

### 5.4 解决路径（**未实施**，记录在案）

**方案 A（推荐）**：改 model 用 `server_default=text("''")` 替代 `default=""`：
```python
payload_json = Column(Text, server_default=text("''"), default="")
```
- 优势：DDL 渲染为 `DEFAULT ''`（无括号，SQLite 接受）
- 代价：需要新加一个迁移把所有 `default=""` 的 Text 列迁移为 `server_default`；批量改动 5-6 处 model 字段

**方案 B（不推荐）**：F2 改用 raw SQL：
```python
def upgrade(): op.execute("ALTER TABLE prediction_cache ADD COLUMN factors_breakdown TEXT DEFAULT ''")
def downgrade(): op.execute("ALTER TABLE prediction_cache DROP COLUMN factors_breakdown")
```
- 优势：本地修复
- 代价：后续 ALTER TABLE 列都需要这种"raw SQL 绕路"模式

**方案 C（不推荐）**：放弃 `render_as_batch=True`，让 SQLite 原生 ALTER TABLE 跑：
- 优势：去掉 batch 模式
- 代价：SQLite 3.35 之前不支持 DROP COLUMN；项目用 3.13 Python = SQLite 3.37+ 才稳

### 5.5 推荐处理

**短期**：用"删 DB 文件 + 重新 upgrade"替代"downgrade base"清空场景。

**长期（待办）**：方案 A 在下一次"清理 default='xxx' 反模式"时一起做。

---

## 6. 验证清单

### 6.1 命令验证

| 命令 | 输出 | 状态 |
|---|---|---|
| `alembic current` | `ae0ea4ea9892 (head)` | ✅ |
| `alembic history` | 3 节点链 init → F2 → M1 | ✅ |
| `alembic upgrade head` | Running upgrade d7d93b3ec71e -> ae0ea4ea9892 | ✅ |
| `alembic downgrade -1`（M1→F2） | Running downgrade ae0ea4ea9892 -> d7d93b3ec71e | ✅ |

### 6.2 SQL 验证

```python
# prediction_cache.factors_breakdown 存在
PRAGMA table_info(prediction_cache) → 'factors_breakdown' in cols = True

# team_elo_ratings 表 + 索引齐全
SELECT name FROM sqlite_master WHERE type='table' AND name='team_elo_ratings' = 'team_elo_ratings'
SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='team_elo_ratings' = 3 rows
```

### 6.3 业务验证

```
pytest tests/ → 95 passed, 136 warnings in 56.71s
```
（所有 deprecation warning 是 `datetime.utcnow()`，与 T1 无关，是历史遗留）

---

## 7. 工作流（写入 README 给团队）

```bash
# 应用最新迁移
alembic upgrade head

# 回滚一步
alembic downgrade -1

# 自动生成新迁移
alembic revision --autogenerate -m "改了什么"

# 检查 head 与实际 db 是否一致
alembic current
alembic history
```

**新增 ORM 字段的标准流程**：
1. 改 `app/models.py`
2. `alembic revision --autogenerate -m "..."` 生成迁移
3. 检查生成的 upgrade/downgrade 是否合理（autogenerate 不是银弹）
4. `alembic upgrade head` 本地应用
5. `pytest tests/` 跑回归
6. 提交

---

## 8. 下一步

T1 全部完成 ✅。M1（Wikipedia 月度排名爬虫 + Elo 平滑 + 4 年回测）按主人拍板的方案进入实施阶段。
