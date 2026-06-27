# SnowSafe · GTA 冬季驾驶安全应用 — 报告与使用指南

> 把 9 个 GTA 城市（Toronto + 约克区 8 市）的雪天交通事故数据和实时天气叠加在一张地图上，帮助冬季通勤决策。
>
> 报告日期：2026-06-21 ｜ 数据范围：2014–2026（部分城市 2021–2025）

---

## 目录

1. [项目简介](#1-项目简介)
2. [数据来源](#2-数据来源)
3. [制作过程](#3-制作过程)
   - [3.1 验证（数据体检）](#31-验证数据体检)
   - [3.2 导出（清洗 + 统一）](#32-导出清洗--统一)
   - [3.3 可视化（地图图层）](#33-可视化地图图层)
4. [使用指南](#4-使用指南)
5. [数据质量说明](#5-数据质量说明)
6. [文件清单](#6-文件清单)

---

## 1. 项目简介

**SnowSafe** 是一个针对 GTA（大多伦多地区）的冬季驾驶安全 Web 应用。它把三个数据维度叠加在一张交互地图上：

- **历史碰撞热点**：把过去几年的交通事故按位置聚合，找出最危险的路口
- **雪量-事故相关性**：每个月的降雪量与事故数的对应关系，量化"下雪天有多危险"
- **实时天气**：调用 Open-Meteo 免费接口，显示当前路况风险等级

应用覆盖 9 个城市：Toronto、Markham、Richmond Hill、Vaughan、Aurora、Newmarket、King、Georgina、Whitchurch-Stouffville。

**特点**：
- 纯前端（vanilla JS + Leaflet），无后端、无数据库
- 数据预先生成成 JSON 文件，加载即用
- 离线友好（数据嵌入 / 可缓存）
- 移动端响应式，支持 GPS 定位

---

## 2. 数据来源

| 城市 | 来源 | 年份范围 | 原始行数 |
|------|------|---------|---------|
| Toronto | Toronto Open Data CSV | 2014–2026 | 809,034 |
| Markham | York Regional Police ArcGIS API | 2021–2025 | 28,511 |
| Richmond Hill | YRP | 2021–2025 | 17,044 |
| Vaughan | YRP | 2021–2025 | 41,919 |
| Aurora | YRP | 2021–2025 | 4,742 |
| Newmarket | YRP | 2021–2025 | 7,304 |
| King | YRP | 2021–2025 | 4,538 |
| Georgina | YRP | 2021–2025 | 3,945 |
| Whitchurch-Stouffville | YRP | 2021–2024 | 3,587 |

**降雪数据**：使用 Toronto 历史月度降雪量（2014–2026），整个 GTA 同气候带共享。

**天气数据**：[Open-Meteo](https://open-meteo.com/) 免费接口，客户端直连。

**社区边界**：York Region EDI 边界 GeoJSON + Toronto Neighbourhood 158。

---

## 3. 制作过程

### 3.1 验证（数据体检）

**目标**：在导出前摸清 9 个城市原始数据的质量。脚本：`etl/verify_collisions.py`，产出 `reports/collision_quality.md`。

**关键发现**：

1. **Toronto 16% 的记录坐标是 (0,0)**
   Toronto Open Data 用 `(0,0)` 表示"位置未知"，而不是 `NaN`。一开始误判为 13 万个"地理越界点"，深入看才发现全是占位符。修复：把 `(0,0)` 归类为 missing coords，不进入导出。

2. **YRP 数据大量重复**
   York Regional Police 的 ArcGIS API 分页拉取时页与页之间重叠，导致重复行：
   - Vaughan 36%、Markham 19%、RH 20%、Newmarket 24%
   - 共 28,811 行需要去重

3. **行人字段异常**
   8 个 YRP 城市里只有 Markham 和 Richmond Hill 的 `PEDESTRIAN` 字段有 YES 值，其余 6 个城市（Vaughan、Aurora、Newmarket、King、Georgina、Whitchurch-Stouffville）全是 NO。不是真的没行人事故，是 API 没返回这个字段。在地图上解读数据时要意识到这一点。

4. **自行车字段值不一致**
   Markham/RH 用 `Y` 表示是，其它字段（如 `INJURY_COLLISIONS`）用 `YES`。导出脚本统一识别 `YES`/`Y`/`TRUE`/`1`。

5. **月份格式不一致**
   Toronto CSV 用月份名（"January"），YRP 用数字（1–12）。导出时统一映射为数字。

6. **年份覆盖**（去重前）：
   - 2014–2019：每年 6.5–8 万行
   - 2020：4.5 万（疫情封锁）
   - 2021–2024：稳步增长到 10 万
   - 2025：6.7 万（部分年）
   - 2026：1.8 万（截至 6 月）

### 3.2 导出（清洗 + 统一）

**目标**：把两种 schema（Toronto / YRP）的原始 CSV 清洗成统一的紧凑 JSON，供前端按需加载。脚本：`etl/export_collisions.py`。

**清洗步骤**（按顺序）：

1. **过滤年份** — Toronto 自 2014 起，YRP 自 2021 起
2. **丢弃 (0,0) 坐标** — Toronto 的占位符
3. **去重** — 先全行去重，再按 `(year, month, lat, lng)` 事件级去重
4. **统一字段** — 把 `INJURY_COLLISIONS`、`PEDESTRIAN`、`InvolveCyclist`/`BICYCLE` 都规整为 0/1
5. **雪标志** — 合并月度降雪数据，月降雪量 > 0 即标记为雪天事故
6. **分层采样** — 每城市最多 5000 行，按 `(年, 是否受伤, 是否行人)` 分层，**稀有层（受伤/行人）全部保留**

**输出格式**（紧凑，每行约 60 字节）：

```json
{"city":"markham","generated_at":"2026-06-21T14:56:57+00:00",
 "total_clean":20088,"exported":4999,"capped":true,
 "fields":["lat","lng","y","m","s","i","p","c"],
 "collisions":[
   {"lat":43.86663,"lng":-79.30407,"y":2024,"m":7,"s":0,"i":0,"p":0,"c":0},
   ...
 ]}
```

字段含义：`y`=年、`m`=月、`s`=雪天、`i`=受伤、`p`=行人、`c`=骑车人。

**最终产出**：9 个城市 × 1 个 JSON = 38,265 条记录 / 2.7MB

| 城市 | 原始行 | 清洗后 | 导出 | 文件大小 |
|------|------:|------:|------:|---------:|
| Toronto | 809,034 | 373,887 | 5,000 | 351 KB |
| Markham | 28,511 | 20,088 | 4,999 | 351 KB |
| Richmond Hill | 17,044 | 11,968 | 5,000 | 351 KB |
| Vaughan | 41,919 | 25,394 | 5,000 | 351 KB |
| Aurora | 4,742 | 3,652 | 3,652 | 257 KB |
| Newmarket | 7,304 | 5,336 | 5,000 | 352 KB |
| King | 4,538 | 3,420 | 3,420 | 240 KB |
| Georgina | 3,945 | 3,288 | 3,288 | 231 KB |
| Whitchurch-Stouffville | 3,587 | 2,906 | 2,906 | 204 KB |

### 3.3 可视化（地图图层）

**目标**：在主地图加一个新的"Collisions"图层，显示所有 9 个城市的碰撞点。代码在 `index.html`。

**实现要点**：

- **懒加载**：toggle 第一次打开时才 fetch 9 个 JSON（并行 `Promise.all`），避免首屏负担
- **Canvas 渲染**：38k 个标记用 `L.canvas()` 而不是默认 SVG renderer，否则会卡
- **配色**（按严重度排序）：
  - 🟧 橙色 = 涉及行人
  - 🟥 红色 = 有人受伤
  - 🟦 蓝色 = 雪天事故
  - ⬜ 灰色 = 普通事故（仅财产损失）
- **弹窗**：点击任何标记显示日期、标志、坐标

---

## 4. 使用指南

### 4.1 启动应用

由于浏览器安全限制，**不能直接双击 `index.html`**（fetch 会失败）。需要起一个本地 HTTP 服务器：

**方法 1：Python（最简单）**

```bash
cd SnowSafe_v1
python3 -m http.server 8765
# 然后浏览器打开 http://localhost:8765/
```

**方法 2：Node**

```bash
cd SnowSafe_v1
npx serve .
# 或 npx http-server -p 8765
```

**方法 3：VS Code**

装 "Live Server" 扩展，右键 `index.html` → "Open with Live Server"。

> 手机测试：电脑和手机连同一 WiFi，把 `localhost` 换成电脑的局域网 IP（如 `http://192.168.1.x:8765/`）。

### 4.2 主要功能（顶部控制栏）

应用顶部有 5 个 toggle 开关，从左到右：

| 开关 | 功能 |
|------|------|
| **Snow** | 显示/隐藏雪天碰撞热点圆圈（默认开） |
| **Heatmap** | 切换为热力图视图（按碰撞密度） |
| **Snowfall** | 按年份/月份切换降雪量热力图 |
| **Weather** | 实时天气图层（Open-Meteo，每 10 分钟刷新） |
| **Collisions** | 🆕 全量碰撞点（38k 个，按严重度着色） |
| **Test Route** | 模拟一次驾车路线，看沿途风险 |

### 4.3 地图与图层解读

**默认视图**：打开后自动定位到 GTA 中心，能看到所有 9 个城市的碰撞热点圆圈。

**GPS 模式**：点左上角定位按钮，地图跟随你的位置。靠近危险路口会触发横幅警告（CAUTION / DANGER）。

**Collisions 图层使用建议**：
- **缩小看分布**：zoom ≤ 10 时，看哪些走廊最密集（Bayview/Yonge/Highway 7 沿线通常显著）
- **放大看单点**：zoom ≥ 13 时，能看清个别事故点
- **配色读法**：
  - 一片区域如果**红点多**，说明事故后果严重（受伤多）
  - 一片区域如果**蓝点多**，说明雪天是主要风险因素
  - 一片区域如果**橙点多**，行人事故频繁，居民区/学校附近要格外小心

**Click 任何标记** → 弹窗显示该事故的日期和标志。

### 4.4 数据解读注意事项

1. **采样**：Toronto 从 37 万条清洗后数据中采样了 5000 条（1.3%），单个区域看到的事故数不能直接比较绝对值。Markham/RH/Vaughan 也都采样到 5000。
2. **行人数据不全**：6 个 YRP 城市（非 Markham/RH）的行人事故数 = 0，是 API 字段缺失，不是真的没有。
3. **雪天定义**：本月降雪量 > 0 cm 即标记为雪天事故。这是月份级近似，不是当天是否下雪。
4. **历史数据**：雪量-风险倍率是基于历史数据计算的，对未来是参考不是预测。

---

## 5. 数据质量说明

完整数据质量报告：`reports/collision_quality.md`。

**已知限制**：

| 问题 | 影响 | 处理方式 |
|------|------|---------|
| Toronto 16% 行坐标缺失 | 这部分事故无法在地图显示 | 导出时丢弃 |
| YRP 重复行 19–36% | 计数虚高 | 导出时去重 |
| 6/8 YRP 城市无行人字段 | 这些城市看不到橙点 | UI 不强调这些城市的行人风险 |
| 月份格式不一致 | 处理逻辑分叉 | 统一映射为 1–12 |
| 自行车字段用 Y 不是 YES | 计数漏掉 | 统一识别 |
| Toronto 数据量极大 | 浏览器渲染卡顿 | 采样到 5000/city |

**数据未覆盖的事故类型**：
- YRP 不返回事故严重程度（仅 injured/non-injured）
- 没有 fatalities 字段（仅 Toronto 有，但 0 行使用）
- 没有时间（小时）字段（仅 Toronto 有，未在本应用使用）
- 没有天气状况字段（用月度雪量近似）

---

## 6. 文件清单

```
SnowSafe_v1/
├── README.md                          ← 你正在看的文件（中文版）
├── index.html                         ← 应用主体（80KB，纯前端）
├── data/                              ← 预生成数据（2.7MB）
│   ├── toronto.json                   ← 城市聚合数据（热点/社区/降雪）
│   ├── toronto_collisions.json        ← 该城市的碰撞点
│   └── ... × 9 城市
├── cities.json                        ← 城市配置（坐标、来源、年份）
├── reports/
│   └── collision_quality.md           ← 详细数据质量报告
├── etl/                               ← ETL 源码（Python，技术参考）
│   ├── verify_collisions.py           ← 数据验证
│   ├── export_collisions.py           ← 导出 + 采样
│   ├── run_pipeline.py                ← 主流水线
│   ├── risk_model.py                  ← 风险数学
│   ├── weather_parser.py              ← 天气解析
│   ├── config.py                      ← 城市配置加载
│   ├── fetch_traffic.py               ← 拉取碰撞数据
│   ├── fetch_snowfall.py              ← 拉取降雪数据
│   └── fetch_neighbourhoods.py        ← 拉取社区边界
└── tests/                             ← pytest 单元测试（33 个）
    ├── test_export_collisions.py
    ├── test_risk_model.py
    └── test_weather_parser.py
```

**重新跑 ETL（可选）**：

```bash
# 装依赖
pip install pandas shapely requests pytest

# 验证数据质量
python3 -m etl.verify_collisions

# 重新生成碰撞 JSON（默认每城市 cap=5000）
python3 -m etl.export_collisions
python3 -m etl.export_collisions --city markham --cap 10000  # 单城市 + 调大 cap

# 跑测试
python3 -m pytest tests/
```

> **注意**：本包不含原始 CSV（Toronto 单文件 167MB），重跑 `export_collisions` 之前需要先用 `etl/fetch_traffic.py` 重新拉取。

---

## 联系方式 / 反馈

如有问题或建议，欢迎反馈。本应用为个人项目，仅供 GTA 通勤参考，**非权威安全建议**。驾驶请遵守当地交通法规，注意路况。
