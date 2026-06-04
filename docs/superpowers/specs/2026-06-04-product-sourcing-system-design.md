# 跨境电商选品对比系统 — 设计文档

- 日期：2026-06-04
- 状态：已通过头脑风暴确认，待评审
- 方案：方案 A（轻量数据管道 + Metabase 看板）

## 1. 背景与目标

跨境电商公司，自家在 AliExpress（速卖通）和 Ozon 开店，并有内部 ERP 系统（含成本/库存，提供 API）。希望通过对比竞品平台商品与自家商品，辅助两类决策：

1. **选品机会发现**：找出自家没有、但竞品卖得好且有利润空间的新品。
2. **竞品监控**：对自家已有商品，监控对应竞品的价格/销量变化并预警。

**对比平台**：AliExpress + Ozon（后续可扩展更多平台）。
**数据获取方式**：已有的「Selenium 探测 + 内部接口回放」脚本（Seerfar / IXSPY / ERP），详见 §2.1。非官方开放 API。
**部署**：海外服务器（理由：竞品数据是高频大量拉取，必须稳；Ozon 服务器在俄罗斯，国内直连易超时；ERP 是自家数据可低频同步）。
**使用者**：多名运营，通过 Web 看板访问。
**团队约束**：技术较弱，借助 Claude + Codex 辅助开发，要求技术栈简单、AI 易维护。

## 2. 核心维度

- **必做**：价格、销量/订单、评价（含差评痛点挖掘）、利润空间估算、与自家商品对比。
- **二期再加**：趋势/季节性、竞争度。

## 2.1 数据来源与取数机制（已验证可行）

公司已有一套可运行的取数脚本（位于 `C:\Users\aibp\Desktop\518\apipy`），采用 **「Selenium 探测 + 内部接口回放」** 模式，**不是官方开放 API**：

- **`*_probe.py`**：用 Selenium + Chromedriver 登录目标站点，导航/筛选后捕获网页发出的内部 XHR/JSON 接口（含请求头、cookie、body），存为 `*_api_candidates.json`。
- **`*_fetch.py`**：挑出商品接口，带 cookie 翻页回放，导出 CSV 到 `input/<源>/<品类>/xxx_products.csv`。ERP 在 token 过期（code `401001`/401/403）时自动重跑 probe 刷新。
- 配置走根目录 `.env`（`PRODUCT_TYPE` 品类、ERP/IXSPY 凭证、`CHROMEDRIVER_PATH` 等），数据按**品类（PRODUCT_TYPE）分批**抓取。

**三个数据源与字段可得性（已验证）：**

| 源 | 取什么 | 关键字段 |
|---|---|---|
| **Seerfar** | 竞品/潜力市场热销品 | sales、origin_sales、sales_rate、**revenue、revenue_rate**、review_count、review_rating、price、category、image、seller、weight/dimension/volume、variants、fulfillment、labels |
| **AliExpress (IXSPY)** | 竞品商品 | sku、title、brand、category、image、price、product_url（当前脚本未抓 sales，销量以 Seerfar 为准） |
| **ERP** | 自家商品全量 | sku/main_sku、中英文名、类目、图片、供应商、**成本价、加权采购价/运费/分拣费、7/30/90天销量、单天销量、总订单量、一次毛利、库存周转天数、待发货/在途/异常/缺货数量、主售平台、主仓** |

**结论**：
- 竞品销量/收入问题由 **Seerfar 已解决**（相当于走第三方数据服务路线，已验证）。
- ERP **本就包含成本、库存、自家销量、毛利**等字段，利润估算所需数据齐全；当前 `erp_api_fetch.py` 仅解析了商品主数据，**需扩展解析以上字段**（列为实现任务）。
- 取数机制为"已登录会话回放内部接口"，介于官方 API 与爬虫之间：**比官方 API 脆弱**（token 过期、页面/接口变动、登录风控），需在编排层做好刷新与失败处理。

## 2.2 集成方式：复用编排现成脚本（方案 A）

