# CheapestFlight — 廉价机票抓取工具 · 功能规格说明书 (SPEC)

| 项目 | 内容 |
| --- | --- |
| 名称 | CheapestFlight（最廉价航空票价抓取，网页版 + 安卓 App） |
| 版本 | v0.1 · 需求记录阶段（尚未实现） |
| 定稿日期 | 2026-07-14（初稿，含待讨论项） |

> **协作约定**：每个和用户敲定的功能都必须写入本 SPEC；今后每次敲定的功能修改都要**同步更新 SPEC 并提交 git**。

---

## 1. 项目概述

一个抓取廉价航空票价的个人工具：

- **形态**：Web 页面（PC 浏览器直接打开使用）+ 安卓 App（App 内嵌 WebView 显示同一 Web 页面即可）。
- **数据源**：首期为**飞猪（Fliggy）**；架构上预留多数据源扩展（后续会增加其他来源）。
- **发布**：安卓 APK 发布在本仓库的 GitHub Release。

---

## 2. 架构（沿用 EventNote++ 验证过的模式，待用户确认）

> **架构决策变更（2026-07-15，因飞猪反爬）**：原「Flask 后端纯接口抓取」路线**作废**——飞猪 mtop 需反爬 JS 生成的 `x5sec` 令牌，纯 requests 拿不到（详见 §3.1）。**新架构＝真实浏览器执行 + 拦截接口响应**：安卓 App 用 WebView 加载飞猪官方 H5 机票页，让其反爬 JS 自然运行，通过 JS 桥/`shouldInterceptRequest` **拦截页面自己发出的 `listingsearch` 响应 JSON**，交给本地层做排序/筛选/收藏/入库。Flask 仍保留做本地存储 API（filter/收藏/价格历史）与前端托管，但**不再直接抓飞猪**。安卓优先，PC 端验证待国内直连后补。

- **后端**：Python + Flask 本地服务。职责：提供本地存储 JSON API（filter / 收藏 / 价格历史）、托管前端页面。**不再直接抓飞猪**（改由 WebView 拦截，见上）。
- **前端**：单页 Web（HTML/CSS/JS），从 API 取数渲染卡片列表；排序/筛选在前端完成（数据一次查回，本地排序过滤即时响应）。
- **PC 使用方式**：运行 `python app.py`（或双击启动脚本）→ 自动打开浏览器到 `http://127.0.0.1:<port>`。
- **安卓 App**：Chaquopy 内嵌 Python 运行时，后台线程跑 Flask，界面为全屏 WebView 指向本机服务（详见 §6）。
- **数据源抽象**：每个数据源实现统一接口 `search(date, from, to) -> [Flight]`，飞猪为第一个实现；返回字段统一，前端与来源无关。
- **存储**：SQLite（`data.db`），存「保存的 filter」（F2）、「收藏航班完整信息 + 价格历史」（F3）。两者**持久保存，下次打开 App 依然在**，且均可管理（增删改）。只有**普通搜索结果列表**（未被收藏的航班）是实时查询即弃、不入库。

## 3. 运行环境与依赖（初定，随实现更新）

| 依赖 | 用途 |
| --- | --- |
| Python 3.11 | 运行环境 |
| flask | 本地服务 / API / 前端托管 |
| requests | HTTP 请求（飞猪接口） |
| （待定）playwright 或类似 | 若飞猪接口反爬严格，作为浏览器自动化兜底方案 |

> 飞猪属阿里系，接口带 mtop 签名与风控；具体抓取方式（纯接口 / 浏览器自动化 / 是否需登录 Cookie）待技术验证后敲定并回填本节。

### 3.1 飞猪接口技术验证（2026-07-15 进行中）

**已确认**：

