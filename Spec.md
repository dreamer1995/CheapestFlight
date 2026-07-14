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

- **后端**：Python + Flask 本地服务。职责：向数据源发起航班查询、整理为统一数据结构、提供 JSON API、托管前端页面。
- **前端**：单页 Web（HTML/CSS/JS），从 API 取数渲染卡片列表；排序/筛选在前端完成（数据一次查回，本地排序过滤即时响应）。
- **PC 使用方式**：运行 `python app.py`（或双击启动脚本）→ 自动打开浏览器到 `http://127.0.0.1:<port>`。
- **安卓 App**：Chaquopy 内嵌 Python 运行时，后台线程跑 Flask，界面为全屏 WebView 指向本机服务（详见 §6）。
- **数据源抽象**：每个数据源实现统一接口 `search(date, from, to) -> [Flight]`，飞猪为第一个实现；返回字段统一，前端与来源无关。

## 3. 运行环境与依赖（初定，随实现更新）

| 依赖 | 用途 |
| --- | --- |
| Python 3.11 | 运行环境 |
| flask | 本地服务 / API / 前端托管 |
| requests | HTTP 请求（飞猪接口） |
| （待定）playwright 或类似 | 若飞猪接口反爬严格，作为浏览器自动化兜底方案 |

> 飞猪属阿里系，接口带 mtop 签名与风控；具体抓取方式（纯接口 / 浏览器自动化 / 是否需登录 Cookie）待技术验证后敲定并回填本节。

---

## 4. 功能规格

### F1 · 航班搜索（飞猪）——首个功能（需求已记录，细节待讨论）

**输入**：出发日期（日期选择器）、出发地、到达地（城市/机场）。

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

### 待讨论（本轮未敲定，敲定后回填）

| 编号 | 问题 |
| --- | --- |
| Q1 | 单程 or 往返？首期是否只做单程 |
| Q2 | 国内航线 or 含国际（港澳台/国际线中转多、页面结构不同） |
| Q3 | 飞猪抓取技术路线：无登录接口 / 用户 Cookie（EventNote 模式）/ 浏览器自动化 |
| Q4 | 乘客数与舱位是否固定为 1 成人 · 经济舱 |
| Q5 | 结果是否需要缓存/历史比价（还是每次实时查询即弃） |

---

## 5. 目录结构（规划）

```
CheapestFlight/
├─ app.py            # 后端入口：启动服务 + 自动开浏览器
├─ sources/          # 数据源实现（fliggy.py 为首个，统一接口）
├─ web/              # 前端单页（index.html / app.js / style.css）
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
