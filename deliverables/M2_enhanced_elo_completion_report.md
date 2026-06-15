# M2 增强 Elo 预测 (Elo + form + H2H) — 完成报告

**日期**: 2026-06-13
**作者**: 工序达
**范围**: 在 M1 Elo + Dixon-Coles 基础上加入 form/h2h 加权因子

---

## 1. 一句话总结

M1 Elo service **不破坏**，新增 `predict_match_enhanced()` + 新 API 端点 `/api/elo/predict-enhanced/{h}/{a}`，
返回 v1 (纯 Elo) vs v2 (Elo + form + h2h) 对比。**算法完整实现、数据基础有限、效果有限但已上线**。

---

## 2. 关键发现（先说结论）

| 项 | 数据基础 | 实际效果 | 评价 |
|---|---|---|---|
| **form 因子** | 48 队中 **仅 4 队** (MEX/KOR/RSA/CZE) 有 recent_form_points | ✅ 生效（-22.5 ~ -37.5 Elo 调整） | 数据稀薄但有效 |
| **H2H 因子** | 111 条记录（2018+2022 世界杯），14 对决有 ≥ 2 场样本，**几乎全部 50/50** 平衡 | ❌ 几乎不生效（home_rate=0.5 → boost=0） | 算法 OK，但巧合没偏向 |
| **Elo 主体** | 63 队有 Elo（48 队映射到本项目） | ✅ 完全生效 | 主力 |
| **未做** | walk-forward 回测 | 数据时间跨度不匹配（Hicruben 913 场无 form/h2h 字段） | 留给 M2.5 |

**诚实评价**：M2 的**算法已就绪并接入**，但**真实数据基础**（form 4 队 + H2H 50/50）让 v2 与 v1 **几乎无差异**。
**真正能演示效果的是 form 因子**（MEX vs CZE 案例：主胜概率从 63.67% → 65.41%）。

---

## 3. 算法设计

### 3.1 核心公式（service 层纯函数）

```python
def form_boost(form_points: Optional[int]) -> float:
    """近 5 场积分 (0-15) → Elo 调整"""
    if form_points is None: return 0.0
    return (form_points - 7.5) * 5   # 0 → -37.5, 7.5 → 0, 15 → +37.5

def h2h_boost(home_wins, away_wins, draws, sample) -> float:
    """H2H 胜率 → Elo 调整（主队视角）"""
    if sample < H2H_MIN_SAMPLES: return 0.0
    home_rate = home_wins / sample
    return (home_rate - 0.5) * 50    # 100% → +25, 50% → 0, 0% → -25

# M2 增强预测
effective_elo_home = base_elo_home + form_boost_home + h2h_boost_home
effective_elo_away = base_elo_away + form_boost_away - h2h_boost_home
v2_probs = match_prob(effective_elo_home, effective_elo_away, HOME_BONUS)
```

### 3.2 参数（已写入代码常量）

| 参数 | 值 | 决策依据 |
|---|---|---|
| `FORM_BOOST_SCALE` | 5.0 | 7.5 分（中位）→ 0 Elo；最高 15 分 → +37.5 Elo，< 1 个主场优势（70）的 50% |
| `H2H_BOOST_SCALE` | 50.0 | 全胜 → +25 Elo，< 主场优势一半（35），避免压过主场加成 |
| `H2H_MIN_SAMPLES` | 2 | 原 3 → 因当前 H2H max=2 不触发；降 2 让至少 14 对决可生效 |

### 3.3 设计原则

- **service 保持纯函数**：不依赖 DB，caller（router）注入 form/h2h 数据
- **H2H 对称处理**：主场 boost 多少，客场减多少，total Elo 差不变
- **透明**：v1 + v2 双返回，让前端对比"差异"而非"替代"

---

## 4. 交付物

| 类别 | 文件 | 增量 |
|---|---|---|
| **Service** | `app/services/elo.py` | +180 行（form_boost + h2h_boost + predict_match_enhanced + 5 常量） |
| **Router** | `app/routers/elo.py` | +80 行（Depends(get_db) + _query_h2h_for_boost + 新端点） |
| **API 端点** | `GET /api/elo/predict-enhanced/{h}/{a}` | 新增，**不破坏** `/api/elo/predict/{h}/{a}` |
| **测试** | 无新增（95/95 全过） | 算法逻辑由人工 case 验证（4 案例） |
| **报告** | 本文 | |

