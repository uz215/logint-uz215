# -*- coding: utf-8 -*-
"""外文→中文归一化补丁（用户定调：扫描时外文识别成中文入库，不产生中英重复节点）

1) region_normalize.yaml：补齐 G 盘 12 国英文别名 + 新增「泰国」中文条目
   + 新增 term_mapping（测井/地质通用术语 英→中）
2) region_normalizer.py：_key() 归一（大小写/空格/下划线/连字符/点 不敏感），
   新增 normalize_term()
按原行尾(CRLF/LF)与 BOM 原子替换。
"""
import re
import os
from pathlib import Path

# ---------------- 配置 ----------------
# G:/入库整理后 实际 12 国目录名 -> 中文正典（与 entity 表 182 个中文国家节点一致）
EN_ALIASES = {
    '阿尔及利亚': ['Algeria', 'Algerie'],
    '乍得': ['Chad', 'Tchad'],
    '伊朗': ['Iran', 'Persia'],
    '伊拉克': ['Iraq'],
    '哈萨克斯坦': ['Kazakhstan'],
    '南苏丹': ['South Sudan', 'SouthSudan'],
    '苏丹': ['Sudan'],
    '泰国': ['Thailand', 'Siam'],
    '土库曼斯坦': ['Turkmenistan'],
    '孟加拉国': ['Bangladesh'],
    '印度尼西亚': ['Indonesia'],
    '尼日尔': ['Niger'],
}

# 测井/地质通用术语：英文写法一律转中文规范名（专名未命中者保留原文，靠 canonical 去重）
TERM_MAPPING = [
    ('sandstone', '砂岩'), ('shale', '泥岩'), ('claystone', '黏土岩'),
    ('siltstone', '粉砂岩'), ('conglomerate', '砾岩'),
    ('limestone', '石灰岩'), ('dolomite', '白云岩'), ('carbonate', '碳酸盐岩'),
    ('anhydrite', '硬石膏'), ('evaporite', '蒸发岩'), ('salt', '盐岩'),
    ('coal', '煤层'), ('igneous', '火成岩'), ('metamorphic', '变质岩'),
    ('reservoir', '储层'), ('source rock', '烃源岩'), ('cap rock', '盖层'),
    ('formation', '地层'), ('basin', '盆地'), ('sag', '凹陷'),
    ('block', '区块'), ('oilfield', '油气田'), ('structure', '构造'),
    ('gamma ray', '自然伽马'), ('spontaneous potential', '自然电位'),
    ('neutron porosity', '中子孔隙度'), ('density', '密度'),
    ('resistivity', '电阻率'), ('sonic', '声波时差'), ('caliper', '井径'),
    ('porosity', '孔隙度'), ('permeability', '渗透率'),
    ('water saturation', '含水饱和度'), ('saturation', '饱和度'),
    ('shale volume', '泥质含量'), ('vsh', '泥质含量'),
    ('archie', '阿尔奇公式'), ('simandoux', '西门度公式'),
    ('larionov', '拉里奥诺夫公式'), ('wylie', '威利公式'),
    ('threshold', '阈值'), ('cutoff', '截止值'), ('formula', '公式'),
    ('applicable condition', '适用条件'), ('interpretation method', '解释方法'),
]


def split_raw(p):
    raw = p.read_bytes()
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    txt = raw[len(bom):].decode('utf-8')
    nl = '\r\n' if '\r\n' in txt else '\n'
    return bom, nl, txt.replace('\r\n', '\n')


def write_atomic(p, bom, nl, text):
    out = bom + text.replace('\n', nl).encode('utf-8')
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_bytes(out)
    os.replace(tmp, p)
    return len(out)


# ---------------- 1. yaml ----------------
YP = Path('logknow/region_normalize.yaml')
ybom, ynl, ytxt = split_raw(YP)
lines = ytxt.split('\n')

try:
    cm_start = lines.index('country_mapping:')
except ValueError:
    raise SystemExit('yaml 结构异常：找不到 country_mapping')


def alias_values(start_idx, end_idx):
    """读取某个 aliases: 块已有的 - 项（到下一个两空格条目或 end 为止）"""
    vals, j = [], start_idx + 1
    while j < end_idx:
        s = lines[j]
        if re.match(r'^  \S', s) or (s and not s.startswith(' ')):
            break
        m = re.match(r'^\s*-\s*(.+?)\s*$', s)
        if m:
            vals.append(m.group(1))
        j += 1
    return vals, j


def find_entry(cn, end_idx):
    """每次重新扫描定位条目行：插入/展开会改变行数，不能缓存索引。"""
    for i in range(cm_start + 1, end_idx):
        if re.match(r'^  ' + re.escape(cn) + r':\s*$', lines[i]):
            a = i + 1 if i + 1 < end_idx and lines[i + 1].startswith('    aliases:') else None
            return i, a
    return None, None