- **mtop H5 签名流程**：`h5api.m.taobao.com/h5/<api>/<ver>/`，首次请求获取 `_m_h5_tk` cookie，签名 = `md5(token&t&appKey&data)`，appKey `12574478`；**匿名即可，无需登录**。
- **核心接口**：`mtop.trip.interflight.listingsearch` v2.3（国际线列表搜索，POST，`needLogin:false`）。**轮询协议**：响应含 `needContinue / nextWaitTime / uniqKey / pollCount`，需带 `uniqKey` 递增 `pollCount` 反复请求直至 `needContinue=false`，结果在 `data.items`。
- **请求参数**（从页面 JS `rx-iflight-eco/1.19.47` 提取）：`tripType`（单程/往返）、`leaveDate/backDate`、`depCityCode/arrCityCode`（城市三字码）、`depCityName/arrCityName`、`adultPassengerNum` 等乘客数、`cabinClassFilter`（`Y`=经济舱/`S/C/F/YS/FC`）、`showTaxPrice`、`sortBy`、`filters`；往返模式改用 `searchSegments` 段列表。
- **辅助接口**：`mtop.trip.flight.calendar.cheapest` v2.0（低价日历）、`mtop.trip.tfsug.card.inter.city.suggest`（城市联想）——两者风控宽松，海外 IP 也能过。
- **风控结论**：`listingsearch` 风控严格，海外数据中心 IP（本机 Vultr TUN 全局代理出口）直接被 `RGV587_ERROR::SM` 滑块惩罚，连真实 Chrome 打开列表页都被拦 → **必须国内 IP 直连阿里系域名**（`*.taobao.com / *.fliggy.com / *.alicdn.com / *.mmstat.com` 走 DIRECT）。用户已确认在代理客户端加直连规则。

**⭐ 根本结论修正（2026-07-15 二次验证）——需要登录，而非风控/代理**：

- 用户反馈「手动 Chrome 能看到飞猪机票」+ 网络排查确认：访问国内目标时出口是**真实国内住宅 IP**（183.34.170.90 广东电信直连），只有访问国外 IP（如 api.ipify）才走 Vultr。**网络没问题**，路由器只代理国外地址。
- 真正原因＝**飞猪国际机票搜索结果需要淘宝登录**。实测用真实 Chrome（CDP 接管、全新配置）驱动 PC 国际机票页 `www.fliggy.com/ijipiao/` 搜索「上海→东京」，结果页跳转 `market.m.taobao.com/.../listing` 后**重定向到 `login.taobao.com` 二维码登录页**。此前的 `RGV587` 也是**未登录态**下的表现，而非机房 IP。
- 首页「特价航线」列表（往返报价）**无需登录可见**，但**点进具体搜索结果必须登录**。用户手动 Chrome 能看＝其浏览器**已登录淘宝**。
- **PC 站可用**：`www.fliggy.com/jipiao/`（国内）与 `www.fliggy.com/ijipiao/`（国际/港澳台，含单程/往返/多程）页面完整加载、表单可驱动、未被风控——只差登录态。

**架构含义**：与 EventNote 完全同构——需**用户自己的登录态**。安卓 App 用 **WebView 扫码/密码登录淘宝**取得会话，再加载机票列表页（此时不再跳登录）→ 拦截 `listingsearch` 响应。登录 cookie 存本地私有目录（同 EventNote `cookie.txt` 模式）。这也解释了为何 §3.1 早前纯 requests 匿名调用必被 `RGV587`。

### 3.3 登录后深入验证（2026-07-15，用户已扫码登录 dreamer199506）

用户扫码登录后，用 CDP 接管的真实 Chrome 继续验证，得到三条关键结论：

1. **登录确实解除风控**：直接签名调 `listingsearch` 从 `RGV587`（滑块）变为 `FAIL_SYS_ILLEGAL_ACCESS::非法访问`——即登录态有效，但**该接口不允许被直接调用**。
2. **真实数据走网关代理**：列表页并不直接请求 `listingsearch`，而是通过 **`mtop.trip.serverless.api.gateway`**（serverless 网关）转发（实测返回 `SUCCESS`）。这解释了为何直连 `listingsearch` 报"非法访问"——正确入口是网关，内层再带 listingsearch 的业务参数。**抓取实现应拦截/复用网关调用，而非直调 listingsearch。**
3. **移动 H5 列表页在自动化环境下拒绝渲染**：`market.m.taobao.com/app/trip/rx-iflight-eco/pages/listing` 在 Playwright/CDP 自动化下**稳定停在飞猪「抱歉出错了」错误页**（伴随 `outfliggys.m.taobao.com/....fmanifest.json` 的 `ERR_FAILED`），即使登录、伪造 manifest、移动端 UA 模拟均无效——页面有**自动化检测**。而用户的**真实 Chrome 能正常显示航班**。

