# -*- coding: utf-8 -*-
"""把「外文→中文归一」接入 bootstrap_knowledge.py 入库链路：
1) 懒加载 RegionNormalizer + _cn()（country 用国别正典 / term 用术语表）
2) simple_geo_extract 抽完后归一名，strata_meta.foreign_alias 保留原文可追溯
3) GeoKnowledgeLoader.ingest_single_record 入库前对 country 再归一（双保险）
保 BOM/LF 原子替换，逐锚点校验命中数。
"""
import os
from pathlib import Path

P = Path('logknow/bootstrap_knowledge.py')
raw = P.read_bytes()
bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
body = raw[len(bom):].decode('utf-8')
PATCHES = []

# 1) 插入归一器
ANCHOR = 'def _safe_name(name: str) -> str:'
INSERT = '''# ---------- 外文 -> 中文归一（用户定调：扫描外文识别成中文入库，不产生中英重复节点） ----------
_NORMALIZER = None


def _get_normalizer():
    """懒加载 RegionNormalizer；yaml/依赖缺失时降级为不归一（不阻断入档）。"""
    global _NORMALIZER
    if _NORMALIZER is None:
        try:
            from logknow.region_normalizer import RegionNormalizer
            _NORMALIZER = RegionNormalizer()
        except Exception:
            try:
                from region_normalizer import RegionNormalizer
                _NORMALIZER = RegionNormalizer()
            except Exception:
                _NORMALIZER = False
    return _NORMALIZER or None


def _cn(raw: str, kind: str = 'country'):
    """外文实体名 -> 中文规范名。返回 (入库名, 原文别名)；未命中则原样返回。
    kind='country' 用国别正典，'term' 用测井/地质术语表。国别归一后 canonical
    与既有 182 个中文国家节点一致，INSERT OR REPLACE 直接合并而非新建。"""
    s = ensure_str(raw)
    if not s:
        return '', ''
    rn = _get_normalizer()
    if rn is None:
        return s, ''
    target = rn.normalize_country(s) if kind == 'country' else rn.normalize_term(s)
    if target and target != s:
        return target, s
    return s, ''


'''
PATCHES.append((ANCHOR, INSERT + ANCHOR, 1))

# 2) simple_geo_extract 抽完后归一
PATCHES.append((
    '''    if not (country and formation):
        return []
    return [{
        "country": country,''',
    '''    # 外文 -> 中文规范名：与既有 182 个中文国家节点合并，杜绝中英重复节点
    aliases: Dict[str, str] = {}
    country, _a = _cn(country, 'country')
    if _a:
        aliases['country'] = _a
    basin, _a = _cn(basin, 'term')
    if _a:
        aliases['basin'] = _a
    formation, _a = _cn(formation, 'term')
    if _a:
        aliases['formation'] = _a
    method_name, _a = _cn(method_name, 'term')
    if _a:
        aliases['method_name'] = _a

    if not (country and formation):
        return []
    return [{
        "country": country,''',
    1,
))

# 3) strata_meta 保留原文别名
PATCHES.append((
    '''        "strata_meta": {"raw_source": "document_extract", "source_path": path_hint},''',
    '''        "strata_meta": {"raw_source": "document_extract", "source_path": path_hint,
                        "foreign_alias": aliases},''',
    1,
))

# 4) ingest_single_record 双保险
PATCHES.append((
    '''        source = f"static_geo/{fname}"
        country = ensure_str(rec.get("country"))
        basin = ensure_str(rec.get("basin"))''',
    '''        source = f"static_geo/{fname}"
        # 双保险：任何来源入库前国别都归一为中文正典，canonical 一致 -> 不产生中英重复节点
        country, _ = _cn(ensure_str(rec.get("country")), 'country')
        basin = ensure_str(rec.get("basin"))''',
    1,
))

for i, (old, new, expect) in enumerate(PATCHES, 1):
    n = body.count(old)
    if n != expect:
        raise SystemExit(f'PATCH {i} 命中数异常: 期望 {expect}, 实际 {n}')
    body = body.replace(old, new, expect)
    print(f'PATCH {i}: OK (命中 {n})')

out = bom + body.encode('utf-8')
tmp = P.with_suffix('.py.tmp')
tmp.write_bytes(out)
os.replace(tmp, P)
print(f'=== bootstrap_knowledge.py 原子替换完成: {len(out)} bytes ===')
