# -*- coding: utf-8 -*-
"""
测井解释知识图谱 (logGraph)
================================================
将 logKnow 知识库从「全文索引 + 向量检索」升级为「可推理的知识图谱」：

  数据底座(logKnow) -> 骨架抽取(元数据/目录/试油表) -> 图谱存储(SQLite+NetworkX)
                                                -> 应用(GraphRAG/相似试油/子图可视化)
                                                -> 缺口自检 -> 定向补全(反馈闭环)

实体类型(kind):
  Document      文档(证据节点, 一切关系可回溯来源)
  Well          井
  Block         区块/气田/盆地
  Country       国家
  TestInterval  试油层位
  Parameter     Archie 解释参数
  Conclusion    试油结论(油层/气层/水层/干层/...)

关系类型(rel):
  LOCATED_IN    位于   (well->block, block->country, well->country)
  EVIDENCE      证据   (doc->well/block/test, 知识来源回溯)
  HAS_TEST      有试油 (well->test)
  TEST_IN       试油在 (test->block)
  USES_PARAM    采用参数 (well->param, block->param)

用法:
  python logGraph.py build         # 全量重建图谱骨架
  python logGraph.py stats         # 实体/关系统计
  python logGraph.py subgraph 井名 # 井邻域子图
  python logGraph.py gap           # 图谱缺口报告(孤立/缺关系/无证据)
  python logGraph.py export        # 导出 graph.json / graph.graphml
"""
import os
import re
import sys
import json
import time
import sqlite3
import hashlib
import argparse
from collections import defaultdict, Counter

import networkx as nx

# logKnow 提供 WellLocationExtractor(井/区块/国家硬约束映射) 与 frontmatter shim
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import logKnow
    from logKnow import WellLocationExtractor
except Exception as _e:  # 兜底: 抽取器不可用时退化为内置轻量映射
    WellLocationExtractor = None
    _WLE_ERR = str(_e)
else:
    _WLE_ERR = None

try:
    import frontmatter as _fm
except Exception:
    _fm = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DIR = os.path.join(BASE_DIR, 'data', 'local')
GRAPH_DIR = os.path.join(BASE_DIR, 'graph')
DB_PATH = os.path.join(GRAPH_DIR, 'graph.db')
EXPORT_JSON = os.path.join(GRAPH_DIR, 'graph.json')
EXPORT_GRAPHML = os.path.join(GRAPH_DIR, 'graph.graphml')

# 参与图谱构建的本地知识子目录(排除 *bak* 备份)
GRAPH_SUBDIRS = ['regional', 'standards', 'well_test', 'well_test_proposal']

# 试油结论关键词(测井/试油口径, 含英文映射)
CONCLUSION_KEYS = [
    '油层', '气层', '水层', '干层', '油水同层', '气水同层', '油干同层',
    '含油', '含气', '含水', '差油层', '低产油层', '凝析气层', '凝析油',
    '致密气层', '水淹层', '可疑层',
]
CONCLUSION_EN = {
    'oil': '油层', 'gas': '气层', 'water': '水层', 'dry': '干层',
    'oil&gas': '油气层', 'oil gas': '油气层', 'gas oil': '油气层',
    'oo': '油水同层', 'ow': '油水同层', 'water/oil': '油水同层',
    'go': '气油同层', 'gw': '气水同层', 'ogw': '油气水同层',
    'oilwater': '油水同层', 'oil,water': '油水同层',
    'condensate': '凝析气层', 'poor oil': '差油层', 'pay': '油层',
}


def _extract_conclusion(fm, text_head=''):
    """从 frontmatter / 文本提取试油结论(中英文, 取首个命中)"""
    candidates = []
    for field in ('result', 'well_test_info', 'conclusion', 'test_result', '结论'):
        v = fm.get(field)
        if isinstance(v, str) and v.strip():
            candidates.append(v)
        elif v is not None and not isinstance(v, str):
            candidates.append(str(v))
    for cand in candidates:
        # 英文映射优先(如 conclusion: oil)
        cl = cand.strip().lower()
        if cl in CONCLUSION_EN:
            return CONCLUSION_EN[cl]
        # "oil(油层)" 中英对照
        for k in CONCLUSION_KEYS:
            if k in cand:
                return k
    # 正文: 先解析 Recovery/recovered 回收物描述(显式证据, 高于裸词)
    t = text_head.lower()
    rm = re.search(r'\brecover\w*\s*[^\n.]{0,120}', t)
    if rm:
        seg = rm.group(0)
        has_oil = re.search(r'\boil\b', seg) or 'oil-cut' in seg or 'oil cut' in seg
        has_gas = re.search(r'\bgas\b', seg)
        has_water = (re.search(r'\bwater\b', seg) or 'salty' in seg
                     or 'foetid' in seg or 'brine' in seg or 'formation water' in seg)
        if re.search(r'\bno recovery\b|\bno dst\b', seg):
            return None
        if has_oil and has_water:
            return '油水同层'
        if has_oil and has_gas:
            return '油气层'
        if has_oil:
            return '油层'
        if has_gas:
            return '气层'
        if has_water:
            return '水层'
    for k in CONCLUSION_KEYS:
        if k in text_head:
            return k
    # 文本英文(裸词, 兜底)
    for en, zh in CONCLUSION_EN.items():
        if re.search(r'\b' + re.escape(en) + r'\b', t):
            return zh
    return None

# Archie 参数键
ARCHIE_KEYS = ['a', 'b', 'm', 'n', 'Rw']