**由此确定的落地路径**：**放弃在开发机上用自动化抓取**（页面反自动化 + 网关鉴权，成本高且脆）。**改由安卓真机的真实 WebView 抓取**——真实 WebView ≠ 自动化浏览器，行为等同用户的真实 Chrome，能正常渲染并触发网关/`listingsearch` 调用，App 通过 `shouldInterceptRequest`/JS 注入 `XMLHttpRequest`/`fetch` 钩子**拦截响应 JSON**即可。即：字段 schema 的最终确定，推迟到**首版「WebView + 拦截」骨架 App 装到用户手机上跑一次搜索**时完成（§3.2 的解锁方式 a）。

> 开发机上的临时登录 Chrome（throwaway 配置）用完即关，不长期保留用户账号会话。

---

**（历史记录）风控深入结论（2026-07-15 追加，后被上方「需登录」结论修正）**：

- listingsearch 的拦截**不只是 IP**，还叠加**反爬指纹**：返回 `RGV587_ERROR::SM` + `.../punish?x5secdata=...` 滑块惩罚 URL。
- 实测在**确认过的国内 IPv6 出口**（240e 广州电信 / 2401:b180 阿里 IPv6）下，纯 requests 匿名会话仍被 RGV587 挑战；用**真实 Chrome（Playwright headful）**打开官方 H5 列表页也停在飞猪「抱歉出错了」错误页（其内部 listingsearch 同样被 punish）。
- 根因：阿里 mtop 需要页面加载时其**反爬 JS SDK 运行后生成的 `x5sec` 令牌**（配合 `cna/umid` 等）。纯 Python `requests` 不执行该 JS，拿不到令牌 → 必被挑战；全新无 Cookie 的浏览器会话同样会被挑战（低风险场景浏览器 JS 会自动过，但需真实环境）。
- 本机网络限制加剧问题：IPv4 全量经路由器 TUN 出口到 Vultr（美国机房 IP，被阿里判高风险）；代理在**路由器（网关 192.168.50.1）**上，PC 端无代理进程、改不动其分流规则。`market.m.taobao.com`（SPA 页所在域）**无 IPv6**，无法用 IPv6 绕过。

**技术选型的现实推论**：

- 「纯接口 requests」路线**不可行**（拿不到 x5sec，稳定被风控），除非引入完整反爬令牌生成（成本高、易碎）。
- 可行路线＝**真实浏览器执行环境**：安卓端用 **WebView 加载官方飞猪 H5 机票页**，让阿里反爬 JS 自然生成令牌，再从中**拦截 listingsearch 的响应 JSON**（页面自己发的请求，我们只读结果）→ 复用 §17 数据结构。这与本机是否被风控无关：**用户手机在真实国内移动网络下访问，天然低风险、可自动过反爬**。
- PC 端验证/使用需要 taobao/fliggy 域名走**国内住宅 IP 直连**（非 Vultr）；当前受路由器分流所限暂时无法从本机跑通端到端，**待用户决定网络方案**（见下）。

**待用户决定（阻塞项）**：
1. 路由器上给 `*.taobao.com / *.fliggy.com / *.alicdn.com / *.mmstat.com` 加**直连（走国内线路）** —— 需路由器后台访问权限，可由用户操作或提供机型/固件由 Claude 指导。
2. 或先以**安卓 App（真机真实国内网络）为首要目标**：架构改为「WebView 加载官方 H5 页 + 拦截接口响应」，PC 端验证延后到有国内直连后再补。

**已决（2026-07-15）**：采用方案 2（安卓优先 + WebView 拦截）。

### 3.2 待办：捕获一次真实 listingsearch 响应以定字段

飞猪列表卡片由**服务端动态 UI 模板（DinamicX）**下发，字段结构**无法从页面 JS 反推**，`items` 内部 schema 必须靠**一次真实响应**确定。当前本机网络被风控，拿不到。**解锁任一即可**：
- (a) 用户在**安卓真机**装上首版「WebView + 拦截」骨架 App，跑一次搜索，把拦截到的 `listingsearch` 响应 JSON 回传（真机真实国内网络可自动过反爬）；
- (b) 路由器给阿里系域名加国内直连后，Claude 从 PC 用真实浏览器捕获。