new_blocks = []
for cn, ens in EN_ALIASES.items():
    gh_start = lines.index('geo_hierarchy:')
    ei, ai = find_entry(cn, gh_start)
    if ei is not None:
        if ai is None:
            raise SystemExit(f'{cn} 缺 aliases 行，需人工处理')
        existing, jend = alias_values(ai, gh_start)
        add = [e for e in ens if e.lower() not in {x.lower() for x in existing}]
        if not add:
            print(f'  [skip] {cn}: 英文别名已齐全')
            continue
        if lines[ai].strip() == 'aliases: []':
            block = ['    aliases:'] + ['    - ' + e for e in (existing + add) if e]
            lines[ai:jend] = block
        else:
            insert_at = ai + 1
            while insert_at < lines.index('geo_hierarchy:') and re.match(r'^\s*-\s*', lines[insert_at]):
                insert_at += 1
            lines[insert_at:insert_at] = ['    - ' + e for e in add]
        print(f'  [add ] {cn}: +{add}')
    else:
        new_blocks.append(cn)

if new_blocks:
    block = []
    for cn in new_blocks:
        block.append('  ' + cn + ':')
        block.append('    aliases:')
        for e in EN_ALIASES[cn]:
            block.append('    - ' + e)
        print(f'  [new ] 新增中文条目 {cn}: {EN_ALIASES[cn]}')
    gh_start = lines.index('geo_hierarchy:')
    lines[gh_start:gh_start] = block

# 追加 term_mapping 段（放在 geo_hierarchy 之前，顶层键）
gh_start = lines.index('geo_hierarchy:')
if not any(l.startswith('term_mapping:') for l in lines):
    tblock = ['term_mapping:', '  # 测井/地质通用术语 英→中：扫描外文资料时归一成中文入库']
    tblock += [f'  {en}: {cn}' for en, cn in TERM_MAPPING]
    tblock.append('')
    lines[gh_start:gh_start] = tblock
    print(f'  [new ] term_mapping: {len(TERM_MAPPING)} 条术语')

n = write_atomic(YP, ybom, ynl, '\n'.join(lines))
print(f'=== yaml 写回 {n} bytes (行尾={"CRLF" if ynl == chr(13)+chr(10) else "LF"}) ===')

# ---------------- 2. region_normalizer.py ----------------
NP = Path('logknow/region_normalizer.py')
nbom, nnl, ntxt = split_raw(NP)

OLD_BUILD = '''    def _build_country_lookup(self):
        lookup = {}
        for main, item in self.cfg["country_mapping"].items():
            lookup[main] = main
            for alias in item.get("aliases", []):
                lookup[alias] = main
        return lookup

    def normalize_country(self, raw_name: str) -> Optional[str]:
        if not raw_name:
            return None
        raw = raw_name.strip()
        return self.country_map.get(raw, None)
'''
NEW_BUILD = '''    @staticmethod
    def _key(s) -> str:
        """归一匹配键：忽略大小写、空格/下划线/连字符/点/括号差异，
        使 'South Sudan' / 'south_sudan' / 'SOUTH-SUDAN' 命中同一中文正典。"""
        return re.sub(r'[\\s_\\-\\.\\u00b7()（）]', '', str(s).strip().lower())

    def _build_country_lookup(self):
        lookup = {}
        for main, item in self.cfg["country_mapping"].items():
            lookup[self._key(main)] = main
            for alias in item.get("aliases", []):
                lookup[self._key(alias)] = main
        return lookup

    def _build_term_lookup(self):
        lookup = {}
        for en, cn in (self.cfg.get("term_mapping") or {}).items():
            lookup[self._key(en)] = cn
        return lookup

    def normalize_country(self, raw_name: str) -> Optional[str]:
        """外文国名 -> 中文正典名；已是中文正典则原样返回；未收录返回 None。"""
        if not raw_name:
            return None
        return self.country_map.get(self._key(raw_name))

    def normalize_term(self, raw_name: str) -> Optional[str]:
        """外文通用术语 -> 中文规范名；未收录返回 None（专名保留原文）。"""
        if not raw_name:
            return None
        return self.term_map.get(self._key(raw_name))
'''
if ntxt.count(OLD_BUILD) != 1:
    raise SystemExit('region_normalizer.py: _build_country_lookup 锚点命中异常')
ntxt = ntxt.replace(OLD_BUILD, NEW_BUILD, 1)

OLD_INIT = '''        self.country_map = self._build_country_lookup()
        self.hierarchy = self.cfg["geo_hierarchy"]["order"]
'''
NEW_INIT = '''        self.country_map = self._build_country_lookup()
        self.term_map = self._build_term_lookup()
        self.hierarchy = self.cfg["geo_hierarchy"]["order"]
'''
if ntxt.count(OLD_INIT) != 1:
    raise SystemExit('region_normalizer.py: __init__ 锚点命中异常')
ntxt = ntxt.replace(OLD_INIT, NEW_INIT, 1)

n = write_atomic(NP, nbom, nnl, ntxt)
print(f'=== region_normalizer.py 写回 {n} bytes ===')
