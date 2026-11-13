---
id: K-SYS-004
title: logknow 入档流程与外文归一准则——bootstrap_knowledge.py 为正本，全文与图谱双写，外文识别成中文入库不重复
type: 体系规则
scope: 全局
status: 已验证
version: 1
date: 2026-11-13
source: 用户定调（"用logknow来入档，也就是其目录下的bootstrap_knowledge.py"；"入库后的关键词可以是中文，但是扫描时的外文需要识别成中文入库，也就是不能重复"；本轮确认"文档全文+图谱双写"、"让它跑完再切 logknow"）
supersedes: []
relates: [K-SYS-001, K-SYS-002, K-SYS-003]
code_ref: logknow/bootstrap_knowledge.py（GeoKnowledgeLoader / scan_docs_in_path / scanpath 子命令 / _cn 归一 / 合规粗筛）；logknow/bootstrap.py（再导出修复）；logknow/region_normalize.yaml（12 国英文别名 + 泰国条目 + 67 条术语）；logknow/region_normalizer.py（_key / normalize_term / normalize_phrase）；gen_kb_reports.py（分类说明「入档流程」章）
tags: [元原则, 知识管理, 入档流程, logknow, 知识图谱, 外文归一, 去重, 收录合规]
---

# logknow 入档流程与外文归一准则（K-SYS-004）

## 一、入档正本与双写模型

**入档正本 = `logknow/bootstrap_knowledge.py`**，不是 `logsys/knowledge/ingest.py`。
两者写的是**同一个 `data/kb/kb.db` 的不同表**，互补而非互斥（2026-11-13 用户定案「文档全文 + 图谱双写」）：

| 落点 | 表 | 内容 | 驱动 |
| --- | --- | --- | --- |
| 文档全文 | `doc` / `chunk` / `doc_fts` | 资料全文与切片，供检索 | `logsys/knowledge/ingest.py`、`ingest_rich.py` |
| 区域知识图谱 | `entity` / `fact` | 国家→盆地→凹陷→区块→油气田→构造→井→地层→解释方法 | **`logknow/bootstrap_knowledge.py`（本正本）** |
| 原件归档 | `logknow/static_geo/docs/` | 原始文件副本 | `scan_docs_in_path`，指纹 `doc_fingerprints.txt` 判重 |

`static_geo/{洲}/{国}.json`（207 个）是区域知识的**结构化正本**，由 `bootstrap` 子命令幂等灌入图谱。

## 二、入档链路（`bootstrap_knowledge.py`）

| 子命令 | 行为 |
| --- | --- |
| `check` / `bootstrap` | 扫描 `static_geo` 有效洲目录下的 json，校验 / 幂等灌入 `entity`/`fact` |
| `scan` | 自动识别**可移动盘**并扫描（原实现仅此一条，G: 为固定盘 type=3 扫不到） |
| **`scanpath <root>`（2026-11-13 新增）** | 直接对指定路径（如 `G:/入库整理后`）扫描入档，突破固定盘限制 |

`scan_docs_in_path(root)` 的关键约定：

- **归档优先**：只要文件有效即归档原件到 `static_geo/docs/` 并记指纹；结构化抽取**尽力而为**。
  原实现在「抽取无匹配」时直接 `continue`，连原件都不归档——对英文资料等于零入档，本版已校正。
- **判重**：文件内容 `sha256`（`doc_fingerprints.txt`），增量可断点续跑，重跑零新增。
- **超大保护**：单文件 > 200MB 跳过归档并记清单。
- **抽取**：`simple_geo_extract(text, path_hint)` 中英双语关键词；国别 / 盆地 / 井优先由**路径层级**派生
  （`G:/入库整理后/<Country>/<Basin>/...` 本身即权威区域信息，比从英文正文猜国家可靠）。

## 三、外文 → 中文归一（核心：不产生中英重复节点）

**事实基线**：现存 `entity` 表 182 个 `country` 节点**全部为中文名**，`static_geo/*.json` 的 `country` 亦为中文
→ 中文是国别正典，外文写法必须归一后再入库。

归一三层（`logknow/region_normalize.yaml` + `region_normalizer.py` + `bootstrap_knowledge._cn()`）：

1. **国别正典**：补齐 G 盘 12 国英文别名（Algeria/Chad/Iran/Iraq/South Sudan/Sudan/Turkmenistan/
   Bangladesh/Indonesia/Niger/Kazakhstan/Thailand），并**新增缺失的「泰国」中文条目**。
   `RegionNormalizer._key()` 忽略大小写与空格/下划线/连字符/点/括号差异，
   `South Sudan` / `south_sudan` / `SOUTH-SUDAN` 均收敛到「南苏丹」。