拿到后回填「§7 数据字段」与卡片渲染映射，再开发排序/筛选/收藏。

---

## 4. 功能规格

### F1 · 航班搜索（飞猪）——首个功能

**已敲定（2026-07-14）**：

- **行程类型**：单程 + 往返都支持。
- **航线范围**：以**国际线**为主（中转选项多，「直飞/中转」筛选价值最大）；国内线能查则一并兼容。
- **乘客/舱位**：固定 **1 成人 · 经济舱**，界面不提供选择（以后有需要再加）。
- **抓取路线**：先验证飞猪 mtop H5 接口（无登录或带 Cookie，轻量、可进安卓 APK）；若被风控拦死，再用 Playwright 浏览器自动化兜底（PC 可用，安卓端受限）。验证结果回填 §3。

**输入**：出发日期（往返再加返程日期）、出发地、到达地（城市/机场）。

**输出**：航班结果卡片列表。每张卡片必须正确显示：

| 字段 | 说明 |
| --- | --- |
| 起飞机场 / 降落机场 | 含城市与机场名（有多机场城市时必须区分具体机场） |
| 起飞时间 / 到达时间 | 到达时间跨天时需标注（如 `+1天`） |
| 总耗时 | 从起飞到最终到达的总时长（含中转等待） |
| 价格 | 当前查询到的票价 |
| 直飞 / 中转 | 中转需标明中转地与次数 |
| 航司 / 航班号 | 承运航司与航班号（中转为多段） |

**排序**（四种，均支持升/降序）：

1. 出发时间
2. 到达时间
3. 价格
4. 飞行时间（总耗时）

**筛选**：

- 直飞 / 中转（全部 / 仅直飞 / 仅中转）

**往返展示（Q6 敲定，2026-07-15）**：照搬飞猪的两步选择流程——先出**去程列表**（可排序/筛选），选中一趟去程后出**对应的返程列表**（组合报价），最终价格为去+返组合价。

**价格口径（边界，2026-07-15）**：一律以飞猪搜索结果**估出的票价**为准。购买页的保险、票价最低中间商等附加选项**一概不考虑**（用户自行决定），本工具不做该层的价格修正。

### F2 · 保存的 Filter（搜索方案）——已敲定（2026-07-15）

- 用户在搜索页做出的**全部选择**（出发/到达地、日期、单程/往返、排序方式、直飞/中转筛选）可一键**保存为一个 filter**。
- 已保存的 filter 列表展示在页面上，**点击即按该 filter 直接发起搜索**（所有条件自动带入）。
- filter 可删除、可修改（含日期——日期会过期，重搜前可快速改日期再查）。
- 存储于 SQLite，PC/安卓各自本地持久。

### F3 · 收藏航班 + 价格变化追踪——已敲定（2026-07-15）

- 搜索结果卡片上可**收藏**某个航班（往返模式下收藏的是「去程+返程组合」）。
- 收藏标识：日期 + 航线 + 航班号（多段/组合为各段航班号拼合），同一标识视为同一收藏。
- **持久化（2026-07-15 补充敲定）**：收藏时将航班**完整信息**（起降机场/时间、总耗时、航司航班号、中转信息、当时价格）整体入库；**下次打开 App 收藏视图直接显示库中数据**（上次刷新时的信息），无需联网重搜。
- **管理**：收藏可查看、删除；保存的 filter 同样可管理（见 F2）。
- 提供**「收藏」视图** + **刷新**动作：刷新时逐个按收藏对应的条件重新搜索，定位到该航班，更新库中航班信息并追加价格快照（时间 + 价格）。
- 卡片显示**价格变化**：当前价、上次价、涨/跌幅标识；查不到该航班时（售罄/取消/变更）标注「本次未找到」，收藏保留不自动删。
- 价格历史全部保留，后续可做价格走势展示（暂不实现，先存数据）。

### 待讨论（本轮未敲定，敲定后回填）

