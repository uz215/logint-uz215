# -*- coding: utf-8 -*-
"""短语级英→中归一补丁：让整串外文字段（如 'Cambro-Ordovician sandstone reservoir'）
归一成中文，与中文写法落到同一 canonical，彻底杜绝中英重复节点。

1) region_normalize.yaml: term_mapping 追加地质年代/储层术语
2) region_normalizer.py: term_pairs + normalize_phrase()（词边界替换、长词优先、中文间去空格）
3) bootstrap_knowledge.py: _cn 支持 kind='phrase'；抽取字段改用 phrase
保 BOM / 行尾原子替换，逐锚点校验。
"""
import re
import os
from pathlib import Path

EXTRA_TERMS = [
    ('cambro-ordovician', '寒武-奥陶系'),
    ('lower cretaceous', '下白垩统'), ('upper cretaceous', '上白垩统'),
    ('cretaceous', '白垩系'), ('jurassic', '侏罗系'), ('triassic', '三叠系'),
    ('permian', '二叠系'), ('carboniferous', '石炭系'), ('devonian', '泥盆系'),
    ('silurian', '志留系'), ('ordovician', '奥陶系'), ('cambrian', '寒武系'),
    ('paleozoic', '古生界'), ('mesozoic', '中生界'), ('cenozoic', '新生界'),
    ('miocene', '中新统'), ('eocene', '始新统'), ('paleocene', '古新统'),
    ('sandstone reservoir', '砂岩储层'), ('carbonate reservoir', '碳酸盐岩储层'),
    ('shale gas', '页岩气'), ('tight sandstone', '致密砂岩'),
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
if 'term_mapping:' not in lines:
    raise SystemExit('term_mapping 段不存在')
insert_at = lines.index('geo_hierarchy:')
existing = '\n'.join(lines)
add = []
for en, cn in EXTRA_TERMS:
    if re.search(r'^  ' + re.escape(en) + r':', existing, re.M):
        continue
    add.append(f'  {en}: {cn}')
if add:
    block = ['  # 地质年代 / 储层：提升地层名整串归一覆盖（2026-11-13）'] + add + ['']
    lines[insert_at:insert_at] = block
    print(f'[yaml] 追加术语 {len(add)} 条')
n = write_atomic(YP, ybom, ynl, '\n'.join(lines))
print(f'[yaml] 写回 {n} bytes')

# ---------------- 2. region_normalizer.py ----------------
NP = Path('logknow/region_normalizer.py')
nbom, nnl, ntxt = split_raw(NP)

OLD_INIT = '''        self.country_map = self._build_country_lookup()
        self.term_map = self._build_term_lookup()
        self.hierarchy = self.cfg["geo_hierarchy"]["order"]
'''
NEW_INIT = '''        self.country_map = self._build_country_lookup()
        self.term_map = self._build_term_lookup()
        # 原始英文->中文，按长度降序供短语替换（长词优先，避免 "sandstone" 抢先命中）
        self.term_pairs = sorted(
            [(str(en), str(cn)) for en, cn in (self.cfg.get("term_mapping") or {}).items()],
            key=lambda x: -len(x[0]))
        self.hierarchy = self.cfg["geo_hierarchy"]["order"]
'''
if ntxt.count(OLD_INIT) != 1:
    raise SystemExit('normalizer __init__ 锚点异常')
ntxt = ntxt.replace(OLD_INIT, NEW_INIT, 1)

OLD_TERM = '''    def normalize_term(self, raw_name: str) -> Optional[str]:
        """外文通用术语 -> 中文规范名；未收录返回 None（专名保留原文）。"""
        if not raw_name:
            return None
        return self.term_map.get(self._key(raw_name))
'''
NEW_TERM = '''    def normalize_term(self, raw_name: str) -> Optional[str]:
        """外文通用术语 -> 中文规范名；未收录返回 None（专名保留原文）。"""
        if not raw_name:
            return None
        return self.term_map.get(self._key(raw_name))

    def normalize_phrase(self, text: str) -> Optional[str]:
        """整串字段的英->中归一：按词边界替换其中的英文通用术语（长词优先），
        并去掉中文之间的空格，使 'Cambro-Ordovician sandstone reservoir' 与
        '寒武-奥陶系砂岩储层' 收敛到同一 canonical。无替换返回 None。"""
        if not text:
            return None
        out = str(text)
        changed = False
        for en, cn in self.term_pairs:
            pat = re.compile(r'(?<![A-Za-z])' + re.escape(en) + r'(?![A-Za-z])', re.I)
            out, n = pat.subn(cn, out)
            if n:
                changed = True
        if not changed:
            return None
        out = re.sub(r'(?<=[\\u4e00-\\u9fff])\\s+(?=[\\u4e00-\\u9fff])', '', out)
        return out.strip()
'''
if ntxt.count(OLD_TERM) != 1:
    raise SystemExit('normalizer normalize_term 锚点异常')
ntxt = ntxt.replace(OLD_TERM, NEW_TERM, 1)
n = write_atomic(NP, nbom, nnl, ntxt)
print(f'[normalizer] 写回 {n} bytes')

# ---------------- 3. bootstrap_knowledge.py ----------------
BP = Path('logknow/bootstrap_knowledge.py')
bbom, bnl, btxt = split_raw(BP)

OLD_CN = '''    target = rn.normalize_country(s) if kind == 'country' else rn.normalize_term(s)
    if target and target != s:
        return target, s
    return s, ''
'''
NEW_CN = '''    if kind == 'country':
        target = rn.normalize_country(s)
    elif kind == 'phrase':
        target = rn.normalize_term(s) or rn.normalize_phrase(s)
    else:
        target = rn.normalize_term(s)
    if target and target != s:
        return target, s
    return s, ''
'''
if btxt.count(OLD_CN) != 1:
    raise SystemExit('bootstrap _cn 锚点异常')
btxt = btxt.replace(OLD_CN, NEW_CN, 1)

for field in ('basin', 'formation', 'method_name'):
    old = f"    {field}, _a = _cn({field}, 'term')"
    new = f"    {field}, _a = _cn({field}, 'phrase')"
    if btxt.count(old) != 1:
        raise SystemExit(f'bootstrap {field} 锚点异常')
    btxt = btxt.replace(old, new, 1)

n = write_atomic(BP, bbom, bnl, btxt)
print(f'[bootstrap_knowledge] 写回 {n} bytes')
print('=== 短语归一补丁完成 ===')