# 已知国家/区域名单(区块名判定排除项)
_KNOWN_COUNTRIES = {
    '中国', '美国', '俄罗斯', '委内瑞拉', '尼日尔', '乍得', '巴西', '土库曼',
    '乌兹别克斯坦', '乌兹别克', '哈萨克斯坦', '秘鲁', '苏丹', '缅甸', '印尼',
    '苏里南', '孟加拉', '阿塞拜疆', '叙利亚', '伊朗', '伊拉克', '阿曼', '埃及',
    '阿尔及利亚', '安哥拉', '英国', '法国', '挪威', '沙特', '卡塔尔', '阿联酋',
    '加拿大', '澳大利亚', '尼日利亚', '加蓬', '刚果', '赤道几内亚', '毛里塔尼亚',
    '利比亚', '南苏丹', '乌干达', '肯尼亚', '坦桑尼亚', '莫桑比克', '马来西亚',
    '泰国', '越南', '蒙古', '巴基斯坦', '印度', '文莱', '阿根廷', '墨西哥',
    '哥伦比亚', '厄瓜多尔', '玻利维亚', '特立尼达', '圭亚那', '中东', '拉美', '南美',
}

# 图谱侧国家补充映射(仅补国家不猜区块; 优先级低于 WellLocationExtractor 硬约束)
GRAPH_PREFIX_COUNTRY = [
    # 巴西盐下井群(ANP 注册号 / RJS=里约州 / BUZ=Búzios 等盐下油田)
    ('RJS', '巴西'), ('BUZ', '巴西'), ('ANP', '巴西'), ('JUP', '巴西'),
    ('ALAT', '乌兹别克斯坦'), ('TRAKES', '尼日尔'), ('IZZ', '委内瑞拉'),
    ('SPS', '巴西'), ('XIMENIA', '乍得'), ('JOR', '土库曼'),
    ('BELTAU', '哈萨克斯坦'), ('ADM', '乍得'),
]
GRAPH_REGION_COUNTRY = {
    '拉美': '巴西', 'LATAM': '巴西', '南美': '巴西', '巴西': '巴西',
    '中亚': '哈萨克斯坦', '哈萨克斯坦': '哈萨克斯坦',
}


def _norm_well(name):
    """井名规范化: 去空白, 统一连字符, 过滤占位/噪声"""
    if not name:
        return None
    s = str(name).strip().strip('"\'')
    s = re.sub(r'\s+', '', s)
    s = s.replace('_', '-')
    if not s:
        return None
    # 过滤噪声: 路径分隔/占位/纯数字/无字母或数字
    if '/' in s or '\\' in s:
        return None
    if s.startswith('-') or s.endswith('-'):
        return None
    if re.fullmatch(r'\d+', s) or len(s) < 2:
        return None
    has_letter = re.search(r'[A-Za-z\u4e00-\u9fff]', s)
    has_digit = re.search(r'\d', s)
    if not (has_letter and has_digit):
        return None
    return s.upper()


def _read_frontmatter(path, head_bytes=65536):
    """只读文件头部, 提取 frontmatter dict(避免读大文件全文)"""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            head = f.read(head_bytes)
        head = head.lstrip('\ufeff')
        if not head.startswith('---'):
            return {}
        end = head.find('\n---', 3)
        if end < 0:
            return {}
        yaml_block = head[3:end]
        try:
            import yaml
            data = yaml.safe_load(yaml_block)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    except Exception:
        pass
    return {}


def _extract_archie(text, head_chars=20000):
    """从文本中抽取 Archie 参数组 a/b/m/n/Rw -> dict 或 None
    支持两种写法: 行内键值(a=1,b=1,m=1.7) 与 Markdown 表格(| m | 1.7 |)"""
    if not text:
        return None
    t = text[:head_chars]
    kv = {}
    # 模式1: 行内键值
    for key in ARCHIE_KEYS:
        for m in re.finditer(r'\b' + re.escape(key) + r'\s*[=:：]\s*(\d+\.?\d*)', t, re.I):
            k = 'rw' if key.lower() == 'rw' else key.lower()
            if k not in kv:
                kv[k] = float(m.group(1))
            break
    # 模式2: Markdown 表格行 (| m | 1.7 | ...)
    for m in re.finditer(r'^\s*\|\s*(a|b|m|n|rw)\s*\|\s*\*{0,2}\s*(\d+\.?\d*)',
                         t, re.I | re.M):
        k = m.group(1).lower()
        if k not in kv:
            kv[k] = float(m.group(2))
    if 'm' in kv and 'n' in kv:
        return kv
    return None