| 编号 | 问题 | 状态 |
| --- | --- | --- |
| Q1 | 单程 or 往返 | ✅ 已定：单程 + 往返都要 |
| Q2 | 国内 or 国际 | ✅ 已定：主要国际线 |
| Q3 | 飞猪抓取技术路线 | ✅ 已定：先试 mtop 接口，不行再 Playwright 兜底 |
| Q4 | 乘客数与舱位 | ✅ 已定：固定 1 成人 · 经济舱 |
| Q5 | 结果是否需要缓存/历史比价 | ✅ 已定（2026-07-15）：filter 与收藏航班（含完整航班信息、价格历史）**持久保存、重开 App 仍在、可管理**；仅未收藏的普通搜索结果实时即弃 |
| Q6 | 往返结果的展示方式 | ✅ 已定（2026-07-15）：照搬飞猪两步选择流程（去程列表 → 选中后出返程列表与组合价） |
| Q7 | 价格口径 | ✅ 已定（2026-07-15）：以飞猪估出的票价为准，保险/中间商等附加项不考虑 |

---

## 5. 目录结构（规划）

```
CheapestFlight/
├─ app.py            # 后端入口：启动服务 + 自动开浏览器
├─ sources/          # 数据源实现（fliggy.py 为首个，统一接口）
├─ store.py          # SQLite 读写：filter / 收藏 / 价格快照
├─ web/              # 前端单页（index.html / app.js / style.css）
├─ data.db           # SQLite（filter / 收藏 / 价格历史）
├─ android/          # 安卓 Gradle 工程（Chaquopy 打包）
└─ Spec.md           # 本规格说明
```

---

## 6. 安卓打包与发布（沿用 EventNote++ §22 已验证流程）

**方案**：Chaquopy——APK 内嵌 Python 运行时，`MainActivity` 后台线程启动 Flask（`start_server`）→ 轮询就绪 → 全屏 WebView 加载 `http://127.0.0.1:<port>`。Python 源码与 `web/` 由构建任务 `syncPySources` 自动从仓库根同步进 APK（单一代码源，改完直接重新 assemble）。

**工程参数**（照搬已验证组合）：AGP 7.4.2 + Kotlin 1.8.22 + Chaquopy 16.1，Python 3.11，仅 arm64，minSdk 26 / targetSdk 33。

**已知要点**（EventNote 踩坑继承）：

- WebView 必须挂默认 `WebChromeClient`，否则 JS `alert/confirm` 被静默吞掉。
- `shouldOverrideUrlLoading` 拦截非 `127.0.0.1` 链接改由系统浏览器打开。
- `settings.gradle` 依赖仓库前置阿里云镜像（`dl.google.com` DNS 污染），勿删。
- `buildToolsVersion` 显式钉住本地已装版本，避免联网下载。
- Python 依赖需为纯 Python / 标准库（Chaquopy 对 C 扩展受限）；若最终采用 Playwright 等重依赖，安卓端需另行评估（可能安卓端只走接口路线）。

**构建环境**（本机既有安装，路径不入 git）：

| 组件 | 位置 |
|---|---|
| JDK 11 | `E:\Software\Android\Android Studio\jre`（设 `JAVA_HOME`） |
| Android SDK | `E:\Software\Android\Sdk`（写在 `android/local.properties`） |
| Gradle 7.6.4 | 独立发行版解压即用，或仓库 `gradlew` 包装器 |

构建命令：

```bash
export JAVA_HOME="E:\Software\Android\Android Studio\jre"
cd android
<gradle目录>/bin/gradle.bat :app:assembleDebug --no-daemon
# 产物：android/app/build/outputs/apk/debug/app-debug.apk
```

**发布（GitHub Release，APK 不进 git 历史）**：

- tag：`v<版本>-android-alphaN`（target=main），`prerelease: true`；资产名：`CheapestFlight-android-alphaN-arm64.apk`。
- 凭据复用 git 凭据管理器，REST API 两步（建 Release → 传 APK）；发布 JSON 一律写临时文件后 `--data-binary @file` 传给 curl（内联中文 JSON 在 Git Bash 传参会出错）。
- 手机端直接打开 Release 页下载安装。
