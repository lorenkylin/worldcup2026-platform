# StatsBomb Open Data 署名

本项目使用 [StatsBomb Open Data](https://github.com/statsbomb/open-data) 训练了一套对比 Elo 评分。

## 使用条款

StatsBomb Open Data 允许免费用于研究和公开分析，但要求：

> 如果发布、分享或分发基于该数据的研究、分析或洞察，请注明数据来源为 StatsBomb 并使用其 logo。

## 本项目用法

- StatsBomb 评分仅作为 **对比数据源**，默认主模型仍为 Hicruben Elo。
- 覆盖赛事：世界杯 2018/2022、欧洲杯 2020/2024、美洲杯 2024、非洲杯 2023。
- 衍生产物：`data/seed/statsbomb/statsbomb_elo.json`（各队 Elo 评分）。

## API 中的 attribution

所有返回 StatsBomb 数据的 API 响应均包含：

```json
{
  "data_source": "statsbomb/open-data",
  "attribution": "StatsBomb data provided by StatsBomb. Used under open data terms."
}
```

---

Data provided by **StatsBomb**.