2. **术语表**：67 条英→中（45 条测井/地质通用术语 + 22 条地质年代/储层），
   `Archie`→`阿尔奇公式`、`sandstone`→`砂岩`、`shale volume`→`泥质含量`。
3. **短语级替换**：`normalize_phrase()` 按词边界、长词优先，把整串外文字段译为中文，
   例：`Cambro-Ordovician sandstone reservoir` → `寒武-奥陶系砂岩储层`。

**双保险**：`simple_geo_extract` 抽取后归一一次；`GeoKnowledgeLoader.ingest_single_record` 入库前对
`country` 再归一一次（覆盖 `bootstrap` 与 `scanpath` 全部来源）。`strata_meta.foreign_alias` 保留原文可追溯。

**不重复的机制**：`add_entity` 的 id = `kind:canonical`，`canonical` 由归一后的中文名派生；
中英文写法归一后 canonical 一致 → `INSERT OR REPLACE` **合并**既有节点而非新建。

**边界**：专有地名 / 地层专名（如 `Hassi Messaoud`、`Doba`）未收录术语表时**保留原文**，
靠 `normalize_name` 规范（小写、去空格/连字符）保证同一写法不重复；若某专名确有中英两种写法需归并，
在 `term_mapping` 增补对照即可，不改代码。

## 四、收录合规（承接 K-SYS-003 v2）

- 显式敏感 / 纯行政路径（人事任免、考勤、薪资、身份证、护照、银行账号、发票流水、涉密等）→ **跳过归档**并记清单。
- **不误杀**：测井类服务合同、研究/采集服务项目要求、特定国家财税政策（地区特别税政策 + 项目要求）
  均属可入档资料，`_SENSITIVE_PATH_KW` 不含「合同 / 税 / 服务」等字样（按内容实质判定，不按文种一刀切）。
- 正文中的身份证号 / 手机号仅**只读抽查**留 PII 待复核清单，**不自动删改、不阻断归档**。

## 五、验证结论（2026-11-13 临时环境，未触碰主库与 G 盘）

构造 5 个样例（英文资料 / 同国中文资料 / 另一国英文 / 敏感行政文件 / 无结构关键词短文）：

- 扫描 5 / **归档 4** / 敏感跳过 1 / 知识记录 3 / 含结构化知识 3；
- `country` = `乍得`、`阿尔及利亚`（**无拉丁字母节点**），中英文同国合并为 **1 个**；
- `formation` = `下白垩统砂岩`、`寒武-奥陶系砂岩储层`（**全中文**），中英文写法合并为 **1 个**；
- `interp_method` = `阿尔奇公式`（`Archie` 与中文写法合并为 **1 个**）；
- 加入短语归一后 entity 总数由 9 降至 **7**，即消除 2 个中英重复节点；
- 重跑：`skip_known=4`、`archived=0`、零新增 → 指纹判重幂等通过。

## 六、落点与待执行

- 代码：`bootstrap_knowledge.py`、`bootstrap.py`（修复引用已不存在的 `GraphStore/BENCHMARK_DATA`
  导致的 `ImportError`，改按真实 API 再导出）、`region_normalize.yaml`、`region_normalizer.py`。
- 文档：`gen_kb_reports.py` 分类说明新增「logknow 入档流程与外文归一」章。
- **待执行**（避免并发写同一个 kb.db）：后台 `doc` 全文入库任务完成后，依次跑
  `python logknow/bootstrap_knowledge.py bootstrap` 与
  `python logknow/bootstrap_knowledge.py scanpath "G:/入库整理后"`，
  随后重算报告、全库合规复核、刷新四同步数字。
- 遗留：`logknow/ingest_static_geo.py` 仍引用 `bootstrap_knowledge.GraphStore`（旧 JSON 图谱
  `graph_store.json` 体系），与本正本的 `entity`/`fact` 落点不同，本轮**刻意未改动**，如需恢复该链路另议。

## 七、校正历史

- 2026-11-13 v1：用户指定 logknow/bootstrap_knowledge.py 为入档正本，确立全文+图谱双写、
  外文归一中文不重复；修复断裂入口、扩充归一表、新增 scanpath 与归档优先，并完成临时环境验证。