总计 +260 行（含注释）。

---

## 5. 案例验证（4 个对照）

### 5.1 MEX vs CZE（双方都有 form）—— **form 因子生效**

```
form_points: MEX=3, CZE=0
form_boost:  MEX=-22.5, CZE=-37.5
净效果:      CZE 降更多 → MEX 胜率上升

V1: 主胜 63.67%  平 23.23%  客胜 13.09%
V2: 主胜 65.41%  平 22.59%  客胜 12.00%
差异: 主胜 +1.74 pp
```

**结论**：form 因子让 v2 主胜概率微升，符合"MEX form=3 略好 vs CZE form=0 很差"。

### 5.2 MAR vs POR（有 2 场 H2H 历史但平衡）—— H2H 因子不生效

```
H2H: 2018 POR 1-0 MAR + 2022 MAR 1-0 POR
MAR 主视角: home_wins=1, away_wins=1, sample=2, home_rate=0.5
h2h_boost:   0（home_rate=0.5 → 0 Elo）

V1 = V2: 完全相同
```

**结论**：巧合各胜 1 场 → boost=0，H2H 不影响。

### 5.3 ARG vs NED（1 场 H2H）—— H2H 因子降级

```
H2H: 2022 8 强 ARG 2-2 NED (PK 4-3)
但 lookback=5 + 实际只有 1 场 → sample=1 < H2H_MIN_SAMPLES=2 → boost=0

V1 = V2: 完全相同
```

**结论**：数据不足时降级到 v1，行为正确。

### 5.4 UZB vs COD（无 form 无 H2H）—— 全降级

```
form: 双方 null
H2H:  0 条历史
V1 = V2: 完全相同
```

**结论**：干净降级，v2 保持 v1 行为。

---

## 6. API 输出格式示例（BRA vs ARG）

```json
{
  "home": {"fifa_code": "BRA", "elo": 1955},
  "away": {"fifa_code": "ARG", "elo": 1976},
  "v1": {
    "probabilities": {"home_win": 0.394, "draw": 0.2836, "away_win": 0.3225},
    "expected_goals": {"home": 1.47, "away": 1.32},
    "effective_elo": {"home": 1955, "away": 1976}
  },
  "v2": {
    "probabilities": {"home_win": 0.394, "draw": 0.2836, "away_win": 0.3225},
    "expected_goals": {"home": 1.47, "away": 1.32},
    "effective_elo": {"home": 1955.0, "away": 1976.0},
    "form_boost_home": 0.0,
    "form_boost_away": 0.0,
    "h2h_boost_home": 0.0,
    "h2h_boost_away": -0.0,
    "h2h_sample": 0
  },
  "factors": {
    "home_form": null, "away_form": null,
    "h2h_home_wins": 0, "h2h_away_wins": 0, "h2h_draws": 0, "h2h_sample": 0
  },
  "model": "elo_dixon_coles_v2",
  "data_source": "hicruben/world-cup-2026-prediction-model",
  "parameters": {
    "k_factor": 60, "home_bonus": 70, "dc_rho": -0.13,
    "form_boost_scale": 5.0, "h2h_boost_scale": 50.0, "h2h_min_samples": 2
  }
}
```

**结构说明**：
- `v1` / `v2` 双返回 → 客户端可视化对比
- `factors` → 透明展示 form/h2h 输入值
- `parameters` → 模型参数自描述（v2 新增 3 个）

---

## 7. 与 M1 predict_match 关系