新系统**不重写采集逻辑**，而是把现成 `probe + fetch` 脚本当作"采集器"：定时调度它们按品类跑出 CSV → 新系统的导入器把 `input/<源>/<品类>/*.csv` 自动加载进 PostgreSQL（原始层 + 标准层）→ 下游匹配/打分/看板照原设计。好处是不浪费已验证的成果、最快出价值。

## 3. 整体架构

四层架构，通过 PostgreSQL 解耦，各层只读上一层产出、写自己的结果：

```
服务器（Docker Compose）
  ① 数据采集层 Collectors（复用现成 probe+fetch 脚本，方案A）
     ├─ Seerfar     probe+fetch → input/seerfar/<品类>/*.csv
     ├─ AliExpress  probe+fetch → input/aliexpress/<品类>/*.csv
     ├─ ERP         probe+fetch → input/erp/<品类>/*.csv（需扩展成本/库存字段）
     └─ (后续) Ozon
            │  调度器按品类定时跑；token 自动刷新；失败隔离
            ▼
  ①.5 导入器 Importer
     读取 input/<源>/<品类>/*.csv → 校验/去重 → 写入 PostgreSQL
            │
            ▼
  ② 数据仓库 PostgreSQL
     原始表 raw_* → 标准表 products/prices/sales/reviews/erp_skus
            │
            ▼
  ③ 分析层 Analyzers
     ├─ 商品匹配引擎（跨平台 + 对自家 SKU）
     ├─ 利润估算
     ├─ 选品机会打分
     └─ 竞品监控（变化检测 → 预警）
            │
            ▼
  ④ 展示层 Metabase
     选品机会看板 / 竞品监控看板 / 匹配确认 / 预警
```

**设计原则**：
- 每层接口清晰、可独立测试，AI 改一层不牵连其它层。
- 采集与分析均为定时批处理（如每天凌晨错峰跑），无需实时架构。
- 新增平台只需新增一个采集器，下游基本不动。

**先定标准化数据契约，再写采集器**：在动手写任何平台采集器之前，先定义统一输出结构（契约）：`NormalizedProduct`、`PriceSnapshot`、`SalesSnapshot`、`Review`、`ErpSku`。每个平台采集器只负责把自己的 API 原始数据转换成这些标准结构。这样新增平台时下游（仓库/分析/看板）完全不用改。

## 4. 数据模型

### 原始层（保留 API 原貌，可溯源、可重解析）
- `raw_aliexpress`、`raw_ozon`、`raw_erp`：id、抓取时间、原始 json、来源 url。

### 标准层（统一结构，系统的"事实"）
| 表 | 内容 | 关键字段 |
|---|---|---|
| `products` | 全部商品（竞品+自家） | product_id（内部统一）、平台、平台商品ID、标题、类目、主图url、品牌、is_own |
| `price_snapshots` | 价格快照（按时间累积） | product_id、价格、币种、抓取时间 |
| `sales_snapshots` | 销量/评论/评分快照 | product_id、销量、评论数、评分、抓取时间 |
| `reviews` | 评论明细（差评挖掘） | product_id、评分、内容、时间 |
| `erp_skus` | 自家 SKU 成本/库存 | sku、成本价、库存、关联 product_id |

快照表（`price_snapshots`、`sales_snapshots`）必须定义**幂等与去重规则**：
- 唯一约束 `(platform, platform_product_id, observed_at)`，重复抓取以 upsert 处理，避免重复数据污染趋势/预警。
- 区分两个时间字段：`observed_at`（数据反映的业务时点）与 `collected_at`（我们实际抓取的时点）。

### 运维层（采集运行与失败追踪）
| 表 | 内容 |
|---|---|
| `collector_runs` | 每次采集的开始/结束时间、状态、平台、处理数量 |
| `collector_errors` | 失败商品、错误原因、重试次数 |
| `source_cursors` | 每个平台的增量游标 / 上次成功同步时间 |

### 分析层（系统产出，喂给 Metabase）
| 表 | 内容 |
|---|---|
| `source_product_links` | 多源同一 listing 归一化（见 §4.1）：source、source_record_id、规范键 (platform, platform_product_id)、归一化到的 product_id |
| `product_matches` | 匹配关系（跨平台同款 / 关联自家SKU）、置信度、**状态（pending/confirmed/rejected/auto_confirmed）、确认人、确认时间、否决原因** |
| `profit_estimates` | 利润估算（拆"确定成本/估算成本" + 置信等级，见 §6） |
| `opportunity_scores` | 选品机会分 + 推荐理由 |
| `alerts` | 竞品监控预警事件 |

