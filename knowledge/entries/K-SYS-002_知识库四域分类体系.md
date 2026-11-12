---
id: K-SYS-002
title: 知识库四域二级分类体系——以测井专业为主的油气知识库
type: 元原则
scope: 全局
status: 已验证
version: 2
date: 2026-11-12
source: 用户定调（测井方法按技术大类×厂商小类；解释方法单列第6大类；地质/通用按大类×技术细分；录井并列一级；射孔归测井；通用仅跨专业规范；scope 顶层分 global/国别，国别=区域地质·规范·公式参数·阈值·曲线特征）
supersedes: []
relates: [K-SYS-001]
code_ref: logsys/knowledge/ingest.py:classify_knowledge / scope 由 country 派生（有国别→国别，否则→global）；logsys/knowledge/db.py（doc 表 scope/category/tech_type/tech_minor 自愈 ALTER）；gen_kb_reports.py（scope_overview.html + 分类说明文档 scope 段）
tags: [元原则, 知识管理, 分类体系, 四域, scope]
---

# 知识库四域二级分类体系（K-SYS-002）

## 一、总定位

本知识库是**以测井专业为主的油气知识库**。全部文档入库时自动归入两层结构：

- **顶层 `scope`（适用范围）**：`global`（普适/专业方法类，不绑定国家）/ `国别`（区域专属知识，由 `country` 标注）
- **领域内三级**：`category`（4 大域）× `tech_type`（域内大类）× `tech_minor`（小类）

| 列 | 层级 | 含义 | 示例 |
| --- | --- | --- | --- |
| `scope` | 顶层 | 适用范围 | global（普适）/ 国别（区域专属） |
| `category` | 域 | 一级域（4 个） | 测井方法 / 地质 / 通用知识 / 录井 |
| `tech_type` | 域内大类 | 技术类型 | 电缆测井 / 油气地质 / 标准规范 |
| `tech_minor` | 小类 | 细分 | SLB（厂商）/ 储层地质（技术细分）/ 课题设计（项目） |

分类入口统一为 `classify_knowledge(path, title, category='') -> (domain, tech_major, tech_minor)`（位于 `logsys/knowledge/ingest.py`）；`scope` 由 `country` 派生（有国别→国别，否则→global）。`db.connect()` 对 `doc` 表做幂等 `_ensure_columns` ALTER（含 `scope`），缺失列自动补齐，重跑入库不丢分类。

## 一之一、scope 顶层轴（global / 国别）

- **global（普适知识）**：不绑定特定国家的通用/专业方法类知识，按「4 域 → 大类 → 小类」细分。当前 1295 篇。
- **国别（区域专属知识）**：内容具区域属性、由 `country` 标注，归入「国别」桶；下钻先按国家、再按领域细分。当前 101 篇，跨 17 国（孟加拉国/乍得/中国各 14 领先）。
- **国别知识定义（用户定调）**：区域地质 / 区域规范 / 区域公式及参数 / 区域阈值 / 区域曲线特征——即"换个国家就不一定成立"的本地化知识。

## 二、四域与二级结构

### 1. 测井方法（623 篇）
大类（技术类型）× 小类（厂商/仪器）：
- **电缆测井** 371 · **解释方法** 110（独立第 6 大类）· **生产测井** 98 · **随钻测井** 24 · **射孔** 13（归测井下，与生产测井并列）· **裸眼测井** 5 · **光纤** 2
- 小类按厂商细分：SLB 24 / 贝克休斯 8 / CNLC 6 / 中海油 …（仅部分文档可识别厂商，其余 minor 留空）

### 2. 地质（644 篇）
大类（基础/油气/非常规）× 技术细分小类：
- **油气地质** 368 · **非常规地质** 154 · **基础地质** 97（余为其他类）
- 技术细分小类（tech_minor）：储层地质 354 / 非常规地质 154 / 岩性与矿物 58 / 构造地质 21 / 沉积与地层 18 / 油气地质 14 …（以油气地质为主）

### 3. 通用知识（98 篇）
**定位：油气通用知识，非测井专业本身。** 三大类仅保留跨专业内容：
- **标准规范**：仅**跨专业**规范归此（专业技术规范回退各自技术域）；共 12 篇
- **项目管理**：限课题设计 / 实施 / 方案，不含预算财务·合同招标·制度办法·研讨交流
- **软件工具**：限测井专业软件（Techlog / Geolog / LEAD / Paradigm），不含 Excel·VBA·Python 通用技能
- 跨专业闸门：`classify_general_method` 遇标准规范但命中 `_LOG_ONLY`/`_GEO_ONLY`/`_MUDLOG_ONLY` 触发词时，回退对应技术域，不占通用名额

### 4. 录井（11 篇）
与测井**并列的一级域**（非测井下属）：综合录井 / 气测录井 / 地化录井 / 岩屑录井 / 钻井液录井。

## 三、领域判定优先级（ingest 内）

`标准 > 项目 > 软件 > 录井 > 地质 > 测井 > 行政 > 兜底`。
跨专业闸门下沉进 `classify_general_method` 内部统一生效，避免经项目/行政分支误挂通用。

## 四、当前库容（2026-11-12 实测）

- **scope 顶层**：global 1295 篇 / 国别 101 篇（跨 17 国，孟加拉国/乍得/中国各 14 领先）
- 域内已分类 1376 篇：测井方法 623 / 地质 644 / 通用知识 98 / 录井 11
- 未归类 20 篇（category 空）
- 报告产物（`gen_kb_reports.py`）：`output/scope_overview.html`（global/国别 顶层 + 下钻）、`output/分类说明文档.html`（含 scope 段）、`output/country_domain_stacked.html`（国别×领域堆叠）、`output/country_domain_matrix.html`（交叉表）、`country_waterfall.*`（原瀑布图）

## 五、校正历史

- 2026-11-12 v1：随四域分类体系落地定案（R 轮次 1f585ce→867d634 分类提交 + 52bcdcb/933770b 报告与 API）。
- 2026-11-12 v2：新增 `scope` 顶层轴（global / 国别），国别=区域专属知识（区域地质·规范·公式参数·阈值·曲线特征），由 `country` 派生；`doc` 表加 `scope` 列、`ingest` 两处 INSERT 写入、`gen_kb_reports.py` 新增 `scope_overview.html` 与文档 scope 段。