| 项 | M1 (`/elo/predict/{h}/{a}`) | M2 (`/elo/predict-enhanced/{h}/{a}`) |
|---|---|---|
| **算法** | Elo + Dixon-Coles | Elo + form + H2H + Dixon-Coles |
| **service 函数** | `predict_match()` | `predict_match_enhanced()` |
| **返回** | 单一结果 | v1 + v2 对比 |
| **DB 依赖** | 无 | 查 form (Team) + H2H (Match + H2HHistoricalMatch) |
| **回测** | ✅ 4 年 walk-forward (913 场) | ❌ 未做（数据基础不匹配） |
| **可触发 form** | - | 4 队 (MEX/KOR/RSA/CZE) |
| **可触发 H2H** | - | 14 对决（但全 50/50） |
| **破坏性** | - | ✅ 不破坏（M1 端点 + service 行为不变） |

**前向兼容**：M1 所有 95 测试 + 5 端点保持原行为。

---

## 8. 未来增强 (M2.5 候选)

| 候选 | 内容 | 影响 | 工作量 |
|---|---|---|---|
| **动态 form** | 6/12 小组赛开打后，每场比赛结束后**自动**算该队近 5 场积分，写回 `Team.recent_form_points` | ✅ form 覆盖率从 8% → 100% | 1-2h（监听 finished match） |
| **H2H 数据回填** | 把 2010/2014/2018 完整赛果 + 历史国际赛爬回 h2h_historical_matches | H2H 样本从 2 场 → 5-10 场 | 4-6h（爬虫） |
| **walk-forward 回测 v2** | 在 Hicruben 913 场上**动态算 form + H2H** 重新跑 | 真实测 v1 vs v2 准确率 | 2-3h |
| **冠军概率** | 1000 次 Monte Carlo tournament sim，给每队夺冠% | 用户洞察 | 1-2h |

按 ROI 排序：**动态 form > walk-forward 回测 > H2H 回填 > 冠军概率**。
等小组赛开打（6/12）后，**动态 form** 可立即实施，让 M2.5 真正发挥威力。

---

## 9. Scope Discipline 检查

| 期望未做 | 实际 | 评价 |
|---|---|---|
| 改 M1 predict_match | ❌ 不动 | ✅ 守住：M1 测试 + 行为完全保留 |
| 改 Elo 数据集 | ❌ 不动 | ✅ 守住：Hicruben 913 场不动 |
| 改现有 95 测试 | ❌ 不动 | ✅ 守住：全过 |
| 写 H2H 爬虫回填 | ❌ 不做 | ✅ 守住：scope 外（4-6h） |
| Monte Carlo 冠军概率 | ❌ 不做 | ✅ 守住：M1.6 候选 |
| 修改 Cockpit / M1.5 Elo UI | ❌ 不动 | ✅ 守住：UI 完美，新功能靠新端点 |
| 真实 walk-forward 回测 | ❌ 不做 | ✅ 守住：诚实交代数据不匹配 |

---

## 10. 验收清单

| 项 | 状态 | 证据 |
|---|---|---|
| `predict_match_enhanced()` 实现 | ✅ | `app/services/elo.py` +180 行 |
| `form_boost` 公式 | ✅ | `(form - 7.5) * 5` 范围 -37.5~+37.5 |
| `h2h_boost` 公式 | ✅ | `(home_rate - 0.5) * 50` 范围 -25~+25 |
| H2H_MIN_SAMPLES=2 | ✅ | 让 14 对决可生效 |
| service 保持纯函数 | ✅ | predict_match_enhanced 不 import DB |
| 新 API 端点 | ✅ | `/api/elo/predict-enhanced/{h}/{a}` |
| M1 端点/行为 | ✅ | `/api/elo/predict/{h}/{a}` 不变 |
| 95/95 测试 | ✅ | 全过 |
| 4 案例验证 | ✅ | MEX/CZE form ✓ / MAR/POR H2H 平衡 / ARG/NED H2H 降级 / UZB/COD 全降级 |
| 数据基础诚实交代 | ✅ | form 4 队 / H2H 14 对决且全 50/50 |
| 不做 walk-forward 理由 | ✅ | Hicruben 913 场无 form/h2h 字段，时间跨度不匹配 |

---

## 11. 关联交付物

- M1 Elo 后端：`deliverables/M1_elo_completion_report.md`
- M1.5 前端 Elo 页：`deliverables/M1.5_elo_ui_completion_report.md`
- 本报告：`deliverables/M2_enhanced_elo_completion_report.md`
- README §七·D（待追加 M2 章节）
