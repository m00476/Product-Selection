# IXSPY 自动下载 + 双筛一条龙 设计（方案 1）

日期：2026-06-16
状态：已与用户确认方向，待 spec 评审

## 目标

把现在**手动**的"登录 IXSPY 网站 → 设筛选 → 点数据导出 → 下载压缩包 → 解压"这一步自动化，
让用户**只给一个品类名**，程序就自动：登录下载 → 解压 → 双筛 → 出老板版报告。

## 范围（用户已确认）

- **一次 1 个品类**，**手动触发**（不是批量、不是定时）。
- 筛选以**类目**为主；**首次发现时间**等条件留作可选参数（以后再用）。
- 采用**方案 1：模拟点击导出**（驱动页面点"数据导出"按钮拿官方压缩包），
  不做接口逆向（方案 2 以后嫌慢再说）。
- 产出的压缩包与用户现在手动下载的**完全一致**，因此**下游双筛流程零改动**。

## 现有可复用代码

`src/sourcing/collect/aliexpress_api_probe.py`：
- `get_login_token_url()` — 用 .env 的 IXSPY 账号登录，返回带 token 的 URL
- `build_driver_with_network_logs()` — 起 Selenium Chrome（含 headless 开关）
- `search_category(driver, category_name)` — 类目框输入 + 选联想项 + 点搜索
- `should_fail_category()`（probe_util）— 类目没选中 fail-fast
- 页面常量 `https://ixspy.com/data#/product/new-product-grow`

`src/sourcing/platform_export_pipeline.py`：
- `run_from_download(src, base_dir, ...)` — 给一个文件夹即自动整理+解析+双筛+报告
- `prepare_from_download` / `_find_export_source` — 自动找 .xls+images、推导 slug/批次

## 架构与组件

```
[双击 bat] 输入品类名
      │
      ▼
ixspy-auto 命令 (cli.py)
      │
      ├─ ① ixspy_download.download_export(category, download_dir, ...)   ← 新模块
      │     登录 → 进新品增长榜页 → 选类目(+可选筛选) → 点"数据导出"
      │     → 等浏览器把 zip 下到 download_dir → 返回 zip 路径
      │
      ├─ ② _extract_zip(zip) → 解压目录                                  ← 新
      │
      └─ ③ run_from_download(解压目录, category_name=品类名)             ← 复用(加1个参数)
            自动 解析 → ERP图搜 → DINOv2精筛 → 老板版报告 → 自动打开
```

### 新模块 `src/sourcing/collect/ixspy_download.py`

- `download_export(category, *, download_dir, filters=None, driver_factory=None, timeout=600) -> Path`
  1. 复用 `get_login_token_url()` + 起带"指定下载目录"的 Chrome（设 `download.default_directory`，禁下载弹窗）
  2. 打开新品增长榜页，`search_category` 选类目；若 `should_fail_category` 命中 → 抛错并截图
  3. （可选）设置 `filters`（如首次发现时间起止）——首版可只占位，留扩展点
  4. 点"数据导出(下载压缩包...)"按钮
  5. `_wait_for_download(download_dir, timeout)` 轮询：出现 `*.zip` 且无 `*.crdownload`、大小稳定 → 返回该 zip
  6. `driver.quit()`
- `_wait_for_download(download_dir, timeout, *, sleep, now) -> Path`（纯逻辑、可注入时钟/列目录，便于测试）
- `_extract_zip(zip_path, dest_dir) -> Path`（解压，返回解压根目录）

### CLI 命令 `ixspy-auto`

`python -m sourcing.cli ixspy-auto --category "汽车及零配件" [--headless] [--limit N]`
- download_dir 默认项目下 `_downloads/ixspy/`（受控，便于检测）
- 调 download_export → _extract_zip → run_from_download（传入已知 `category_name`）
- 打印并自动打开报告目录

### 触发 bat `ixspy-自动下载双筛.bat`（纯 ASCII 内容，避免 GBK 闪退）

```
双击 → 提示 "输入品类名:" (set /p) → 回车 → 跑 ixspy-auto → 完成打开报告
```

## 关键设计决策

1. **下载目录受控**：用 Chrome `download.default_directory` 指到项目内 `_downloads/ixspy/`，
   不用默认"下载"文件夹，方便准确检测"这次下的是哪个 zip"。每次跑前清空该目录。
2. **下载完成检测**：轮询目标目录，等到有 `.zip`、无 `.crdownload`、且大小连续两次不变 → 判定完成；
   超时（默认 10 分钟，导出带图片可能较大）→ 抛错截图。
3. **品类名显式传入**：解压出来的是 `Product_xxx` 目录（无中文名），而我们**已知**用户输入的品类名，
   故给 `run_from_download` / `prepare_from_download` 加可选 `category_name` 覆盖参数，
   不再从文件夹名猜（slug 仍由该中文名转拼音生成，与拖拽流程一致）。
4. **筛选可扩展**：`filters` 设计成可选 dict（首版只实现类目；首次发现时间留接口），避免一次做太多。

## 错误处理

| 情况 | 处理 |
|---|---|
| 登录失败 / 验证码 | 抛错 + 截图保存到下载目录，提示人工处理 |
| 类目没选中 | `should_fail_category` fail-fast，抛错截图（不静默下错品类） |
| 导出按钮找不到 | 抛错 + 截图 |
| 下载超时 | 抛错 + 截图，保留已下文件供排查 |
| ERP token 过期等下游问题 | 双筛环节已自愈，无需在此处理 |

## 测试策略

- **可单测**（纯逻辑、注入依赖）：
  - `_wait_for_download`：注入"列目录"函数 + 时钟，覆盖"出现zip→完成""一直没好→超时""有crdownload时不算完成"
  - `_extract_zip`：用 tmp 里造个小 zip，验证解压出文件
  - `run_from_download` 的 `category_name` 覆盖：验证传入时用它、不传时仍按原逻辑
- **不单测（需真浏览器）**：登录、选类目、点导出——靠一次真实冒烟跑验证（`--headless` 关掉盯着看第一次）。

## YAGNI（本期不做）

- 多品类批量、定时调度（用户明确只要单品类手动）
- 导出接口逆向（方案 2）
- 首次发现时间等高级筛选的完整实现（只留参数接口）

## 验收标准

- `ixspy-auto --category "<某品类>"` 能：自动登录、下载该品类 zip、解压、跑完双筛、生成
  `output/platform_export_match/ixspy/<拼音slug>/<批次>/<中文品类>_<时间>.xlsx` 并自动打开。
- 类目打错/没选中时**报错退出**，不会下错品类静默出报告。
- 新增纯逻辑测试全绿；一次真实品类冒烟通过。