class GraphStore:
    """SQLite 图存储 + NetworkX 内存图"""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.g = nx.MultiDiGraph()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # ---------- 存储层 ----------
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS nodes(
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, props TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS edges(
            src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL, props TEXT NOT NULL,
            PRIMARY KEY(src, rel, dst))""")
        return conn

    def save(self):
        conn = self._conn()
        try:
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM edges")
            conn.executemany(
                "INSERT INTO nodes(id, kind, props) VALUES(?,?,?)",
                [(n, d.get('kind', '?'), json.dumps(d, ensure_ascii=False, default=str))
                 for n, d in self.g.nodes(data=True)])
            # 重边聚合兜底: (src,rel,dst) 唯一, 合并 props 并累计计数
            edge_rows = {}
            for s, t, d in self.g.edges(data=True):
                rel = d.get('rel')
                key = (s, rel, t)
                if key in edge_rows:
                    nd = dict(edge_rows[key][3])
                    nd['count'] = int(nd.get('count', 1)) + int(d.get('count', 1))
                    edge_rows[key] = (s, rel, t, nd)
                else:
                    edge_rows[key] = (s, rel, t, dict(d))
            conn.executemany(
                "INSERT INTO edges(src, rel, dst, props) VALUES(?,?,?,?)",
                [(s, rel, t, json.dumps(d, ensure_ascii=False, default=str))
                 for s, rel, t, d in edge_rows.values()])
            conn.commit()
        finally:
            conn.close()
        return self.g.number_of_nodes(), self.g.number_of_edges()

    def load(self):
        conn = self._conn()
        try:
            self.g = nx.MultiDiGraph()
            for nid, kind, props in conn.execute("SELECT id, kind, props FROM nodes"):
                d = json.loads(props)
                d.setdefault('kind', kind)
                self.g.add_node(nid, **d)
            for s, r, t, props in conn.execute("SELECT src, rel, dst, props FROM edges"):
                d = json.loads(props)
                d.setdefault('rel', r)
                self.g.add_edge(s, t, **d)
        finally:
            conn.close()
        return self.g.number_of_nodes(), self.g.number_of_edges()

    # ---------- 图运算 ----------
    def neighbors(self, node_id, rel=None):
        out = []
        for _, t, d in self.g.out_edges(node_id, data=True):
            if rel is None or d.get('rel') == rel:
                out.append((t, d.get('rel')))
        for s, _, d in self.g.in_edges(node_id, data=True):
            if rel is None or d.get('rel') == rel:
                out.append((s, d.get('rel')))
        return out

    def subgraph(self, node_id, hop=1):
        """井/区块等实体的 hop 跳邻域子图"""
        nodes = {node_id}
        frontier = {node_id}
        for _ in range(hop):
            nxt = set()
            for n in frontier:
                nxt.update(t for _, t in self.g.out_edges(n))
                nxt.update(s for s, _ in self.g.in_edges(n))
            nodes.update(nxt)
            frontier = nxt
        return self.g.subgraph(nodes).copy()

    def stats(self):
        kinds = Counter(d.get('kind', '?') for _, d in self.g.nodes(data=True))
        rels = Counter(d.get('rel', '?') for _, _, d in self.g.edges(data=True))
        return kinds, rels

    def isolated(self, kinds=('Well', 'Block', 'TestInterval')):
        """孤立实体: 没有任何边的节点"""
        return [n for n, d in self.g.nodes(data=True)
                if d.get('kind') in kinds and self.g.degree(n) == 0]


class GraphBuilder:
    """骨架抽取: 元数据 + 目录 + 试油表 -> 实体与核心关系"""

    def __init__(self, store):
        self.store = store
        self.g = store.g
        self.extractor = WellLocationExtractor() if WellLocationExtractor else None
        self._stats = Counter()
        self._doc_count = 0
        self._well_tests = defaultdict(set)  # 井 -> 已建 TestInterval id 集合(按井去重)
        self._doc_test = {}  # doc_id -> 无深度 test_id(同一源文档只建一个)

    # ---------- 实体创建 ----------
    def _add(self, nid, kind, **props):
        props['kind'] = kind
        if nid in self.g:
            # 合并别名/证据计数
            old = dict(self.g.nodes[nid])
            for k, v in props.items():
                if k == 'kind':
                    continue
                if k == 'aliases':
                    old['aliases'] = sorted(set(old.get('aliases', [])) | set(v))
                elif k not in old or not old[k]:
                    old[k] = v
            props = old
        self.g.add_node(nid, **props)
        return nid

    def _link(self, src, rel, dst, **props):
        if not src or not dst:
            return
        props.setdefault('rel', rel)
        # 去重: 同 (src,rel,dst) 边已存在时累加证据计数
        ed = self.g.get_edge_data(src, dst)
        if ed:
            for _, d in ed.items():
                if d.get('rel') == rel:
                    d['count'] = int(d.get('count', 1)) + 1
                    return
        self.g.add_edge(src, dst, **props)
        self._stats[('edge', rel)] += 1

    # ---------- 抽取主流程 ----------
    def build(self):
        t0 = time.time()
        self.g.clear()
        files = self._collect_md_files()
        self._stats['files_scanned'] = len(files)

        for path in files:
            self._process_file(path)

        # 井名变体归并(巴西 ANP 注册号体系等高置信模式)
        self._stats['well_merged'] = self.merge_well_variants()

        # 国家/区块归一: 孤立国家清掉
        self._prune_empty_countries()

        # 区域构造抽取: 盆地/凹陷/隆起/区块/油气田/构造
        self._stats['regional_extracted'] = self._extract_regional_structures()

        self._stats['build_seconds'] = round(time.time() - t0, 1)
        return self._stats

    def merge_well_variants(self):
        """归并高置信井名变体, 每次 build 自动执行。

        规则(保守, 仅两类高置信模式):
          R1 数字前缀变体: 3-RJS-731 ~ RJS-731 / 8-BUZ-15 ~ BUZ-15 (去 ^\\d+- 前缀相等)
          R2 注册号州后缀: 2-ANP-2A-RJS ~ 2-ANP-2A (去 ^\\d+-[A-Z]+-\\d+[A-Z]*-[A-Z]{2,4}$ 后缀)
        歧义防护: 同一别名被多个注册号指向(如 3-RJS-731 与 7-RJS-731 共享 RJS-731)时整组跳过;
                  组内别名数 != 1 时跳过。
        归并方向: 保留更完整(较长)名字, 别名节点全部边迁移后删除。
        """
        import re as _re
        wells = [n for n, d in self.g.nodes(data=True) if d.get('kind') == 'Well']
        group = {}   # canonical(较长/注册号) -> set(alias)
        for n in wells:
            m = _re.match(r'^(\d+)-(.*)$', n)
            if m and m.group(2) in wells and m.group(2) != n:
                group.setdefault(n, set()).add(m.group(2))
            m2 = _re.match(r'^(\d+-[A-Z]+-\d+[A-Z]*)-[A-Z]{2,4}$', n)
            if m2 and m2.group(1) in wells and m2.group(1) != n:
                group.setdefault(n, set()).add(m2.group(1))
        merged = 0
        for canonical in list(group):
            aliases = {a for a in group[canonical] if a != canonical and a in self.g}
            if len(aliases) != 1:
                continue  # 歧义/多别名, 跳过
            alias = aliases.pop()
            # 别名被其他注册号共享 -> 歧义, 跳过
            if any(alias in v for k, v in group.items() if k != canonical):
                continue
            # 迁移 alias 全部出边
            for s, t, d in list(self.g.out_edges(alias, data=True)):
                rel = d.get('rel')
                ed = self.g.get_edge_data(canonical, t)
                dup = any(x.get('rel') == rel for x in ed.values()) if ed else False
                if not dup:
                    self.g.add_edge(canonical, t, **d)
                else:
                    for x in ed.values():
                        if x.get('rel') == rel:
                            x['count'] = int(x.get('count', 1)) + int(d.get('count', 1))
                            break
            # 迁移 alias 全部入边
            for s, t, d in list(self.g.in_edges(alias, data=True)):
                rel = d.get('rel')
                ed = self.g.get_edge_data(s, canonical)
                dup = any(x.get('rel') == rel for x in ed.values()) if ed else False
                if not dup:
                    self.g.add_edge(s, canonical, **d)
                else:
                    for x in ed.values():
                        if x.get('rel') == rel:
                            x['count'] = int(x.get('count', 1)) + int(d.get('count', 1))
                            break
            # 归并节点属性(别名/计数)
            old = dict(self.g.nodes[canonical])
            aold = dict(self.g.nodes[alias])
            old['aliases'] = sorted(set(old.get('aliases', [])) | set(aold.get('aliases', [])) | {alias})
            for k, v in aold.items():
                if k in ('kind', 'aliases'):
                    continue
                if k not in old or not old[k]:
                    old[k] = v
            self.g.nodes[canonical].update(old)
            self.g.remove_node(alias)
            merged += 1
        return merged

    def _collect_md_files(self):
        files = []
        if not os.path.isdir(LOCAL_DIR):
            return files
        # 扫描 data\local 全部(根目录+子目录), 排除备份目录
        for root, dirs, names in os.walk(LOCAL_DIR):
            dirs[:] = [x for x in dirs if 'bak' not in x.lower()]
            for name in names:
                if name.lower().endswith('.md'):
                    files.append(os.path.join(root, name))
        return files

    def _process_file(self, path):
        self._doc_count += 1
        rel_dir = os.path.relpath(path, LOCAL_DIR)
        fname = os.path.basename(path)
        fm = _read_frontmatter(path)

        # --- 1. 元数据: frontmatter 优先, 文件名/路径兜底 ---
        loc = {}
        if self.extractor:
            try:
                loc = self.extractor.extract_from_filename(fname) or {}
            except Exception:
                loc = {}
        well_raw = fm.get('well_name') or loc.get('extracted_well_name')
        well = _norm_well(well_raw)

        region_raw = fm.get('region') or loc.get('region')
        country_raw = fm.get('country') or loc.get('country')
        block_raw = fm.get('oil_field') or loc.get('oil_field') or \
                    (region_raw if self._is_block_name(region_raw) else None)
        # 井名硬约束 -> 区块/国家(优先于软检测), 结果读回 dict
        if well and self.extractor:
            try:
                rc = {'country': country_raw, 'region': region_raw, 'oil_field': block_raw}
                self.extractor._apply_hard_constraints(rc, well, is_path=False)
                country_raw = rc.get('country') or country_raw
                block_raw = rc.get('oil_field') or block_raw
            except Exception:
                pass
        # 图谱侧补充: region 语义映射(如 拉美->巴西)
        if country_raw:
            country_raw = GRAPH_REGION_COUNTRY.get(country_raw, country_raw)
        # 图谱侧补充: 井名前缀/段 -> 国家(仅补国家, 不猜区块)
        if not country_raw and well:
            tokens = {x.upper() for x in well.replace('_', '-').split('-') if x}
            for prefix, cc in GRAPH_PREFIX_COUNTRY:
                if prefix in tokens:
                    country_raw = cc
                    break
        # 区块名硬约束
        if not block_raw and self.extractor and country_raw:
            for k, (c, b) in (self.extractor.BLOCK_REGION_MAP or {}).items():
                if k in fname or k in (region_raw or ''):
                    block_raw = b
                    country_raw = country_raw or c
                    break

        country = self._norm_country(country_raw)
        block = self._norm_block(block_raw) if block_raw else None
        is_welltest_doc = self._is_welltest_doc(rel_dir, fname)

        # --- 2. 建文档证据节点(chunk 分块按 source_file 归并为同一文档实体) ---
        doc_id = fm.get('source_file') or path
        if doc_id not in self.g:
            self._add(doc_id, 'Document',
                      title=fm.get('title') or os.path.splitext(fname)[0],
                      category=fm.get('category', 'local'),
                      file_type=fm.get('file_type', ''),
                      depth_range=fm.get('depth_range', ''),
                      subdir=rel_dir.split(os.sep)[0],
                      chunks=int(fm.get('chunk_total') or 1))
        else:
            # 归并分块: 累加 chunk 数/证据计数
            nd = dict(self.g.nodes[doc_id])
            nd['chunks'] = max(int(nd.get('chunks', 1)), int(fm.get('chunk_total') or 1))
            self.g.nodes[doc_id].update(nd)

        # --- 3. 井实体 + 证据/位置关系 ---
        if well:
            self._add(well, 'Well', aliases=[well_raw or well],
                      region=region_raw or '', depth_range=fm.get('depth_range', ''),
                      docs=doc_id)
            self._link(doc_id, 'EVIDENCE', well, source='frontmatter')
            # 区块与国家同名(如 尼日尔)时降级为仅国家, 避免国家被建成 Block
            if block and country and block == country:
                block = None
            if block:
                self._add(block, 'Block')
                self._link(well, 'LOCATED_IN', block, source='mapping')
                if country:
                    self._add(country, 'Country')
                    self._link(block, 'LOCATED_IN', country, source='mapping')
            elif country:
                self._add(country, 'Country')
                self._link(well, 'LOCATED_IN', country, source='mapping')
        elif block:
            if country and block == country:
                block = None
            if block:
                self._add(block, 'Block', docs=doc_id)
                self._link(doc_id, 'EVIDENCE', block, source='frontmatter')
            if country:
                self._add(country, 'Country', docs=doc_id)
                if block and block != country:
                    self._link(block, 'LOCATED_IN', country, source='mapping')
        elif country:
            self._add(country, 'Country', docs=doc_id)

        # --- 4. 试油层位实体(试油/测试类文档, 按井去重) ---
        text_head = self._read_text_head(path) if (is_welltest_doc or '参数' in fname or '解释' in fname) else ''
        if is_welltest_doc and well:
            dr = fm.get('depth_range') or loc.get('depth_range') or ''
            if not dr:
                td, bd = fm.get('top_depth'), fm.get('bottom_depth')
                if td and bd:
                    dr = f"{td}-{bd}"
                elif td:
                    dr = str(td)
            if dr:
                test_id = f"{well}@{dr}"
            elif doc_id in self._doc_test:
                test_id = self._doc_test[doc_id]  # 同源文档复用
            else:
                n_test = len(self._well_tests.get(well, set()))
                test_id = f"{well}@test#{n_test + 1}"
                self._doc_test[doc_id] = test_id
            if test_id in self.g:  # 已存在: 仅追加证据文档
                self._link(doc_id, 'EVIDENCE', test_id, source='welltest_doc')
                self._link(well, 'HAS_TEST', test_id, source='dir_welltest')
            else:
                concl = _extract_conclusion(fm, text_head)
                test_props = {'depth_range': dr}
                if concl:
                    test_props['conclusion'] = concl
                test_props['docs'] = doc_id
                self._add(test_id, 'TestInterval', **test_props)
                self._link(well, 'HAS_TEST', test_id, source='dir_welltest')
                self._link(doc_id, 'EVIDENCE', test_id, source='welltest_doc')
                if block:
                    self._link(test_id, 'TEST_IN', block, source='well')
                self._well_tests[well].add(test_id)

        # --- 5. Archie 参数实体(试油/参数/解释类文档轻量抽取) ---
        if text_head:
            arch = _extract_archie(text_head)
            if arch:
                pid = 'Archie:' + ':'.join(f"{k}={arch[k]}" for k in sorted(arch))
                self._add(pid, 'Parameter', **arch, docs=doc_id)
                self._link(doc_id, 'EVIDENCE', pid, source='content_extract')
                if well:
                    self._link(well, 'USES_PARAM', pid, source='cooccurrence')
                elif block:
                    self._link(block, 'USES_PARAM', pid, source='cooccurrence')

        # --- 6. 无井无区块但有国家关键词的文档 -> 国家证据 ---
        self._stats['docs'] = self._doc_count

    def _read_text_head(self, path, chars=20000):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read(chars)
        except Exception:
            return ''

    def _is_welltest_doc(self, rel_dir, fname):
        head = os.sep.join(rel_dir.split(os.sep)[:2]).lower()
        if 'well_test' in rel_dir.lower() or '试油' in rel_dir:
            return True
        keys = ['试油', '测试', 'well test', 'welltest', 'dst', 'production test',
                '完井', '产能', '射孔', '地层测试']
        low = fname.lower()
        return any(k in low for k in keys)

    def _is_block_name(self, region):
        if not region:
            return False
        # 国家名/区域名不得作为区块名(防止国家被建成 Block 实体)
        if region in _KNOWN_COUNTRIES:
            return False
        return any(k in region for k in
                   ['区块', '气田', '盆地', '凹陷', '油田', '构造', '项目', '台地'])

    def _norm_country(self, raw):
        """国家名归一为中文(优先)"""
        if not raw:
            return None
        s = str(raw).strip()
        cmap = getattr(self.extractor, 'COUNTRY_MAP', {}) if self.extractor else {}
        for zh, en in (cmap or {}).items():
            if s == en:
                return zh
            if s == zh:
                return zh
        # 常见英文直接映射
        en_zh = {'Venezuela': '委内瑞拉', 'Niger': '尼日尔', 'Chad': '乍得',
                 'Brazil': '巴西', 'Turkmenistan': '土库曼', 'Uzbekistan': '乌兹别克斯坦',
                 'Suriname': '苏里南', 'Bangladesh': '孟加拉', 'Peru': '秘鲁',
                 'Sudan': '苏丹', 'Myanmar': '缅甸', 'Russia': '俄罗斯',
                 'Kazakhstan': '哈萨克斯坦', 'Azerbaijan': '阿塞拜疆', 'Indonesia': '印尼',
                 'Syria': '叙利亚', 'Iran': '伊朗', 'Iraq': '伊拉克', 'Oman': '阿曼',
                 'Egypt': '埃及', 'Algeria': '阿尔及利亚', 'Angola': '安哥拉'}
        if s in en_zh:
            return en_zh[s]
        if '中国' in s or s in ('China', '大庆', '胜利'):
            return '中国'
        if '中东' in s or s == 'Middle East':
            return '中东'
        return s if len(s) <= 12 else None

    def _norm_block(self, raw):
        return str(raw).strip().strip('"\'') or None

    def _prune_empty_countries(self):
        """删除没有任何边且非证据目标的孤立国家节点(避免噪声)"""
        for n, d in list(self.g.nodes(data=True)):
            if d.get('kind') == 'Country' and self.g.degree(n) == 0:
                self.g.remove_node(n)

    def _extract_regional_structures(self):
        """自动区域构造抽取: 盆地/凹陷/隆起/构造/油气田
        
        从 overseas 目录下的 md 文件中自动抽取地名，建立层级关系:
          Country -> Basin -> Sag/Uplift -> Structure -> Field -> Well
        
        原则:
          - 地区统一的地质知识往上收（盆地级）
          - 具体特征往下放（油田级）
        """
        import re
        import os
        
        # overseas 目录
        overseas_dir = os.path.join(LOCAL_DIR, 'well_test', 'overseas')
        if not os.path.isdir(overseas_dir):
            return 0
        
        # 地质分级模式（正则）
        patterns = {
            'Basin': [
                r'([A-Z][a-zA-Z\s]+)\s*Basin\b',      # Santos Basin
                r'([\u4e00-\u9fa5]{2,})盆地',           # 桑托斯盆地
            ],
            'Sag': [
                r'([A-Z][a-zA-Z\s]+)\s*Sag\b',        # Santos Sag
                r'([\u4e00-\u9fa5]{2,})凹陷',           # 桑托斯凹陷
            ],
            'Uplift': [
                r'([A-Z][a-zA-Z\s]+)\s*Uplift\b',     # Santos Uplift
                r'([\u4e00-\u9fa5]{2,})隆起',           # 桑托斯隆起
            ],
            'Structure': [
                r'([A-Z][a-zA-Z\s]+)\s*Structure\b',  # Chanin Structure
                r'([\u4e00-\u9fa5]{2,})构造',           # 昌德构造
            ],
            'Field': [
                r'([A-Z][a-zA-Z\s]+)\s*Field\b',      # Titas Field
                r'([\u4e00-\u9fa5]{2,})油田',           # 扎波塔尔油田
                r'([\u4e00-\u9fa5]{2,})气田',           # 提塔斯气田
            ],
        }
        
        # 噪音词（严格过滤）
        noise_words = {
            'the', 'and', 'for', 'are', 'was', 'were', 'been', 'this', 'that',
            'these', 'those', 'with', 'from', 'have', 'has', 'had', 'not', 'but',
            'they', 'their', 'them', 'then', 'than', 'when', 'where', 'which',
            'while', 'will', 'would', 'could', 'should', 'about', 'after',
            'before', 'between', 'through', 'during', 'because', 'although',
            'though', 'until', 'since', 'also', 'only', 'just', 'very', 'much',
            'many', 'some', 'any', 'all', 'each', 'every', 'both', 'either',
            'neither', 'one', 'two', 'first', 'second', 'last', 'next',
            'previous', 'following', 'above', 'below', 'under', 'over', 'again',
            'further', 'once', 'here', 'there', 'why', 'how', 'what', 'who',
            'company', 'technical', 'geological', 'sedimentary', 'crystal',
            'magnetic', 'gravity', 'flame', 'trending', 'daily', 'supervisor',
            'another', 'far', 'near', 'along', 'across', 'behind', 'beside',
            'including', 'given', 'known', 'unknown', 'specific', 'general',
            'special', 'particular', 'certain', 'different', 'similar', 'same',
            'other', 'others', 'such', 'like', 'unlike', 'new', 'old',
            'modern', 'ancient', 'historical', 'future', 'past', 'present',
            'absent', 'missing', 'available', 'possible', 'impossible',
            'probable', 'likely', 'unlikely', 'certain', 'uncertain', 'clear',
            'unclear', 'obvious', 'subtle', 'hidden', 'visible', 'real',
            'false', 'true', 'fake', 'genuine', 'artificial', 'natural',
            'normal', 'abnormal', 'regular', 'irregular', 'common',
            'uncommon', 'rare', 'frequent', 'constant', 'variable', 'fixed',
            'changing', 'stable', 'unstable', 'steady', 'smooth', 'rough',
            'flat', 'uneven', 'level', 'even', 'odd', 'straight', 'curved',
            'bent', 'twisted', 'winding', 'parallel', 'perpendicular',
            'diagonal', 'vertical', 'horizontal', 'inclined', 'sloped',
            'tilted', 'classification', 'important', 'evaluation', 'table',
            'petrophysical', 'reservoir', 'best', 'our', 'at', 'in', 'on',
            'of', 'to', 'for', 'with', 'by', 'from', 'as', 'is', 'are',
            'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'may',
            'might', 'must', 'can', 'could', 'need', 'dare', 'ought',
            'used', 'had', 'better', 'rather', 'sooner', 'later',
        }
        
        def is_noise(name):
            name_lower = name.lower().strip()
            # 长度限制
            if len(name_lower) < 3:
                return True
            # 单词数限制（最多3个单词）
            words = name_lower.split()
            if len(words) > 3:
                return True
            # 包含换行符
            if '\n' in name or '\r' in name:
                return True
            # 纯数字
            if name_lower.replace(' ', '').replace('-', '').isdigit():
                return True
            # 在噪音词列表中
            if name_lower in noise_words:
                return True
            # 包含噪音词
            for noise in noise_words:
                if noise in name_lower:
                    return True
            return False
        
        # 从 overseas 目录扫描
        extracted = 0
        country_entities = {}
        
        for country_dir in os.listdir(overseas_dir):
            country_path = os.path.join(overseas_dir, country_dir)
            if not os.path.isdir(country_path):
                continue
            
            country = country_dir
            
            # 确保国家节点存在
            if country not in self.g:
                self._add(country, 'Country', name=country)
            
            country_entities[country] = {
                'Basin': set(), 'Sag': set(), 'Uplift': set(),
                'Structure': set(), 'Field': set()
            }
            
            # 扫描该国家目录下的 md 文件（最多20个）
            md_files = [f for f in os.listdir(country_path) if f.endswith('.md')][:20]
            
            for md_file in md_files:
                md_path = os.path.join(country_path, md_file)
                try:
                    with open(md_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                except:
                    continue
                
                # 匹配各种模式
                for kind, pats in patterns.items():
                    for pat in pats:
                        matches = re.findall(pat, content, re.IGNORECASE)
                        for match in matches:
                            name = match.strip()
                            if not is_noise(name):
                                country_entities[country][kind].add(name)
        
        # 建立层级关系
        for country, kinds in country_entities.items():
            if country not in self.g:
                continue
            
            # 1. Country -> Basin
            for basin_name in kinds['Basin']:
                basin_id = f'{country}_Basin_{basin_name}'
                if basin_id not in self.g:
                    self._add(basin_id, 'Basin', name=basin_name, country=country)
                    extracted += 1
                self._link(country, 'CONTAINS', basin_id)
            
            # 2. Basin -> Sag/Uplift
            for sag_name in kinds['Sag']:
                sag_id = f'{country}_Sag_{sag_name}'
                if sag_id not in self.g:
                    self._add(sag_id, 'Sag', name=sag_name, country=country)
                    extracted += 1
                # 挂到第一个盆地
                if kinds['Basin']:
                    basin_name = list(kinds['Basin'])[0]
                    basin_id = f'{country}_Basin_{basin_name}'
                    self._link(basin_id, 'CONTAINS', sag_id)
            
            for uplift_name in kinds['Uplift']:
                uplift_id = f'{country}_Uplift_{uplift_name}'
                if uplift_id not in self.g:
                    self._add(uplift_id, 'Uplift', name=uplift_name, country=country)
                    extracted += 1
                if kinds['Basin']:
                    basin_name = list(kinds['Basin'])[0]
                    basin_id = f'{country}_Basin_{basin_name}'
                    self._link(basin_id, 'CONTAINS', uplift_id)
            
            # 3. Structure -> Field
            for struct_name in kinds['Structure']:
                struct_id = f'{country}_Structure_{struct_name}'
                if struct_id not in self.g:
                    self._add(struct_id, 'Structure', name=struct_name, country=country)
                    extracted += 1
                # 挂到盆地
                if kinds['Basin']:
                    basin_name = list(kinds['Basin'])[0]
                    basin_id = f'{country}_Basin_{basin_name}'
                    self._link(basin_id, 'CONTAINS', struct_id)
            
            for field_name in kinds['Field']:
                field_id = f'{country}_Field_{field_name}'
                if field_id not in self.g:
                    self._add(field_id, 'Field', name=field_name, country=country)
                    extracted += 1
                # 挂到构造或盆地
                if kinds['Structure']:
                    struct_name = list(kinds['Structure'])[0]
                    struct_id = f'{country}_Structure_{struct_name}'
                    self._link(struct_id, 'CONTAINS', field_id)
                elif kinds['Basin']:
                    basin_name = list(kinds['Basin'])[0]
                    basin_id = f'{country}_Basin_{basin_name}'
                    self._link(basin_id, 'CONTAINS', field_id)
        
        return extracted


def gap_report(store):
    """图谱缺口自检 -> 定向补全清单"""
    g = store.g
    lines = []
    kinds, rels = store.stats()

    wells = [n for n, d in g.nodes(data=True) if d.get('kind') == 'Well']
    blocks = [n for n, d in g.nodes(data=True) if d.get('kind') == 'Block']
    tests = [n for n, d in g.nodes(data=True) if d.get('kind') == 'TestInterval']
    docs = [n for n, d in g.nodes(data=True) if d.get('kind') == 'Document']
    params = [n for n, d in g.nodes(data=True) if d.get('kind') == 'Parameter']

    lines.append(f"实体: 井 {len(wells)} / 区块 {len(blocks)} / 国家 "
                 f"{sum(1 for _,d in g.nodes(data=True) if d.get('kind')=='Country')} / "
                 f"试油层位 {len(tests)} / 参数 {len(params)} / 文档 {len(docs)}")
    lines.append(f"关系: {sum(1 for _ in g.edges())} 条")

    # 1) 孤立井/区块/试油(无任何关系)
    iso = store.isolated()
    iso_well = [n for n in iso if g.nodes[n].get('kind') == 'Well']
    iso_block = [n for n in iso if g.nodes[n].get('kind') == 'Block']
    iso_test = [n for n in iso if g.nodes[n].get('kind') == 'TestInterval']
    lines.append(f"缺口1-孤立实体: 井 {len(iso_well)} / 区块 {len(iso_block)} / 试油层位 {len(iso_test)}")
    if iso_well:
        lines.append("  孤立井: " + ", ".join(iso_well[:30]) + (" ..." if len(iso_well) > 30 else ""))

    # 2) 井未挂区块(缺区域定位)
    no_block = [n for n in wells if not any(d.get('rel') == 'LOCATED_IN'
                 for _, _, d in g.out_edges(n, data=True))]
    lines.append(f"缺口2-井无区块归属: {len(no_block)}")
    if no_block:
        lines.append("  " + ", ".join(sorted(no_block)[:40]) + (" ..." if len(no_block) > 40 else ""))

    # 3) 井无试油关联(缺试油金标准)
    no_test = [n for n in wells if not any(d.get('rel') == 'HAS_TEST'
                 for _, _, d in g.out_edges(n, data=True))]
    lines.append(f"缺口3-井无试油关联: {len(no_test)}")
    if no_test:
        lines.append("  " + ", ".join(sorted(no_test)[:40]) + (" ..." if len(no_test) > 40 else ""))

    # 4) 试油无结论
    no_concl = [n for n in tests if not g.nodes[n].get('conclusion')]
    lines.append(f"缺口4-试油无结论标注: {len(no_concl)}")
    if no_concl:
        lines.append("  " + ", ".join(sorted(no_concl)[:30]) + (" ..." if len(no_concl) > 30 else ""))

    # 5) 无参数井/区块(缺解释参数知识)
    no_param_well = [n for n in wells if not any(d.get('rel') == 'USES_PARAM'
                     for _, _, d in g.out_edges(n, data=True))]
    lines.append(f"缺口5-井无解释参数: {len(no_param_well)}")
    if no_param_well:
        lines.append("  " + ", ".join(sorted(no_param_well)[:30]) + (" ..." if len(no_param_well) > 30 else ""))

    # 6) 按国家统计井覆盖(沿 LOCATED_IN 传递到 Country, 明确哪些国家资料最缺)
    def _country_of(well):
        seen = {well}
        cur = [well]
        while cur:
            nxt = []
            for n in cur:
                for _, t, ed in g.out_edges(n, data=True):
                    if ed.get('rel') != 'LOCATED_IN' or t in seen:
                        continue
                    seen.add(t)
                    if g.nodes[t].get('kind') == 'Country':
                        return t
                    nxt.append(t)
            cur = nxt
        return None

    by_country = defaultdict(list)
    for n, d in g.nodes(data=True):
        if d.get('kind') != 'Well':
            continue
        by_country[_country_of(n) or '(未知)'].append(n)
    lines.append(f"缺口6-按国家井数: " + " / ".join(
        f"{c}:{len(v)}" for c, v in sorted(by_country.items(),
        key=lambda x: -len(x[1]))[:15]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description='测井解释知识图谱 (logGraph)')
    ap.add_argument('cmd', nargs='?', default='stats',
                    choices=['build', 'stats', 'subgraph', 'gap', 'export'])
    ap.add_argument('args', nargs='*')
    args = ap.parse_args()

    store = GraphStore()

    if args.cmd == 'build':
        print(f"开始骨架抽取: {LOCAL_DIR}")
        builder = GraphBuilder(store)
        st = builder.build()
        n, e = store.save()
        print(f"构建完成: 文档 {st['files_scanned']} -> 节点 {n} / 关系 {e} "
              f"({st.get('build_seconds', 0)}s)")
        print(gap_report(store))

    elif args.cmd == 'stats':
        if not os.path.exists(DB_PATH):
            print("图谱尚未构建, 先运行: python logGraph.py build")
            sys.exit(1)
        store.load()
        kinds, rels = store.stats()
        print("实体:", dict(kinds))
        print("关系:", dict(rels))
        print("总节点:", store.g.number_of_nodes(), "总边:", store.g.number_of_edges())

    elif args.cmd == 'gap':
        if not os.path.exists(DB_PATH):
            print("图谱尚未构建, 先运行: python logGraph.py build")
            sys.exit(1)
        store.load()
        print(gap_report(store))

    elif args.cmd == 'subgraph':
        if not args.args:
            print("用法: python logGraph.py subgraph <井名或区块名> [hop]")
            sys.exit(1)
        store.load()
        q = args.args[0].upper()
        hop = int(args.args[1]) if len(args.args) > 1 else 1
        cand = [n for n in store.g.nodes if q in n.upper()]
        if not cand:
            print(f"未找到包含 '{q}' 的实体")
            sys.exit(1)
        # 优先实体节点(井/区块/试油/参数/国家), 文档证据节点垫底
        def _prio(n):
            k = store.g.nodes[n].get('kind', '?')
            return {'Well': 0, 'Block': 1, 'TestInterval': 2, 'Parameter': 3,
                    'Country': 4}.get(k, 9)
        cand.sort(key=_prio)
        node = cand[0]
        if len(cand) > 1:
            print("候选:", ", ".join(sorted(cand[:20], key=_prio)))
        sg = store.subgraph(node, hop)
        print(f"子图 {node} (hop={hop}): {sg.number_of_nodes()} 节点 / {sg.number_of_edges()} 边")
        for n, d in sg.nodes(data=True):
            extra = ""
            if d.get('kind') == 'Well':
                extra = f" 区块证据文档 {len(set(d.get('docs','').split(',')))} 个"
            print(f"  [{d.get('kind','?')}] {n}{extra}")
        print("--- 关系 ---")
        for s, t, d in sg.edges(data=True):
            print(f"  {s} -[{d.get('rel')}]-> {t}")

    elif args.cmd == 'gap':
        if not os.path.exists(DB_PATH):
            print("图谱尚未构建, 先运行: python logGraph.py build")
            sys.exit(1)
        store.load()
        print(gap_report(store))

    elif args.cmd == 'export':
        if not os.path.exists(DB_PATH):
            print("图谱尚未构建, 先运行: python logGraph.py build")
            sys.exit(1)
        store.load()
        data = {
            'nodes': [{**d, 'id': n, 'kind': d.get('kind', '?')}
                      for n, d in store.g.nodes(data=True)],
            'edges': [{'src': s, 'rel': d.get('rel'), 'dst': t,
                       **{k: v for k, v in d.items() if k != 'rel'}}
                      for s, t, d in store.g.edges(data=True)],
        }
        with open(EXPORT_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1, default=str)
        try:
            # GraphML 属性须为 str/int/float/bool, 先全部字符串化再写
            gg = nx.MultiDiGraph()
            for n, d in store.g.nodes(data=True):
                gg.add_node(n, **{k: str(v) for k, v in d.items()})
            for s, t, d in store.g.edges(data=True):
                gg.add_edge(s, t, **{k: str(v) for k, v in d.items()})
            nx.write_graphml(gg, EXPORT_GRAPHML)
            print(f"导出: {EXPORT_JSON} / {EXPORT_GRAPHML}")
        except Exception as e:
            print(f"导出 JSON: {EXPORT_JSON} (GraphML 失败: {e})")


if __name__ == '__main__':
    main()