**设计要点**：
1. 快照表按时间**累积不覆盖**，支撑趋势与预警（如"7 天降价 20%"），并遵守上述幂等/去重规则。
2. `products` 用统一内部 `product_id`，跨平台同款通过 `product_matches` 关联，而非塞进一行。
3. `product_matches` 保留完整审核状态与历史，便于后续调阈值和排查错配。

## 4.1 跨数据源商品归一化（同一 listing 的多源合并）

竞品数据来自多个源（Seerfar 给销量/收入/排名，IXSPY 给 AliExpress 商品详情），**同一个平台 listing 可能在两个源都出现**，必须先合并成同一个"竞品商品"，否则销量和详情对不上、机会分失真。

**已验证的事实**：
- Seerfar 记录含 `sku`（= 平台商品ID）和 `productUrl`（平台规范链接，如 `https://www.ozon.ru/product/{id}`、AliExpress 为 `/item/{id}.html`）。
- IXSPY/AliExpress 记录含 `product_url`，并用 `/item/(\d+)\.html` 解析出 `sku`（= AliExpress item id）。

**归一化规则（确定键优先，模糊兜底）：**
1. **抽取规范键**：对每条竞品记录，从 `productUrl` 解析出 `(platform, platform_product_id)` 作为规范标识（platform 由域名判定：ozon.ru→ozon，aliexpress→aliexpress）。
2. **确定关联**：`(platform, platform_product_id)` 相同的记录直接判定为同一 listing，合并字段（Seerfar 的销量/收入/排名 + IXSPY 的详情），写入统一表 `source_product_links`（记录 source、source_record_id、归一化到的 product_id）。
3. **模糊兜底**：极少数无法解析出稳定 ID 的记录，才用标题+图片+价格+店铺+类目做候选匹配（复用 §5 的多信号打分），低置信进人工确认队列。
4. **置信约束**：关联置信度低时**不得直接合并销量与利润**；机会分（§6）**只使用"确定关联"或"高置信关联"的数据**，否则在看板标注"数据来源不完整"。
5. Ozon 竞品目前 Seerfar 单源即覆盖，无需跨源合并；该规则主要服务 AliExpress（Seerfar × IXSPY）及未来新源。

**附带改进**：现有 `seerfar_api_fetch.py` 的 flatten 丢弃了原始响应中的 `profit、grossMargin、categoryRank、naturalRank、adRank、orderConversionRate、returnCancellationRate、views、missedRevenue` 等有价值字段，扩展解析时一并纳入（对机会打分有用）。

## 5. 商品匹配引擎（核心难点）

目标：①两个跨平台商品是否同款；②竞品对应自家哪个 SKU（或属于空缺）。

**做法：多信号打分 + 人工确认（半自动，不追求全自动）**

匹配信号（逐步叠加）：
1. **类目 + 关键词**（一期必做）：标题分词、品牌、型号、规格的文本相似度。
2. **图片相似度**（一期建议做）：图像向量/感知哈希比主图。跨境同款常用同供应商图，图片是较强信号，但**一期保守使用——感知哈希只用于候选召回和辅助打分，不单独作为自动匹配依据**（同模板不同商品易误判）。自动确认阈值宁可设高，多留给人工确认。
3. **价格/规格辅助校验**（二期）：作为加权项。

流程：
```
候选生成（同类目下关键词/图片初筛 Top-N）
  → 多信号加权打分 → 置信度
  → 高置信度：标记 auto_confirmed（阈值设高，宁缺毋滥）
  → 中置信度：进"待人工确认"队列，运营在确认入口确认/否决
  → 确认结果回流 product_matches，用于调参
```

**人工确认入口（不用 Metabase 写入）**：Metabase 是只读 BI，不适合做确认/否决的写入闭环。一期单独设计一个**轻量确认入口**——可以是一个简单的 Admin 页面（如 FastAPI + 最小化模板，或 Streamlit），或者一期先用 **CSV/Excel 导入确认结果**。确认结果稳定回流 `product_matches` 是匹配闭环的关键，必须有独立写入路径。

