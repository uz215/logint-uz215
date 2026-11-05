# 知识库（Knowledge Base）版本化说明

本目录是解释程序的知识库资产，**纳入 git 版本控制**：

| 文件/目录 | 内容 | git 方式 |
|---|---|---|
| `kb.db` | 知识库 SQLite（文档/块/实体/事实/案例/条款/区域标定，FTS5） | **Git LFS**（约111MB） |
| `topics/` | 专题报告（低阻油层、水淹层、页岩气、煤层气、碳酸盐岩、核磁、成像、凝析气、固井、标准规范、元素测井、测井解释方法） | 普通 git |
| `kb_manifest.json` | 数据库统计/大小/sha256/生成时间（人工可读版本标记） | 普通 git |
| `data/knowledge_summary/` | 公式/参数/方法摘要 | 普通 git |
| `data/exported_experiences/` | 导出的经验条目 | 普通 git |
| `graph/graph.db` | 知识图谱 SQLite（实体/关系/证据） | **Git LFS**（约12MB） |
| `graph/graph.json` / `graph.graphml` | 图谱导出（供查看/交换） | 普通 git |
| `index/` | Whoosh 全文索引（约1.2GB，可由 KB 重建） | **不入库**，用 `python logKnow.py update --index-only` 重建 |
| `data/kb/well_knowledge/` | 井目录知识总结（录井/岩心/XRD/XRF，50m井段+数值范围） | 普通 git |
| `data/local/` | 原始/导入语料（约6GB） | **不入库**，由资料盘重新导入 |

## 重建/更新
```bash
python -m logsys.knowledge.build            # 增量/构建
python -m logsys.knowledge.build --cases-only
```
重建后：更新 `kb_manifest.json`（或运行维护脚本），`git add data/kb/kb.db data/kb/kb_manifest.json`，提交。

## Git LFS
```bash
git lfs install        # 每台机器一次
git lfs ls-files       # 查看 LFS 跟踪文件
```
首次 clone 需安装 git-lfs；否则 `kb.db` 只是指针文件。远端仓库需支持 LFS（GitHub 默认支持，LFS 存储/流量有配额）。

## 原则
- 源码/配置/条款 JSON（`logsys/knowledge/`）与知识库快照（本目录）共同入库；
- 大语料原文件（数据盘 `D:\360\培训材料` 等）不入库，由入库脚本生成 `kb.db`；
- `index/` 与 `data/local/` 为可重建大资产，不入库；克隆后按需重建。
- 重建导致 DB 变化时同步更新 manifest，便于追溯。


## 井目录知识总结
```bash
python -c "from logsys.well_knowledge import save_well_knowledge; save_well_knowledge(r'D:\360\Brasil\Curacao-1', well_name='1-SPS-108')"
```
- 录井/XRD/XRF 不要求与测井深度精确对齐，按约50m井段汇总岩性/矿物/元素范围；
- quicklook 自动生成并并入 logKnow 摘要。


## 知识层级
- 目录：`data/kb/well_knowledge/<国家>/<盆地>/<凹陷>/<构造>/<油田>/<井>/<分类>.md`；
- 分类：basic_data / stratigraphy / lithology / testing / log_interpretation / gas_show；
- 录井岩性→地层/岩性；气测异常→gas_show；钻头/套管/坐标/井别→basic_data。