**为什么半自动**：跨平台语言（俄/英/中）和规格写法差异大，纯自动必有错配，错配会让利润和选品分全错。匹配**不全量做**，只对"值得关注的高潜力竞品"做，人工量可控，且随确认数据积累阈值越调越准。

## 6. 两大核心功能

### 利润估算（拆细 + 置信等级）
原"售价−成本−佣金−物流"过于简化。跨境电商实际还涉及汇率、平台佣金档位、广告费、优惠券、退货损耗、税费、头程/尾程物流等。因此：
- 把成本拆成 **确定成本** 和 **估算成本**：
  - **确定成本**直接来自 ERP：`成本价`、`加权采购价`、`加权运费`、`加权分拣费`（ERP 已提供，质量高），ERP 还直接给了 `一次毛利` 可作交叉校验。
  - **估算成本**：平台佣金档位、广告费、优惠券、退货损耗、税费、汇率波动等需估算项。
- 每条利润估算给出**置信等级 high/medium/low**：确定成本（ERP 实际值）占比越高、估算项越少 → 置信越高。
- 看板展示利润时一并展示置信等级，避免用估算值误导运营做决策。
- 注意：ERP 成本/毛利对应**自家 SKU**；对**竞品**只能用其售价（Seerfar/IXSPY）− 估算的同类采购成本来推算潜在利润，置信天然偏低，需标注清楚。

### 功能一：选品机会发现（新品）
针对自家没有、竞品卖得好的商品打分：
```
机会分 = 销量/订单热度 × 利润空间 × 评价质量 − 竞争惩罚
```
- 一期用**规则加权打分**（透明、可解释、易调），不上机器学习（YAGNI）。
- 每个推荐附**理由**（如"Ozon 月销 2000+、估算毛利率 35%、自家无同款"）。
- 差评痛点挖掘：对高潜力竞品差评做关键词聚合，给出差异化改进点。

### 功能二：竞品监控（现有商品）
针对已匹配到自家 SKU 的竞品监控变化、出预警：
- 竞品降价超阈值 → 跟价提示（结合成本算利润空间）。
- 竞品销量突增 → 关注提示。
- 竞品断货/下架 → 抢量提示。
- 自家定价高/评分低于竞品 → 调整提示。
- 预警写入 `alerts`，Metabase 做监控看板 + 可选每日推送。

### 两个 Metabase 看板
1. **选品机会看板**：机会分排序的竞品列表，按类目/利润率/销量筛选，详情含理由。
2. **竞品监控看板**：自家 vs 竞品对照、预警列表、价格/销量趋势图。

## 7. 可靠性、技术栈与部署

### 采集可靠性
- **token/会话刷新**：内部接口回放依赖登录 cookie/token，过期时自动重跑对应 probe 刷新（ERP 已实现，Seerfar/IXSPY 比照）。
- **限速** + 失败指数退避重试，避免触发风控/被封号。
- **失败隔离**：单源/单品类/单商品失败不中断整批。
- **原始数据先落库**：先保存 fetch 的原始 JSON/CSV 再解析入标准层，解析逻辑可重跑而不重新抓取。
- **定时调度**：APScheduler 或 cron，按源 + 品类（PRODUCT_TYPE）错峰循环。

### Selenium/Chromedriver 与部署位置的权衡（需复核）
采集依赖**有头/无头 Chrome + Chromedriver 登录** ERP、Seerfar、IXSPY，这给"海外服务器"决策带来新约束：
- **ERP 在国内**（如 `http://103.198.125.2:8077`），海外服务器登录它会慢、甚至需专线/代理。
- **Seerfar / IXSPY 登录**从陌生（海外）IP 可能触发验证码/风控，而这些工具的数据多面向国际，国内访问也未必稳。
- 因此部署位置要在"离 ERP 近（国内）"与"离竞品源/看板访问近（海外）"之间复核。**可选拆分**：采集脚本跑在离数据源合适的机器（甚至沿用现有国内环境）只产出 CSV，PostgreSQL + 分析 + Metabase 跑在服务器，两者通过 CSV/数据库同步解耦。最终位置在实现前结合实测确定。

### 技术栈
| 层 | 选型 | 理由 |
|---|---|---|
| 语言 | Python | AI 友好、库全 |
| 采集/分析 | Python + requests/httpx | 简单直接 |
| 调度 | APScheduler 或 cron | 轻量 |
| 数据库 | PostgreSQL | 稳、JSON 支持好、Metabase 原生支持 |
| 图片匹配 | 一期感知哈希，必要时升级 CLIP 向量 | 由简到繁 |
| 看板 | Metabase（Docker） | 现成、免写前端 |
| 部署 | 海外服务器 + Docker Compose | 一键编排 Python 服务 + PostgreSQL + Metabase |

### ERP 连接
ERP 在国内、服务器在海外 → 采集器设计为**低频定时同步**（如每天 1 次成本/库存），做好超时重试。

### 密钥与配置管理
API key、ERP 凭证、数据库密码**严禁写死**在代码或配置样例里。从第一版起：
- 所有密钥/凭证走 `.env`，并提供 `.env.example`（只有键名、无真实值，可入库）。
- 真实 `.env` 加入 `.gitignore`，不入库。
- Docker Compose 只引用环境变量。

## 8. 分期落地

### 第零步（实现前准备）
- **扩展 `erp_api_fetch.py` 解析**：补出成本价、加权采购/运费/分拣费、7/30/90天销量、库存（待发货/在途/缺货）、一次毛利、主售平台等字段（利润估算依赖）。
- **扩展 `seerfar_api_fetch.py` 解析**：纳入 profit、grossMargin、categoryRank、orderConversionRate、returnCancellationRate、views 等被丢弃的字段；确保保留 sku/productUrl（归一化键）。
- 实现 §4.1 的**规范键抽取**（从 productUrl 解析 platform + platform_product_id）。
- 定义 §3 的**标准化数据契约**（NormalizedProduct / PriceSnapshot / SalesSnapshot / Review / ErpSku），并确认现有 CSV 列能映射过去。
- 复核部署位置（§7 Selenium 与国内/海外权衡）。

### 第一期（MVP，跑通一条链路）
- 数据源：**Seerfar（竞品销量）+ AliExpress/IXSPY（竞品）+ ERP（自家成本/库存/销量）**。
- 链路：调度现成 probe+fetch 出 CSV → **导入器**入 PostgreSQL → 利润估算（含置信等级）→ **选品机会看板**（规则打分）。
- 商品匹配：关键词 + 感知哈希图片（保守用），半自动 + 轻量确认入口。
- **差评痛点挖掘一期只保留表结构与接口占位**，实际分析放第二期。
- 目标：验证数据能拉通入库、机会分有没有用。

### 第二期（补全平台与监控）
- 接入 Ozon（采集器 + 自家 Ozon 店铺）。
- 上线竞品监控看板 + 预警（依赖快照数据已积累）。
- 差评痛点挖掘。

### 第三期（增强）
- 趋势/季节性、竞争度维度。
- 预警推送（飞书/钉钉/邮件）。
- 图片匹配升级 CLIP 向量。
- 用积累的人工确认数据调优匹配阈值。

### 后续
- 新增平台只写新采集器，下游复用。

## 9. 范围之外（YAGNI）

- 实时采集架构（一期用每日批处理足够）。
- 机器学习选品模型（先用规则打分）。
- 全自动商品匹配（错配代价过高，坚持半自动）。
- 全定制前端（看板用 Metabase；仅匹配确认用最小化写入入口）。

## 10. 待定决策

- **部署位置**（见 §7）：采集脚本依赖 Chrome 登录国内 ERP + 国际 Seerfar/IXSPY，海外/国内/拆分三种形态需结合实测确定。
- **Ozon 竞品数据来源**：二期接入 Ozon 时，确认走 Seerfar（若覆盖 Ozon）还是单独的 probe+fetch。
- **现有 518 项目的代码复用边界**：新系统是直接调用 `apipy` 脚本，还是把它们作为子模块/独立服务封装（实现计划阶段细化）。
